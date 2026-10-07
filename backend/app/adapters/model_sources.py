import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)

WEIGHT_SUFFIXES = (".safetensors", ".bin", ".pt", ".gguf")


class ModelMeta(BaseModel):
    id: str
    source: str
    locator: str
    name: str
    size_bytes: int | None = None
    architecture: str | None = None
    model_type: str | None = None
    quantization: str | None = None
    dtype: str | None = None
    max_context: int | None = None
    kv_bytes_per_token: int | None = None
    needs_remote_code: bool = False
    host_path: str
    container_subpath: str
    mount_host_path: str
    mount_rel_path: str = ""


class SourceInfo(BaseModel):
    id: str
    type: str
    path: str
    model_count: int
    available: bool


class ModelSource(ABC):
    id: str
    type: str

    @abstractmethod
    def scan(self) -> list[ModelMeta]: ...

    @abstractmethod
    def info(self, model_count: int) -> SourceInfo: ...


def parse_config(model_dir: Path) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        return data
    except (OSError, json.JSONDecodeError) as e:
        log.warning("cannot parse config.json in %s: %s", model_dir, e)
        return {}


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def _max_context(cfg: dict[str, Any]) -> int | None:
    text_cfg = cfg.get("text_config") if isinstance(cfg.get("text_config"), dict) else {}
    for src in (cfg, text_cfg or {}):
        for key in ("max_position_embeddings", "max_sequence_length", "seq_length", "n_positions"):
            val = src.get(key)
            if isinstance(val, int) and val > 0:
                return val
    return None


DTYPE_BYTES = {"float32": 4, "float16": 2, "bfloat16": 2, "float8": 1}


def _kv_bytes_per_token(cfg: dict[str, Any]) -> int | None:
    text_cfg = cfg.get("text_config")
    src: dict[str, Any] = text_cfg if isinstance(text_cfg, dict) else cfg

    def pos_int(key: str) -> int | None:
        v = src.get(key)
        return v if isinstance(v, int) and v > 0 else None

    layers = pos_int("num_hidden_layers")
    heads = pos_int("num_attention_heads")
    kv_heads = pos_int("num_key_value_heads") or heads
    head_dim = pos_int("head_dim")
    hidden = pos_int("hidden_size")
    if head_dim is None and hidden and heads:
        head_dim = hidden // heads
    if layers is None or kv_heads is None or not head_dim:
        return None
    dtype_bytes = DTYPE_BYTES.get(str(src.get("torch_dtype") or cfg.get("torch_dtype") or "bfloat16"), 2)
    return 2 * layers * kv_heads * head_dim * dtype_bytes


def meta_from_dir(
    model_dir: Path,
    *,
    source: str,
    locator: str,
    name: str,
    host_path: str,
    container_subpath: str,
    mount_host_path: str | None = None,
    mount_rel_path: str = "",
) -> ModelMeta:
    cfg = parse_config(model_dir)
    archs = cfg.get("architectures") or []
    quant = cfg.get("quantization_config") or {}
    return ModelMeta(
        id=f"{source}:{locator}",
        source=source,
        locator=locator,
        name=name,
        size_bytes=dir_size(model_dir),
        architecture=archs[0] if archs else None,
        model_type=cfg.get("model_type"),
        quantization=quant.get("quant_method") if isinstance(quant, dict) else None,
        dtype=cfg.get("torch_dtype") or cfg.get("dtype"),
        max_context=_max_context(cfg),
        kv_bytes_per_token=_kv_bytes_per_token(cfg),
        needs_remote_code=bool(cfg.get("auto_map")),
        host_path=host_path,
        container_subpath=container_subpath,
        mount_host_path=mount_host_path or host_path,
        mount_rel_path=mount_rel_path,
    )


def _has_weights(model_dir: Path) -> bool:
    return any(p.suffix in WEIGHT_SUFFIXES for p in model_dir.iterdir() if p.is_file())


class LocalDirSource(ModelSource):
    type = "local_dir"

    def __init__(self, source_id: str, root: Path, host_root: str) -> None:
        self.id = source_id
        self.root = root
        self.host_root = host_root.rstrip("/")

    def scan(self) -> list[ModelMeta]:
        if not self.root.is_dir():
            return []
        out: list[ModelMeta] = []
        for cfg in sorted(self.root.glob("*/config.json")) + sorted(self.root.glob("*/*/config.json")):
            model_dir = cfg.parent
            if any(part.startswith(".") for part in model_dir.relative_to(self.root).parts):
                continue  # hidden dirs, incl. in-progress downloads (.<name>.partial)
            if not _has_weights(model_dir):
                continue
            rel = model_dir.relative_to(self.root).as_posix()
            out.append(
                meta_from_dir(
                    model_dir,
                    source=self.id,
                    locator=rel,
                    name=model_dir.name,
                    host_path=f"{self.host_root}/{rel}",
                    container_subpath=rel,
                )
            )
        return out

    def info(self, model_count: int) -> SourceInfo:
        return SourceInfo(
            id=self.id, type=self.type, path=self.host_root, model_count=model_count, available=self.root.is_dir()
        )


class HFCacheSource(ModelSource):
    type = "hf_cache"

    def __init__(self, source_id: str, hub_dir: Path, host_hub_dir: str) -> None:
        self.id = source_id
        self.hub_dir = hub_dir
        self.host_hub_dir = host_hub_dir.rstrip("/")

    def scan(self) -> list[ModelMeta]:
        if not self.hub_dir.is_dir():
            return []
        out: list[ModelMeta] = []
        for repo in sorted(self.hub_dir.glob("models--*")):
            repo_id = repo.name.removeprefix("models--").replace("--", "/")
            ref = repo / "refs" / "main"
            snapshots = repo / "snapshots"
            snap: Path | None = None
            if ref.is_file():
                cand = snapshots / ref.read_text(encoding="utf-8").strip()
                snap = cand if cand.is_dir() else None
            if snap is None and snapshots.is_dir():
                snaps = sorted((p for p in snapshots.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
                snap = snaps[-1] if snaps else None
            if snap is None or not (snap / "config.json").is_file() or not _has_weights(snap):
                continue
            rel = snap.relative_to(self.hub_dir).as_posix()
            meta = meta_from_dir(
                snap,
                source=self.id,
                locator=repo_id,
                name=repo_id,
                host_path=f"{self.host_hub_dir}/{rel}",
                container_subpath=rel,
                mount_host_path=f"{self.host_hub_dir}/{repo.name}",
                mount_rel_path=snap.relative_to(repo).as_posix(),
            )
            meta.size_bytes = dir_size(repo / "blobs") if (repo / "blobs").is_dir() else meta.size_bytes
            out.append(meta)
        return out

    def info(self, model_count: int) -> SourceInfo:
        return SourceInfo(
            id=self.id, type=self.type, path=self.host_hub_dir, model_count=model_count, available=self.hub_dir.is_dir()
        )


class ModelCatalog:
    def __init__(self, sources: list[ModelSource]) -> None:
        self.sources = sources
        self._cache: dict[str, ModelMeta] = {}
        self._counts: dict[str, int] = {}

    def rescan(self) -> list[ModelMeta]:
        cache: dict[str, ModelMeta] = {}
        counts: dict[str, int] = {}
        for src in self.sources:
            try:
                found = src.scan()
            except OSError as e:
                log.warning("scan failed for source %s: %s", src.id, e)
                found = []
            counts[src.id] = len(found)
            for m in found:
                cache[m.id] = m
        self._cache, self._counts = cache, counts
        return list(cache.values())

    def all(self) -> list[ModelMeta]:
        if not self._cache and not self._counts:
            self.rescan()
        return list(self._cache.values())

    def get(self, model_id: str) -> ModelMeta | None:
        if model_id not in self._cache:
            self.rescan()
        return self._cache.get(model_id)

    def source_infos(self) -> list[SourceInfo]:
        if not self._counts:
            self.rescan()
        return [s.info(self._counts.get(s.id, 0)) for s in self.sources]
