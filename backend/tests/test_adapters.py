from pathlib import Path

from app.adapters.docker_runtime import ContainerSpec, DockerRuntime
from app.adapters.metrics import read_meminfo
from app.adapters.model_sources import HFCacheSource, LocalDirSource, ModelCatalog
from app.profiles import load_profile
from tests.conftest import REPO_ROOT, make_model

SPARK_MEMINFO = """MemTotal:       127598612 kB
MemFree:        80566912 kB
MemAvailable:   124034912 kB
Buffers:          470876 kB
Cached:         42605512 kB
SwapTotal:      16777212 kB
SwapFree:       16777212 kB
"""


def test_meminfo(tmp_path: Path) -> None:
    p = tmp_path / "meminfo"
    p.write_text(SPARK_MEMINFO)
    m = read_meminfo(p)
    assert m is not None
    assert round(m.total_bytes / 2**30, 1) == 121.7
    assert m.available_bytes > m.free_bytes
    assert m.used_bytes == m.total_bytes - m.available_bytes
    assert read_meminfo(tmp_path / "missing") is None


def test_local_dir_source(tmp_path: Path) -> None:
    make_model(
        tmp_path,
        "a",
        {
            "architectures": ["X"],
            "quantization_config": {"quant_method": "fp8"},
            "text_config": {"max_position_embeddings": 8192},
            "auto_map": {"x": "y"},
        },
    )
    make_model(tmp_path, "org/b", {"architectures": ["Y"]})
    (tmp_path / "no-weights").mkdir()
    (tmp_path / "no-weights" / "config.json").write_text("{}")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "config.json").write_text("{not json")
    (tmp_path / "broken" / "model.safetensors").write_bytes(b"0")

    found = {m.locator: m for m in LocalDirSource("local", tmp_path, "/data/models/").scan()}
    assert set(found) == {"a", "org/b", "broken"}
    a = found["a"]
    assert a.quantization == "fp8"
    assert a.max_context == 8192
    assert a.needs_remote_code is True
    assert a.host_path == "/data/models/a"
    assert found["broken"].architecture is None


def test_hf_cache_source(tmp_path: Path) -> None:
    repo = tmp_path / "models--Qwen--Qwen2.5-0.5B"
    snap = repo / "snapshots" / "abc123"
    make_model(snap.parent, "abc123", {"architectures": ["Qwen2ForCausalLM"]})
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text("abc123")
    found = HFCacheSource("hf_cache", tmp_path, "/home/u/.cache/huggingface/hub").scan()
    assert len(found) == 1
    m = found[0]
    assert m.id == "hf_cache:Qwen/Qwen2.5-0.5B"
    assert m.container_subpath == "models--Qwen--Qwen2.5-0.5B/snapshots/abc123"


def test_catalog_multiple_sources(tmp_path: Path) -> None:
    make_model(tmp_path / "local", "m1", {})
    cat = ModelCatalog(
        [LocalDirSource("local", tmp_path / "local", "/x"), HFCacheSource("hf", tmp_path / "missing", "/y")]
    )
    assert [m.id for m in cat.all()] == ["local:m1"]
    infos = {i.id: i for i in cat.source_infos()}
    assert infos["hf"].available is False
    assert cat.get("local:m1") is not None


def test_profiles_load() -> None:
    spark = load_profile(REPO_ROOT / "configs", "spark")
    assert spark.vllm.image.startswith("eugr/spark-vllm@sha256:")
    assert spark.vllm.gpu is True
    assert spark.vllm.ipc_host is False
    dev = load_profile(REPO_ROOT / "configs", "dev")
    assert dev.vllm.gpu is False


def test_docker_run_kwargs_spark() -> None:
    rt = DockerRuntime(load_profile(REPO_ROOT / "configs", "spark"), "dgxsp")
    spec = ContainerSpec(
        name="dgxsp-vllm-abc",
        instance_id="abc",
        served_model_name="qwen",
        command=["vllm", "serve", "/models/q"],
        host_model_path="/data/models/q",
        container_model_path="/models/q",
    )
    kw = rt.build_run_kwargs(spec)
    assert kw["network"] == "dgxsp"
    assert kw["labels"]["dgxsp.managed"] == "true"
    assert kw["volumes"] == {"/data/models/q": {"bind": "/models/q", "mode": "ro"}}
    assert kw["device_requests"][0]["Capabilities"] == [["gpu"]]
    assert kw["shm_size"] == "16g"
    assert "ipc_mode" not in kw
    assert "ports" not in kw
    assert kw["environment"]["HF_HUB_OFFLINE"] == "1"


def test_docker_run_kwargs_dev_with_port() -> None:
    rt = DockerRuntime(load_profile(REPO_ROOT / "configs", "dev"), "dgxsp")
    spec = ContainerSpec(
        name="n",
        instance_id="i",
        served_model_name="s",
        command=[],
        host_model_path="/h",
        container_model_path="/c",
        host_port=18000,
    )
    kw = rt.build_run_kwargs(spec)
    assert "device_requests" not in kw
    assert kw["ports"] == {"8000/tcp": 18000}
