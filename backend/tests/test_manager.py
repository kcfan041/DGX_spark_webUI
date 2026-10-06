import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from app.adapters.litellm_client import GatewayError
from app.adapters.metrics import MemoryStats
from app.adapters.model_sources import LocalDirSource, ModelCatalog
from app.db.session import build_engine, init_db
from app.domain.instance import GatewayState, InstanceStatus
from app.profiles import load_profile
from app.services.error_classifier import ErrorClassifier
from app.services.instance_manager import ConflictError, InstanceManager
from app.services.planner import PlanInput, Planner
from app.services.presets import PresetResolver
from tests.conftest import QWEN_CONFIG, REPO_ROOT, make_model
from tests.fakes import FakeGateway, FakeProbe, FakeRuntime

GB = 2**30
MODEL_ID = "local:Qwen2.5-0.5B-Instruct"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    e = build_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    init_db(e)
    yield e
    e.dispose()


class Env:
    def __init__(self, tmp_path: Path, engine: Engine, boot: str = "100") -> None:
        models = tmp_path / "models"
        if not models.exists():
            make_model(models, "Qwen2.5-0.5B-Instruct", QWEN_CONFIG)
        profile = load_profile(REPO_ROOT / "configs", "spark")
        profile.timeouts.health_s = 2
        self.runtime = FakeRuntime()
        self.gateway = FakeGateway()
        self.probe = FakeProbe()
        self.boot = boot
        mem = MemoryStats(
            total_bytes=120 * GB,
            available_bytes=110 * GB,
            free_bytes=100 * GB,
            cached_bytes=10 * GB,
            swap_total_bytes=0,
            swap_free_bytes=0,
        )
        self.mgr = InstanceManager(
            engine=engine,
            profile=profile,
            runtime=self.runtime,
            gateway=self.gateway,
            catalog=ModelCatalog([LocalDirSource("local", models, "/data/models")]),
            planner=Planner(profile, PresetResolver.from_file(REPO_ROOT / "configs" / "presets.yaml", profile)),
            classifier=ErrorClassifier.from_file(REPO_ROOT / "configs" / "error-patterns.yaml"),
            probe=self.probe,
            memory=lambda: mem,
            container_prefix="dgxsp-vllm-",
            poll_interval=0.01,
            boot_time=lambda: self.boot,
        )

    def create(self, **kw: object) -> str:
        plan = self.mgr.plan(PlanInput(model_id=MODEL_ID, **kw))  # type: ignore[arg-type]
        return self.mgr.create(plan).id


@pytest.fixture
def env(tmp_path: Path, engine: Engine) -> Env:
    return Env(tmp_path, engine)


async def test_full_lifecycle(env: Env) -> None:
    iid = env.create()
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.CREATED
    assert inst.served_model_name == "qwen2.5-0.5b-instruct"

    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.READY
    assert inst.gateway_state == GatewayState.REGISTERED
    assert inst.phase == "ready"

    spec = env.runtime.runs[0]
    assert spec.command[:3] == ["vllm", "serve", "/models"]
    assert spec.host_model_path == "/data/models/Qwen2.5-0.5B-Instruct"
    assert "--served-model-name" in spec.command

    reg = next(iter(env.gateway.models.values()))
    assert reg["litellm_params"]["api_base"] == f"http://dgxsp-vllm-{iid}:8000/v1"

    result = await env.mgr.test(iid, "hi")
    assert result.ok and result.reply_preview == "echo: hi"

    await env.mgr.stop(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.STOPPED
    assert env.gateway.models == {}

    types = [e.type for e in env.mgr.events(iid)]
    assert {
        "created",
        "start_requested",
        "container_started",
        "model_loaded",
        "gateway_registered",
        "stopped",
        "gateway_removed",
    } <= set(types)

    await env.mgr.delete(iid)
    assert env.mgr.all() == []
    assert env.runtime.containers == {}


async def test_loads_are_serialized(env: Env) -> None:
    env.probe.ready_after = 5
    a = env.create(served_model_name="first", params={"gpu_memory_utilization": 0.2})
    b = env.create(served_model_name="second", params={"gpu_memory_utilization": 0.2})
    await env.mgr.start(a)
    await asyncio.sleep(0.02)
    await env.mgr.start(b)
    await asyncio.sleep(0.02)
    assert env.mgr.get(a).status == InstanceStatus.LOADING
    second = env.mgr.get(b)
    assert second.status == InstanceStatus.STARTING
    assert second.phase == "queued"
    assert [s.name for s in env.runtime.runs] == [f"dgxsp-vllm-{a}"]
    await env.mgr.wait_idle(a)
    await env.mgr.wait_idle(b)
    assert env.mgr.get(b).status == InstanceStatus.READY
    assert [s.name for s in env.runtime.runs] == [f"dgxsp-vllm-{a}", f"dgxsp-vllm-{b}"]
    assert "queued" in [e.type for e in env.mgr.events(b)]


async def test_cancel_while_queued(env: Env) -> None:
    env.probe.ready_after = 10**9
    a = env.create(served_model_name="first", params={"gpu_memory_utilization": 0.2})
    b = env.create(served_model_name="second", params={"gpu_memory_utilization": 0.2})
    await env.mgr.start(a)
    await asyncio.sleep(0.02)
    await env.mgr.start(b)
    await asyncio.sleep(0.02)
    await env.mgr.cancel(b)
    assert env.mgr.get(b).status == InstanceStatus.STOPPED
    assert len(env.runtime.runs) == 1
    await env.mgr.cancel(a)


async def test_restart(env: Env) -> None:
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    await env.mgr.restart(iid)
    await env.mgr.wait_idle(iid)
    assert env.mgr.get(iid).status == InstanceStatus.READY
    assert len(env.gateway.models) == 1


async def test_invalid_transitions(env: Env) -> None:
    iid = env.create()
    with pytest.raises(ConflictError):
        await env.mgr.stop(iid)
    await env.mgr.start(iid)
    with pytest.raises(ConflictError):
        await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    with pytest.raises(ConflictError):
        await env.mgr.delete(iid)


async def test_oom_failure_classified(env: Env) -> None:
    env.runtime.fail_with = (
        1,
        False,
        [
            "ERROR torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB",
            "RuntimeError: Engine core initialization failed. See root cause above.",
        ],
    )
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.ERROR
    assert inst.last_error is not None
    assert inst.last_error["code"] == "OOM"
    assert any("out of memory" in e for e in inst.last_error["evidence"])
    assert inst.last_error["suggestions"][0]["patch"] == {"max_model_len": 8192}
    assert env.gateway.models == {}

    env.runtime.fail_with = None
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    assert env.mgr.get(iid).status == InstanceStatus.READY
    assert env.mgr.get(iid).last_error is None


async def test_unknown_failure_is_crashed(env: Env) -> None:
    env.runtime.fail_with = (1, False, ["RuntimeError: Engine core initialization failed. See root cause above."])
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    assert env.mgr.get(iid).last_error["code"] == "CRASHED"  # type: ignore[index]


async def test_health_timeout(env: Env) -> None:
    env.probe.ready_after = 10**9
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.ERROR
    assert inst.last_error["code"] == "HEALTH_TIMEOUT"  # type: ignore[index]


async def test_cancel_during_loading(env: Env) -> None:
    env.probe.ready_after = 10**9
    iid = env.create()
    await env.mgr.start(iid)
    await asyncio.sleep(0.05)
    assert env.mgr.get(iid).status == InstanceStatus.LOADING
    await env.mgr.cancel(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.STOPPED
    assert env.runtime.containers[f"dgxsp-vllm-{iid}"].status == "exited"


async def test_cancel_before_container_created(env: Env) -> None:
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.cancel(iid)
    assert env.mgr.get(iid).status == InstanceStatus.STOPPED
    for c in env.runtime.containers.values():
        assert c.status == "exited"


async def test_run_error_image_missing(env: Env) -> None:
    env.runtime.run_error = Exception("404 Client Error: No such image: eugr/spark-vllm")
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    assert env.mgr.get(iid).last_error["code"] == "IMAGE_UNAVAILABLE"  # type: ignore[index]


async def test_gateway_failure_then_retry(env: Env) -> None:
    env.gateway.register_error = GatewayError("connection refused")
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.READY
    assert inst.gateway_state == GatewayState.FAILED
    assert inst.last_error["code"] == "GATEWAY_UNREACHABLE"  # type: ignore[index]

    env.gateway.register_error = None
    inst = await env.mgr.retry_gateway(iid)
    assert inst.gateway_state == GatewayState.REGISTERED
    assert inst.last_error is None


async def test_reconcile_container_removed_externally(env: Env) -> None:
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    env.runtime.containers.clear()
    stats = await env.mgr.reconcile_once()
    inst = env.mgr.get(iid)
    assert stats["marked_error"] == 1
    assert inst.status == InstanceStatus.ERROR
    assert inst.last_error["code"] == "CONTAINER_MISSING"  # type: ignore[index]
    assert env.gateway.models == {}


async def test_reconcile_removes_orphans_and_reregisters(env: Env) -> None:
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    await env.gateway.register_model(served_model_name="ghost", api_base="x", instance_id="nope")
    mid = env.mgr.get(iid).gateway_model_id
    assert mid
    await env.gateway.delete_model(mid)

    stats = await env.mgr.reconcile_once()
    names = [m["model_name"] for m in env.gateway.models.values()]
    assert names == [env.mgr.get(iid).served_model_name]
    assert stats["gateway_removed"] == 1
    assert stats["gateway_registered"] == 1


async def test_test_key_regenerated_when_revoked(env: Env) -> None:
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    assert (await env.mgr.test(iid)).ok
    env.gateway.keys.clear()
    assert (await env.mgr.test(iid)).ok


async def test_recover_after_reboot_and_autostart(tmp_path: Path, engine: Engine) -> None:
    env = Env(tmp_path, engine, boot="100")
    await env.mgr.recover()
    a = env.create(
        served_model_name="auto-a", autostart=True, autostart_order=2, params={"gpu_memory_utilization": 0.3}
    )
    b = env.create(
        served_model_name="auto-b", autostart=True, autostart_order=1, params={"gpu_memory_utilization": 0.3}
    )
    c = env.create(served_model_name="manual-c", params={"gpu_memory_utilization": 0.2})
    for iid in (a, b, c):
        await env.mgr.start(iid)
        await env.mgr.wait_idle(iid)

    rebooted = Env(tmp_path, engine, boot="200")
    assert await rebooted.mgr.recover() is True
    for iid in (a, b, c):
        assert rebooted.mgr.get(iid).status == InstanceStatus.STOPPED
    assert "host_restarted" in [e.type for e in rebooted.mgr.events(a)]

    progress = rebooted.mgr.start_autostart()
    assert progress.queue == [b, a]
    assert rebooted.mgr._autostart_task is not None
    await rebooted.mgr._autostart_task
    assert rebooted.mgr.autostart.state == "done"
    assert rebooted.mgr.autostart.results == {b: "ready", a: "ready"}
    assert rebooted.mgr.get(c).status == InstanceStatus.STOPPED
    starts = [s.name for s in rebooted.runtime.runs]
    assert starts == [f"dgxsp-vllm-{b}", f"dgxsp-vllm-{a}"]


async def test_platform_restart_keeps_running_containers(tmp_path: Path, engine: Engine) -> None:
    env = Env(tmp_path, engine, boot="100")
    await env.mgr.recover()
    iid = env.create()
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)

    again = Env(tmp_path, engine, boot="100")
    again.runtime = env.runtime
    again.mgr.runtime = env.runtime
    assert await again.mgr.recover() is False
    assert again.mgr.get(iid).status == InstanceStatus.READY
