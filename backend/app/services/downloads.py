import asyncio
import contextlib
import fnmatch
import json
import logging
import os
import re
import shutil
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from app.adapters.model_sources import _max_context as max_context
from app.adapters.model_sources import dir_size
from app.db.models import Download

log = logging.getLogger(__name__)

REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
DIR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DEFAULT_PATTERNS = [
    "*.json",
    "*.safetensors",
    "*.txt",
    "*.model",
    "*.tiktoken",
    "*.jinja",
    "*.py",
    "tokenizer*",
]
ACTIVE = ("queued", "downloading")
PARTIAL_SUFFIX = ".partial"
DISK_MARGIN_MAX = 5 * 2**30
DISK_MARGIN_MIN = 512 * 2**20


def disk_margin(size: int) -> int:
    return max(DISK_MARGIN_MIN, min(DISK_MARGIN_MAX, size // 10))


def utcnow() -> datetime:
    return datetime.now(UTC)


class DownloadError(Exception):
    def __init__(self, code: str, status: int = 400, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.params = params or {}


class RepoFile(BaseModel):
    path: str
    size: int | None


class RepoInfo(BaseModel):
    repo_id: str
    revision: str | None = None
    sha: str | None = None
    gated: bool | str = False
    private: bool = False
    files: list[RepoFile] = Field(default_factory=list)
    config: dict[str, Any] | None = None


class DownloadPreview(BaseModel):
    repo_id: str
    target_dir: str
    exists: bool
    files: int
    size_bytes: int
    disk_free_bytes: int | None
    has_config: bool
    has_weights: bool
    architecture: str | None = None
    quantization: str | None = None
    max_context: int | None = None
    gated: bool = False
    warnings: list[str] = Field(default_factory=list)
    blocking: bool = False


SPEED_WINDOW_S = 10.0


class SpeedTracker:
    """Speed averaged over a sliding window, so a second without disk writes doesn't read as 0 B/s."""

    def __init__(self, window_s: float = SPEED_WINDOW_S) -> None:
        self.window_s = window_s
        self._samples: deque[tuple[float, int]] = deque()
        self._last_growth: float | None = None
        self._last_bytes = -1

    def add(self, t: float, nbytes: int) -> None:
        if self._last_growth is None or nbytes > self._last_bytes:
            self._last_growth = t
        self._last_bytes = max(self._last_bytes, nbytes)
        self._samples.append((t, nbytes))
        while len(self._samples) > 2 and t - self._samples[1][0] >= self.window_s:
            self._samples.popleft()

    def speed(self) -> float | None:
        if len(self._samples) < 2:
            return None
        (t0, b0), (t1, b1) = self._samples[0], self._samples[-1]
        return max(0.0, (b1 - b0) / (t1 - t0)) if t1 > t0 else None

    def stalled_for(self, now: float) -> float:
        return 0.0 if self._last_growth is None else max(0.0, now - self._last_growth)


class DownloadOut(BaseModel):
    id: str
    repo_id: str
    revision: str | None
    target_dir: str
    status: str
    bytes_total: int | None
    bytes_done: int
    files_total: int | None
    progress: float | None
    speed_bps: float | None = None
    stalled_s: float | None = None
    error: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    model_id: str | None = None


class HubClient(Protocol):
    def inspect(self, repo_id: str, revision: str | None, token: str | None) -> RepoInfo: ...


EndpointSource = Callable[[], str | None]


def _const(v: str | None) -> EndpointSource:
    return lambda: v


class HFHubClient:
    def __init__(self, endpoint: str | None | EndpointSource = None) -> None:
        self._endpoint: EndpointSource = endpoint if callable(endpoint) else _const(endpoint)

    @property
    def endpoint(self) -> str | None:
        return self._endpoint()

    @staticmethod
    def ping(endpoint: str | None, timeout: float = 8.0) -> dict[str, Any]:
        """Check from this host that the hub (or a mirror) answers the model API."""
        import time

        import httpx

        base = (endpoint or "https://huggingface.co").rstrip("/")
        t0 = time.monotonic()
        try:
            r = httpx.get(f"{base}/api/models", params={"limit": 1}, timeout=timeout, follow_redirects=True)
        except httpx.TimeoutException:
            return {"ok": False, "reason": "timeout", "url": base}
        except httpx.HTTPError:
            return {"ok": False, "reason": "network", "url": base}
        ms = int((time.monotonic() - t0) * 1000)
        if r.status_code != 200:
            return {"ok": False, "reason": "http", "status": r.status_code, "url": base}
        try:
            valid = isinstance(r.json(), list)
        except ValueError:
            valid = False
        if not valid:
            return {"ok": False, "reason": "not_hf", "url": base}
        return {"ok": True, "ms": ms, "url": base}

    def inspect(self, repo_id: str, revision: str | None, token: str | None) -> RepoInfo:
        from huggingface_hub import HfApi, hf_hub_download
        from huggingface_hub.errors import (
            GatedRepoError,
            HfHubHTTPError,
            RepositoryNotFoundError,
            RevisionNotFoundError,
        )

        api = HfApi(endpoint=self.endpoint, token=token or None)
        try:
            info = api.model_info(repo_id, revision=revision, files_metadata=True)
        except GatedRepoError as e:
            raise DownloadError("REPO_GATED", 403) from e
        except (RepositoryNotFoundError, RevisionNotFoundError) as e:
            raise DownloadError("REPO_NOT_FOUND", 404) from e
        except HfHubHTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (401, 403):
                raise DownloadError("REPO_GATED", 403) from e
            if status == 404:
                raise DownloadError("REPO_NOT_FOUND", 404) from e
            raise DownloadError("HUB_UNREACHABLE", 502) from e
        except Exception as e:
            raise DownloadError("HUB_UNREACHABLE", 502) from e
        files = [RepoFile(path=s.rfilename, size=getattr(s, "size", None)) for s in (info.siblings or [])]
        config = None
        gated = getattr(info, "gated", False) or False
        if any(f.path == "config.json" for f in files):
            try:
                path = hf_hub_download(
                    repo_id, "config.json", revision=revision, token=token or None, endpoint=self.endpoint
                )
                config = json.loads(Path(path).read_text(encoding="utf-8"))
            except GatedRepoError as e:
                raise DownloadError("REPO_GATED", 403) from e
            except HfHubHTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if gated or status in (401, 403):
                    raise DownloadError("REPO_GATED", 403) from e
                log.info("could not fetch config.json for %s: %s", repo_id, e)
            except Exception as e:  # noqa: BLE001
                log.info("could not fetch config.json for %s: %s", repo_id, e)
        return RepoInfo(
            repo_id=repo_id,
            revision=revision,
            sha=getattr(info, "sha", None),
            gated=gated,
            private=bool(getattr(info, "private", False)),
            files=files,
            config=config,
        )


@dataclass
class Fetcher:
    """Runs the worker as a subprocess. Replaceable in tests."""

    python: str = sys.executable
    endpoint_source: EndpointSource = field(default_factory=lambda: _const(None))

    @property
    def endpoint(self) -> str | None:
        return self.endpoint_source()

    async def start(
        self, repo_id: str, revision: str | None, local_dir: Path, patterns: list[str], token: str | None
    ) -> asyncio.subprocess.Process:
        env = {**os.environ, "HF_TOKEN": token or "", "HF_HUB_DISABLE_TELEMETRY": "1"}
        args = json.dumps(
            {
                "repo_id": repo_id,
                "revision": revision,
                "local_dir": str(local_dir),
                "allow_patterns": patterns,
                "endpoint": self.endpoint,
            }
        )
        return await asyncio.create_subprocess_exec(
            self.python,
            "-m",
            "app.workers.hf_download",
            args,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )


def matches(path: str, patterns: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def default_dir_name(repo_id: str) -> str:
    return repo_id.split("/")[-1]


class DownloadManager:
    def __init__(
        self,
        *,
        engine: Engine,
        model_root: Path,
        hub: HubClient,
        fetcher: Any,
        token: Callable[[], str | None],
        on_complete: Callable[[], object],
        owner: tuple[int, int] | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self.engine = engine
        self.model_root = model_root
        self.hub = hub
        self.fetcher = fetcher
        self.token = token
        self.on_complete = on_complete
        self.owner = owner
        self.poll_interval = poll_interval
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._current: str | None = None
        self._proc: Any = None
        self._cancel_requested: set[str] = set()
        self._speed: dict[str, SpeedTracker] = {}
        self.clock: Callable[[], float] = time.monotonic

    # ------------------------------------------------------------------ helpers

    def _get(self, download_id: str) -> Download:
        with Session(self.engine) as s:
            d = s.get(Download, download_id)
            if d is None:
                raise DownloadError("DOWNLOAD_NOT_FOUND", 404)
            s.expunge(d)
            return d

    def _update(self, download_id: str, **fields: Any) -> None:
        with Session(self.engine) as s:
            d = s.get(Download, download_id)
            if d is None:
                return
            for k, v in fields.items():
                setattr(d, k, v)
            s.add(d)
            s.commit()

    def all(self) -> list[Download]:
        with Session(self.engine) as s:
            rows = list(s.exec(select(Download).order_by(col(Download.created_at).desc())).all())
            for r in rows:
                s.expunge(r)
            return rows

    def out(self, d: Download) -> DownloadOut:
        progress = None
        if d.bytes_total:
            progress = min(1.0, d.bytes_done / d.bytes_total) if d.status != "completed" else 1.0
        model_id = f"local:{d.target_dir}" if d.status == "completed" else None
        tracker = self._speed.get(d.id) if d.status == "downloading" else None
        return DownloadOut(
            id=d.id,
            repo_id=d.repo_id,
            revision=d.revision,
            target_dir=d.target_dir,
            status=d.status,
            bytes_total=d.bytes_total,
            bytes_done=d.bytes_done,
            files_total=d.files_total,
            progress=progress,
            speed_bps=tracker.speed() if tracker else None,
            stalled_s=round(tracker.stalled_for(self.clock()), 1) if tracker else None,
            error=d.error,
            created_at=d.created_at,
            started_at=d.started_at,
            finished_at=d.finished_at,
            model_id=model_id,
        )

    def _validate(self, repo_id: str, target_dir: str | None) -> tuple[str, str]:
        repo_id = repo_id.strip().strip("/")
        if repo_id.startswith("https://huggingface.co/"):
            repo_id = "/".join(repo_id.removeprefix("https://huggingface.co/").split("/")[:2])
        if not REPO_RE.match(repo_id) or ".." in repo_id:
            raise DownloadError("REPO_ID_INVALID", 422)
        name = (target_dir or default_dir_name(repo_id)).strip()
        if not DIR_RE.match(name) or name in (".", "..") or name.endswith(PARTIAL_SUFFIX):
            raise DownloadError("TARGET_DIR_INVALID", 422)
        return repo_id, name

    def _disk_free(self) -> int | None:
        try:
            return shutil.disk_usage(self.model_root).free
        except OSError:
            return None

    def _active_targets(self) -> set[str]:
        return {d.target_dir for d in self.all() if d.status in ACTIVE}

    # ------------------------------------------------------------------ preview / create

    def preview(self, repo_id: str, target_dir: str | None, revision: str | None = None) -> DownloadPreview:
        repo_id, name = self._validate(repo_id, target_dir)
        info = self.hub.inspect(repo_id, revision, self.token())
        selected = [f for f in info.files if matches(f.path, DEFAULT_PATTERNS)]
        size = sum(f.size or 0 for f in selected)
        has_weights = any(f.path.endswith(".safetensors") for f in selected)
        has_bin_only = not has_weights and any(f.path.endswith((".bin", ".pt", ".gguf")) for f in info.files)
        cfg = info.config or {}
        archs = cfg.get("architectures") or []
        quant = cfg.get("quantization_config") or {}
        exists = (self.model_root / name).exists() or name in self._active_targets()
        free = self._disk_free()
        warnings: list[str] = []
        blocking = False
        if exists:
            warnings.append("TARGET_EXISTS")
            blocking = True
        if not any(f.path == "config.json" for f in info.files):
            warnings.append("NO_CONFIG")
            blocking = True
        if not has_weights:
            warnings.append("NO_SAFETENSORS_BIN_ONLY" if has_bin_only else "NO_WEIGHTS")
            blocking = True
        if free is not None and size + disk_margin(size) > free:
            warnings.append("DISK_SPACE_LOW")
            blocking = True
        if cfg.get("auto_map"):
            warnings.append("REMOTE_CODE")
        if info.gated:
            warnings.append("GATED_OK")
        return DownloadPreview(
            repo_id=repo_id,
            target_dir=name,
            exists=exists,
            files=len(selected),
            size_bytes=size,
            disk_free_bytes=free,
            has_config=info.config is not None,
            has_weights=has_weights,
            architecture=archs[0] if archs else None,
            quantization=quant.get("quant_method") if isinstance(quant, dict) else None,
            max_context=max_context(cfg) if cfg else None,
            gated=bool(info.gated),
            warnings=warnings,
            blocking=blocking,
        )

    def create(self, repo_id: str, target_dir: str | None, revision: str | None = None) -> Download:
        p = self.preview(repo_id, target_dir, revision)
        if p.blocking:
            raise DownloadError("DOWNLOAD_BLOCKED", 409, {"warnings": p.warnings})
        d = Download(
            repo_id=p.repo_id,
            revision=revision,
            target_dir=p.target_dir,
            allow_patterns=DEFAULT_PATTERNS,
            bytes_total=p.size_bytes,
            files_total=p.files,
        )
        with Session(self.engine) as s:
            s.add(d)
            s.commit()
            s.refresh(d)
            s.expunge(d)
        self._wake.set()
        return d

    async def cancel(self, download_id: str) -> Download:
        d = self._get(download_id)
        if d.status not in ACTIVE:
            raise DownloadError("DOWNLOAD_NOT_ACTIVE", 409)
        if self._current == download_id and self._proc is not None:
            self._cancel_requested.add(download_id)
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()
            for _ in range(100):
                if self._get(download_id).status not in ACTIVE:
                    break
                await asyncio.sleep(0.05)
        else:
            self._update(download_id, status="cancelled", finished_at=utcnow())
            self._remove_partial(d.target_dir)
        return self._get(download_id)

    def retry(self, download_id: str) -> Download:
        d = self._get(download_id)
        if d.status not in ("failed", "cancelled"):
            raise DownloadError("DOWNLOAD_NOT_RETRYABLE", 409)
        if (self.model_root / d.target_dir).exists() or d.target_dir in self._active_targets():
            raise DownloadError("DOWNLOAD_BLOCKED", 409, {"warnings": ["TARGET_EXISTS"]})
        self._update(download_id, status="queued", error=None, bytes_done=0, started_at=None, finished_at=None)
        self._wake.set()
        return self._get(download_id)

    def delete(self, download_id: str) -> None:
        d = self._get(download_id)
        if d.status in ACTIVE:
            raise DownloadError("DOWNLOAD_ACTIVE", 409)
        with Session(self.engine) as s:
            row = s.get(Download, download_id)
            if row:
                s.delete(row)
                s.commit()

    # ------------------------------------------------------------------ worker

    def _partial(self, target: str) -> Path:
        return self.model_root / f".{target}{PARTIAL_SUFFIX}"

    def _remove_partial(self, target: str) -> None:
        shutil.rmtree(self._partial(target), ignore_errors=True)

    def _next(self) -> Download | None:
        with Session(self.engine) as s:
            d = s.exec(select(Download).where(Download.status == "queued").order_by(col(Download.created_at))).first()
            if d:
                s.expunge(d)
            return d

    async def startup(self) -> None:
        with Session(self.engine) as s:
            for d in s.exec(select(Download).where(col(Download.status).in_(ACTIVE))).all():
                if d.status == "downloading":
                    d.status = "queued"
                    s.add(d)
            s.commit()
        for p in self.model_root.glob(f".*{PARTIAL_SUFFIX}") if self.model_root.is_dir() else []:
            target = p.name[1 : -len(PARTIAL_SUFFIX)]
            if target not in self._active_targets():
                shutil.rmtree(p, ignore_errors=True)
        self._task = asyncio.create_task(self._loop(), name="downloads")
        self._wake.set()

    async def shutdown(self) -> None:
        if self._proc is not None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task

    async def _loop(self) -> None:
        while True:
            d = self._next()
            if d is None:
                self._wake.clear()
                await self._wake.wait()
                continue
            try:
                await self._run(d)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("download %s failed", d.id)
                self._update(
                    d.id,
                    status="failed",
                    finished_at=utcnow(),
                    error={"code": "UNKNOWN", "message": repr(e)[:300]},
                )
                self._remove_partial(d.target_dir)
            finally:
                self._current = None
                self._proc = None

    async def _run(self, d: Download) -> None:
        final = self.model_root / d.target_dir
        partial = self._partial(d.target_dir)
        if final.exists():
            self._update(d.id, status="failed", finished_at=utcnow(), error={"code": "TARGET_EXISTS"})
            return
        partial.mkdir(parents=True, exist_ok=True)
        self._current = d.id
        self._update(d.id, status="downloading", started_at=utcnow(), bytes_done=0, error=None)
        proc = await self.fetcher.start(d.repo_id, d.revision, partial, d.allow_patterns, self.token())
        self._proc = proc

        stderr_chunks: list[bytes] = []

        async def read_stderr() -> None:
            if proc.stderr is None:
                return
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    return
                stderr_chunks.append(chunk)

        reader = asyncio.create_task(read_stderr())
        tracker = SpeedTracker()
        tracker.add(self.clock(), 0)
        self._speed[d.id] = tracker
        while True:
            try:
                await asyncio.wait_for(proc.wait(), timeout=self.poll_interval)
                break
            except TimeoutError:
                done = await asyncio.to_thread(dir_size, partial)
                tracker.add(self.clock(), done)
                self._update(d.id, bytes_done=done)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(reader, timeout=5)
        self._speed.pop(d.id, None)
        rc = proc.returncode

        if d.id in self._cancel_requested:
            self._cancel_requested.discard(d.id)
            self._remove_partial(d.target_dir)
            self._update(d.id, status="cancelled", finished_at=utcnow())
            return

        if rc != 0:
            err = self._parse_error(b"".join(stderr_chunks).decode(errors="replace"), rc)
            self._remove_partial(d.target_dir)
            self._update(d.id, status="failed", finished_at=utcnow(), error=err)
            return

        cache = partial / ".cache"
        shutil.rmtree(cache, ignore_errors=True)
        if not (partial / "config.json").is_file():
            self._remove_partial(d.target_dir)
            self._update(d.id, status="failed", finished_at=utcnow(), error={"code": "NO_CONFIG"})
            return
        if self.owner:
            self._chown(partial, *self.owner)
        total = await asyncio.to_thread(dir_size, partial)
        os.replace(partial, final)
        self._update(d.id, status="completed", finished_at=utcnow(), bytes_done=total, bytes_total=total)
        try:
            self.on_complete()
        except Exception:  # noqa: BLE001
            log.exception("rescan after download failed")

    @staticmethod
    def _chown(path: Path, uid: int, gid: int) -> None:
        chown = getattr(os, "chown", None)
        if chown is None:
            return
        with contextlib.suppress(OSError):
            chown(path, uid, gid)
            for root, dirs, files in os.walk(path):
                for n in dirs + files:
                    chown(os.path.join(root, n), uid, gid)

    @staticmethod
    def _parse_error(stderr: str, rc: int | None) -> dict[str, Any]:
        for line in reversed(stderr.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                with contextlib.suppress(ValueError):
                    data = json.loads(line)
                    if isinstance(data, dict) and "code" in data:
                        return {"code": data["code"], "message": str(data.get("message", ""))[:300]}
        tail = stderr.strip().splitlines()[-1:] if stderr.strip() else []
        return {"code": "UNKNOWN", "message": (tail[0] if tail else f"exit {rc}")[:300]}
