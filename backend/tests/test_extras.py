from pathlib import Path

from fastapi.testclient import TestClient

from app.adapters.metrics import GpuProcess, GpuStats, container_of_pid, parse_gpu
from app.services.external import build_external

CID_EXT = "a" * 64
CID_OURS = "b" * 64


def proc_root(tmp_path: Path, pid: int, cgroup: str) -> Path:
    d = tmp_path / "proc" / str(pid)
    d.mkdir(parents=True)
    (d / "cgroup").write_text(cgroup)
    return tmp_path / "proc"


def test_container_of_pid(tmp_path: Path) -> None:
    root = proc_root(tmp_path, 42, f"0::/system.slice/docker-{CID_EXT}.scope\n")
    assert container_of_pid(42, root) == CID_EXT
    proc_root(tmp_path, 43, "0::/user.slice/user-1000.slice/session-2.scope\n")
    assert container_of_pid(43, root) is None
    assert container_of_pid(99, root) is None


def test_parse_gpu_spark_shape(tmp_path: Path) -> None:
    root = proc_root(tmp_path, 4810, f"0::/docker/{CID_OURS}\n")
    stats = parse_gpu(
        [["NVIDIA GB10", "580.178.04", "37", "45", "[N/A]"]],
        [["3106", "/usr/lib/xorg/Xorg", "59"], ["4810", "VLLM::EngineCore", "11791"], ["x", "bad", "1"]],
        root,
    )
    assert stats.name == "NVIDIA GB10"
    assert stats.utilization_pct == 37
    assert stats.temperature_c == 45
    assert stats.power_w is None
    assert [p.pid for p in stats.processes] == [3106, 4810]
    assert stats.processes[1].container_id == CID_OURS
    assert stats.process_bytes == (59 + 11791) * 2**20


def test_build_external() -> None:
    gpu = GpuStats(
        processes=[
            GpuProcess(pid=1, name="/usr/lib/xorg/Xorg", used_bytes=59 * 2**20),
            GpuProcess(pid=2, name="VLLM::EngineCore", used_bytes=36 * 2**30, container_id=CID_EXT),
            GpuProcess(pid=3, name="VLLM::EngineCore", used_bytes=28 * 2**30, container_id=CID_OURS),
            GpuProcess(pid=4, name="python", used_bytes=3 * 2**30),
        ]
    )
    containers = [{"id": CID_EXT, "name": "vllm_node", "image": "vllm-node", "status": "running", "ports": []}]
    ext = build_external(containers, gpu, {CID_OURS})
    names = [s.name for s in ext.services]
    assert names == ["vllm_node", "python"]
    assert ext.services[0].gpu_bytes == 36 * 2**30
    assert ext.services[0].hint_key == "external.hint.vllm"
    assert ext.services[1].kind == "process"
    assert ext.total_gpu_bytes == 39 * 2**30


def test_model_details_and_logs_sources(client: TestClient, auth: dict[str, str]) -> None:
    d = client.get("/api/v1/model-details/local:Qwen2.5-0.5B-Instruct", headers=auth)
    assert d.status_code == 200
    body = d.json()
    assert body["config"]["num_hidden_layers"] == 24
    assert body["config"]["architectures"] == ["Qwen2ForCausalLM"]
    assert [f["name"] for f in body["files"]] == ["config.json", "model.safetensors"]
    assert {p["id"] for p in body["presets"]} >= {"balanced", "low_memory"}
    assert client.get("/api/v1/model-details/local:nope", headers=auth).status_code == 404
    assert client.get("/api/v1/logs/unknown", headers=auth).status_code == 404
