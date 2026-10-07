import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from app.db.session import build_engine, init_db
from app.services.downloads import DownloadError, DownloadManager, RepoFile, RepoInfo, SpeedTracker, matches

WORKER = Path(__file__).with_name("fake_hf_worker.py")


class FakeHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def inspect(self, repo_id: str, revision: str | None, token: str | None) -> RepoInfo:
        self.calls.append((repo_id, token))
        if repo_id.endswith("/missing"):
            raise DownloadError("REPO_NOT_FOUND", 404)
        files = [
            RepoFile(path="config.json", size=100),
            RepoFile(path="model-00001.safetensors", size=3000),
            RepoFile(path="tokenizer.json", size=50),
            RepoFile(path="README.md", size=10),
            RepoFile(path="pytorch_model.bin", size=999999),
        ]
        if repo_id.endswith("/binonly"):
            files = [RepoFile(path="config.json", size=1), RepoFile(path="pytorch_model.bin", size=10)]
        if repo_id.endswith("/huge"):
            files = [RepoFile(path="config.json", size=1), RepoFile(path="m.safetensors", size=10**18)]
        cfg = {
            "architectures": ["Qwen2ForCausalLM"],
            "max_position_embeddings": 32768,
            "quantization_config": {"quant_method": "fp8"},
        }
        return RepoInfo(repo_id=repo_id, files=files, config=cfg, gated=repo_id.endswith("/gated"))


class ScriptFetcher:
    async def start(self, repo_id, revision, local_dir, patterns, token):  # type: ignore[no-untyped-def]
        import os

        env = {**os.environ, "HF_TOKEN": token or ""}
        args = json.dumps({"repo_id": repo_id, "local_dir": str(local_dir), "allow_patterns": patterns})
        return await asyncio.create_subprocess_exec(
            sys.executable,
            str(WORKER),
            args,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    e = build_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    init_db(e)
    return e


@pytest.fixture
async def mgr(tmp_path: Path, engine: Engine) -> AsyncIterator[DownloadManager]:
    root = tmp_path / "models"
    root.mkdir()
    rescans: list[int] = []
    m = DownloadManager(
        engine=engine,
        model_root=root,
        hub=FakeHub(),
        fetcher=ScriptFetcher(),
        token=lambda: "hf_secret",
        on_complete=lambda: rescans.append(1),
        poll_interval=0.05,
    )
    m.rescans = rescans  # type: ignore[attr-defined]
    await m.startup()
    yield m
    await m.shutdown()


async def wait_done(m: DownloadManager, did: str, timeout: float = 20) -> str:
    for _ in range(int(timeout / 0.05)):
        st = m._get(did).status
        if st not in ("queued", "downloading"):
            return st
        await asyncio.sleep(0.05)
    raise AssertionError("download did not finish")


def test_patterns() -> None:
    from app.services.downloads import DEFAULT_PATTERNS

    assert matches("config.json", DEFAULT_PATTERNS)
    assert matches("sub/model-00001-of-00004.safetensors", DEFAULT_PATTERNS)
    assert matches("tokenizer.model", DEFAULT_PATTERNS)
    assert not matches("pytorch_model.bin", DEFAULT_PATTERNS)
    assert not matches("original/consolidated.pth", DEFAULT_PATTERNS)


def test_speed_tracker_smooths_gaps_and_reports_stall() -> None:
    s = SpeedTracker(window_s=10)
    s.add(0, 0)
    assert s.speed() is None
    s.add(1, 100)
    assert s.speed() == 100
    s.add(2, 100)
    assert s.speed() == 50
    assert s.stalled_for(2) == 1
    for t in range(3, 13):
        s.add(t, 100 + (t - 2) * 100)
    assert s.speed() == pytest.approx(100, rel=0.11)
    assert s.stalled_for(12) == 0
    for t in range(13, 50):
        s.add(t, 1100)
    assert s.speed() == 0
    assert s.stalled_for(49) == 37


async def test_preview(mgr: DownloadManager) -> None:
    p = mgr.preview("Qwen/Qwen2.5-7B-Instruct", None)
    assert p.target_dir == "Qwen2.5-7B-Instruct"
    assert p.size_bytes == 3150
    assert p.files == 3
    assert p.architecture == "Qwen2ForCausalLM"
    assert p.quantization == "fp8"
    assert p.max_context == 32768
    assert not p.blocking
    assert mgr.preview("https://huggingface.co/Qwen/Qwen2.5-7B-Instruct", None).repo_id == "Qwen/Qwen2.5-7B-Instruct"

    assert "NO_SAFETENSORS_BIN_ONLY" in mgr.preview("a/binonly", None).warnings
    huge = mgr.preview("a/huge", None)
    assert huge.blocking and "DISK_SPACE_LOW" in huge.warnings
    with pytest.raises(DownloadError) as e:
        mgr.preview("not a repo", None)
    assert e.value.code == "REPO_ID_INVALID"
    with pytest.raises(DownloadError) as e:
        mgr.preview("a/b", "../escape")
    assert e.value.code == "TARGET_DIR_INVALID"
    with pytest.raises(DownloadError) as e:
        mgr.preview("a/missing", None)
    assert e.value.code == "REPO_NOT_FOUND"


async def test_download_success(mgr: DownloadManager) -> None:
    d = mgr.create("org/good", "good-model")
    assert await wait_done(mgr, d.id) == "completed"
    final = mgr.model_root / "good-model"
    assert (final / "config.json").is_file()
    assert len(list(final.glob("*.safetensors"))) == 3
    assert not (final / ".cache").exists()
    assert not list(mgr.model_root.glob(".*.partial"))
    out = mgr.out(mgr._get(d.id))
    assert out.progress == 1.0
    assert out.model_id == "local:good-model"
    assert mgr.rescans == [1]  # type: ignore[attr-defined]
    p = mgr.preview("org/good", "good-model")
    assert p.blocking and "TARGET_EXISTS" in p.warnings


async def test_download_failures(mgr: DownloadManager) -> None:
    g = mgr.create("org/gated", "g")
    assert await wait_done(mgr, g.id) == "failed"
    assert mgr._get(g.id).error["code"] == "REPO_GATED"  # type: ignore[index]
    assert not (mgr.model_root / "g").exists()

    n = mgr.create("org/noconfig", "n")
    assert await wait_done(mgr, n.id) == "failed"
    assert mgr._get(n.id).error["code"] == "NO_CONFIG"  # type: ignore[index]
    assert not list(mgr.model_root.iterdir())


async def test_cancel_running_and_queued(mgr: DownloadManager) -> None:
    slow = mgr.create("org/slow", "slow")
    queued = mgr.create("org/good", "after")
    for _ in range(100):
        if mgr._get(slow.id).status == "downloading" and mgr._get(slow.id).bytes_done > 0:
            break
        await asyncio.sleep(0.05)
    assert mgr._get(queued.id).status == "queued"
    assert (await mgr.cancel(queued.id)).status == "cancelled"
    n_rescans = len(mgr.rescans)  # type: ignore[attr-defined]
    assert (await mgr.cancel(slow.id)).status == "cancelled"
    assert not (mgr.model_root / "slow").exists()
    assert not list(mgr.model_root.glob(".*.partial"))
    assert len(mgr.rescans) > n_rescans  # type: ignore[attr-defined]
    assert mgr._get(slow.id).error is None

    again = mgr.retry(queued.id)
    assert again.status == "queued"
    assert await wait_done(mgr, queued.id) == "completed"
    mgr.delete(slow.id)
    with pytest.raises(DownloadError):
        mgr._get(slow.id)


async def test_one_at_a_time_and_duplicate_target(mgr: DownloadManager) -> None:
    a = mgr.create("org/slow", "x")
    with pytest.raises(DownloadError) as e:
        mgr.create("org/good", "x")
    assert e.value.code == "DOWNLOAD_BLOCKED"
    b = mgr.create("org/good", "y")
    await asyncio.sleep(0.3)
    assert mgr._get(b.id).status == "queued"
    await mgr.cancel(a.id)
    assert await wait_done(mgr, b.id) == "completed"


async def test_startup_requeues_and_cleans(tmp_path: Path, engine: Engine) -> None:
    root = tmp_path / "m2"
    root.mkdir()
    (root / ".stale.partial").mkdir()
    m = DownloadManager(
        engine=engine,
        model_root=root,
        hub=FakeHub(),
        fetcher=ScriptFetcher(),
        token=lambda: None,
        on_complete=lambda: None,
        poll_interval=0.05,
    )
    d = m.create("org/good", "resume")
    m._update(d.id, status="downloading")
    await m.startup()
    try:
        assert not (root / ".stale.partial").exists()
        assert await wait_done(m, d.id) == "completed"
    finally:
        await m.shutdown()


def test_api_preview_and_token(client, auth) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/api/v1/settings/hf-token", headers=auth)
    assert r.json() == {"configured": False, "source": None}
    r = client.put("/api/v1/settings/hf-token", json={"token": "hf_abc"}, headers=auth)
    assert r.json() == {"configured": True, "source": "web"}
    assert "hf_abc" not in r.text
    r = client.put("/api/v1/settings/hf-token", json={"token": ""}, headers=auth)
    assert r.json()["configured"] is False
    bad = client.post("/api/v1/downloads/preview", json={"repo_id": "no-slash"}, headers=auth)
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "REPO_ID_INVALID"
    assert client.get("/api/v1/downloads", headers=auth).json() == []


def test_api_delete_model(client, auth, settings) -> None:  # type: ignore[no-untyped-def]
    mid = "local:Qwen2.5-0.5B-Instruct"
    inst = client.post("/api/v1/instances", json={"model_id": mid, "start": False}, headers=auth).json()
    r = client.delete(f"/api/v1/models/{mid}", headers=auth)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MODEL_IN_USE"
    client.delete(f"/api/v1/instances/{inst['id']}", headers=auth)
    assert client.delete(f"/api/v1/models/{mid}", headers=auth).status_code == 204
    assert not (settings.model_root / "Qwen2.5-0.5B-Instruct").exists()
    assert client.get("/api/v1/models", headers=auth).json() == []
    assert client.delete("/api/v1/models/local:..%2F..%2Fetc", headers=auth).status_code == 404


def test_scan_skips_partial_and_hidden_dirs(tmp_path: Path) -> None:
    from app.adapters.model_sources import LocalDirSource
    from tests.conftest import QWEN_CONFIG, make_model

    make_model(tmp_path, "real", QWEN_CONFIG)
    make_model(tmp_path, ".gpt-oss-20b.partial", QWEN_CONFIG)
    make_model(tmp_path / ".hidden", "inner", QWEN_CONFIG)
    assert [m.locator for m in LocalDirSource("local", tmp_path, "/data/models").scan()] == ["real"]


def test_remove_partial_reports_leftovers(tmp_path: Path, engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    m = DownloadManager(
        engine=engine,
        model_root=tmp_path,
        hub=FakeHub(),
        fetcher=ScriptFetcher(),
        token=lambda: None,
        on_complete=lambda: None,
    )
    p = tmp_path / ".stuck.partial"
    p.mkdir()
    (p / "f").write_text("x")
    assert m._remove_partial("missing") is True

    def fake_rmtree(path, onexc=None):  # type: ignore[no-untyped-def]
        onexc(None, str(path), PermissionError("denied"))

    monkeypatch.setattr("app.services.downloads.shutil.rmtree", fake_rmtree)
    assert m._remove_partial("stuck") is False
    d = m.create("org/good", "stuck")
    m._cleanup_failed(d.id, "stuck", status="cancelled")
    err = m._get(d.id).error
    assert err is not None and err["leftover"].endswith(".stuck.partial")


def test_api_delete_model_edge_cases(client, auth, settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import shutil as _shutil

    from tests.conftest import QWEN_CONFIG, make_model

    mid = "local:Qwen2.5-0.5B-Instruct"
    assert client.get("/api/v1/models", headers=auth).status_code == 200
    _shutil.rmtree(settings.model_root / "Qwen2.5-0.5B-Instruct")
    r = client.delete(f"/api/v1/models/{mid}", headers=auth)
    assert r.status_code == 204
    assert client.get("/api/v1/models", headers=auth).json() == []

    make_model(settings.model_root, "busy", QWEN_CONFIG)
    client.post("/api/v1/model-sources/rescan", headers=auth)
    svc = client.app.state.services
    monkeypatch.setattr(svc.downloads, "is_busy", lambda t: t == "busy")
    r = client.delete("/api/v1/models/local:busy", headers=auth)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "DOWNLOAD_ACTIVE"
    monkeypatch.setattr(svc.downloads, "is_busy", lambda t: False)

    def denied(path):  # type: ignore[no-untyped-def]
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr("app.api.downloads.shutil.rmtree", denied)
    r = client.delete("/api/v1/models/local:busy", headers=auth)
    assert r.status_code == 500 and r.json()["detail"]["code"] == "MODEL_DELETE_PERMISSION"

    def other(path):  # type: ignore[no-untyped-def]
        raise OSError(39, "Directory not empty", str(path))

    monkeypatch.setattr("app.api.downloads.shutil.rmtree", other)
    r = client.delete("/api/v1/models/local:busy", headers=auth)
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "MODEL_DELETE_FAILED"
    assert "Directory not empty" in r.json()["detail"]["params"]["error"]
