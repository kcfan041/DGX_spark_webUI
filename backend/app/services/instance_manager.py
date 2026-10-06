import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, col, delete, select

from app.adapters.docker_runtime import ContainerSpec
from app.adapters.litellm_client import INSTANCE_FIELD, GatewayError
from app.adapters.metrics import MemoryStats
from app.adapters.model_sources import ModelCatalog, ModelMeta
from app.db.models import Instance, InstanceEvent, SystemSetting
from app.domain.errors import ErrorCode, InstanceError
from app.domain.instance import ACTIVE_STATUSES, GatewayState, InstancePhase, InstanceStatus
from app.domain.params import InstanceParams, build_command
from app.profiles import RuntimeProfile
from app.services.error_classifier import ErrorClassifier, make_error, tailor_suggestions
from app.services.planner import Plan, PlanInput, Planner
from app.services.ports import GatewayPort, RuntimePort
from app.services.probe import Probe

log = logging.getLogger(__name__)

STARTABLE = {InstanceStatus.CREATED, InstanceStatus.STOPPED, InstanceStatus.ERROR}
STOPPABLE = {InstanceStatus.STARTING, InstanceStatus.LOADING, InstanceStatus.READY, InstanceStatus.ERROR}
DELETABLE = {InstanceStatus.CREATED, InstanceStatus.STOPPED, InstanceStatus.ERROR}
TEST_KEY_SETTING = "system_test_key"
BOOT_SETTING = "last_boot_time"


class ConflictError(Exception):
    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.params = params or {}


class NotFoundError(Exception):
    pass


class AutostartProgress(BaseModel):
    state: str = "idle"
    queue: list[str] = Field(default_factory=list)
    current: str | None = None
    results: dict[str, str] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TestResult(BaseModel):
    ok: bool
    latency_ms: int | None = None
    reply_preview: str | None = None
    error: str | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)


def read_boot_time(path: str = "/proc/stat") -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("btime "):
                    return line.split()[1]
    except OSError:
        return None
    return None


class InstanceManager:
    def __init__(
        self,
        *,
        engine: Engine,
        profile: RuntimeProfile,
        runtime: RuntimePort,
        gateway: GatewayPort,
        catalog: ModelCatalog,
        planner: Planner,
        classifier: ErrorClassifier,
        probe: Probe,
        memory: Callable[[], MemoryStats | None],
        container_prefix: str,
        poll_interval: float = 3.0,
        reconcile_interval: float = 10.0,
        boot_time: Callable[[], str | None] = read_boot_time,
    ) -> None:
        self.engine = engine
        self.profile = profile
        self.runtime = runtime
        self.gateway = gateway
        self.catalog = catalog
        self.planner = planner
        self.classifier = classifier
        self.probe = probe
        self.memory = memory
        self.prefix = container_prefix
        self.poll_interval = poll_interval
        self.reconcile_interval = reconcile_interval
        self.boot_time = boot_time
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._background: list[asyncio.Task[None]] = []
        self._autostart_task: asyncio.Task[None] | None = None
        self.autostart = AutostartProgress()
        # vLLM sizes its memory reservation from free memory at startup; loading two models at the same
        # time makes both see stale free memory (measured on Spark: 0.5B failed while 7B was loading).
        self._load_gate = asyncio.Lock()

    # ------------------------------------------------------------------ helpers

    def _lock(self, instance_id: str) -> asyncio.Lock:
        return self._locks.setdefault(instance_id, asyncio.Lock())

    def get(self, instance_id: str) -> Instance:
        with Session(self.engine) as s:
            inst = s.get(Instance, instance_id)
            if inst is None:
                raise NotFoundError(instance_id)
            s.expunge(inst)
            return inst

    def all(self) -> list[Instance]:
        with Session(self.engine) as s:
            rows = list(s.exec(select(Instance).order_by(col(Instance.created_at))).all())
            for r in rows:
                s.expunge(r)
            return rows

    def _update(self, instance_id: str, **fields: Any) -> Instance:
        with Session(self.engine) as s:
            inst = s.get(Instance, instance_id)
            if inst is None:
                raise NotFoundError(instance_id)
            for k, v in fields.items():
                setattr(inst, k, v)
            inst.updated_at = utcnow()
            s.add(inst)
            s.commit()
            s.refresh(inst)
            s.expunge(inst)
            return inst

    def event(self, instance_id: str, type_: str, **data: Any) -> None:
        with Session(self.engine) as s:
            s.add(InstanceEvent(instance_id=instance_id, type=type_, data=data))
            s.commit()

    def events(self, instance_id: str, limit: int = 200) -> list[InstanceEvent]:
        with Session(self.engine) as s:
            q = (
                select(InstanceEvent)
                .where(InstanceEvent.instance_id == instance_id)
                .order_by(col(InstanceEvent.id).desc())
                .limit(limit)
            )
            rows = list(s.exec(q).all())
            for r in rows:
                s.expunge(r)
            return rows

    def _get_setting(self, key: str) -> str | None:
        with Session(self.engine) as s:
            row = s.get(SystemSetting, key)
            return row.value if row else None

    def _set_setting(self, key: str, value: str) -> None:
        with Session(self.engine) as s:
            row = s.get(SystemSetting, key) or SystemSetting(key=key, value=value)
            row.value = value
            row.updated_at = utcnow()
            s.add(row)
            s.commit()

    def container_name(self, inst: Instance) -> str:
        return f"{self.prefix}{inst.id}"

    def internal_base(self, inst: Instance) -> str:
        return f"http://{self.container_name(inst)}:{self.profile.vllm.port}"

    def _set_error(self, instance_id: str, err: InstanceError, status: InstanceStatus = InstanceStatus.ERROR) -> None:
        self._update(instance_id, status=status, phase=None, last_error=err.model_dump(mode="json"))
        self.event(instance_id, "error", code=err.code.value, evidence=err.evidence[-3:])

    # ------------------------------------------------------------------ planning / CRUD

    def plan(self, inp: PlanInput, exclude_id: str | None = None) -> Plan:
        model = self.catalog.get(inp.model_id)
        return self.planner.plan(inp, model, self.all(), self.memory(), exclude_id=exclude_id)

    def create(self, plan: Plan) -> Instance:
        if plan.blocking:
            raise ConflictError("PLAN_BLOCKED", {"warnings": [w.model_dump() for w in plan.warnings]})
        inst = Instance(
            display_name=plan.display_name,
            served_model_name=plan.served_model_name,
            model_id=plan.model_id,
            preset=plan.preset,
            params=plan.params.model_dump(),
            autostart=plan.autostart,
            autostart_order=plan.autostart_order,
        )
        with Session(self.engine) as s:
            s.add(inst)
            s.commit()
            s.refresh(inst)
            s.expunge(inst)
        self.event(inst.id, "created", preset=plan.preset)
        return inst

    def update(self, instance_id: str, plan: Plan) -> tuple[Instance, bool]:
        current = self.get(instance_id)
        if plan.blocking:
            raise ConflictError("PLAN_BLOCKED", {"warnings": [w.model_dump() for w in plan.warnings]})
        restart_required = current.status in ACTIVE_STATUSES and (
            plan.params.model_dump() != current.params
            or plan.served_model_name != current.served_model_name
            or plan.model_id != current.model_id
        )
        inst = self._update(
            instance_id,
            display_name=plan.display_name,
            served_model_name=plan.served_model_name,
            model_id=plan.model_id,
            preset=plan.preset,
            params=plan.params.model_dump(),
            autostart=plan.autostart,
            autostart_order=plan.autostart_order,
        )
        self.event(instance_id, "updated", restart_required=restart_required)
        return inst, restart_required

    async def delete(self, instance_id: str) -> None:
        async with self._lock(instance_id):
            inst = self.get(instance_id)
            if inst.status not in DELETABLE:
                raise ConflictError("INSTANCE_RUNNING", {"status": inst.status})
            await self._deregister(inst)
            await asyncio.to_thread(self.runtime.remove, self.container_name(inst))
            with Session(self.engine) as s:
                s.execute(delete(InstanceEvent).where(col(InstanceEvent.instance_id) == instance_id))
                row = s.get(Instance, instance_id)
                if row:
                    s.delete(row)
                s.commit()
        self._locks.pop(instance_id, None)

    # ------------------------------------------------------------------ lifecycle

    async def start(self, instance_id: str, reason: str = "manual") -> Instance:
        async with self._lock(instance_id):
            inst = self.get(instance_id)
            if inst.status not in STARTABLE:
                raise ConflictError("INVALID_STATE", {"status": inst.status, "action": "start"})
            inst = self._update(
                instance_id,
                status=InstanceStatus.STARTING,
                phase=InstancePhase.PREPARING.value,
                phase_started_at=utcnow(),
                last_error=None,
                gateway_state=GatewayState.NONE,
            )
            self.event(instance_id, "start_requested", reason=reason)
            self._spawn(instance_id, self._run_start(instance_id))
            return inst

    async def stop(self, instance_id: str, reason: str = "manual") -> Instance:
        async with self._lock(instance_id):
            inst = self.get(instance_id)
            if inst.status not in STOPPABLE:
                raise ConflictError("INVALID_STATE", {"status": inst.status, "action": "stop"})
            await self._cancel_task(instance_id)
            self._update(instance_id, status=InstanceStatus.STOPPING)
            await self._deregister(inst)
            await asyncio.to_thread(self.runtime.stop, self.container_name(inst), self.profile.timeouts.stop_s)
            inst = self._update(
                instance_id,
                status=InstanceStatus.STOPPED,
                phase=None,
                phase_started_at=None,
                gateway_state=GatewayState.NONE,
                gateway_model_id=None,
                last_error=None,
            )
            self.event(instance_id, "stopped", reason=reason)
            return inst

    async def restart(self, instance_id: str) -> Instance:
        inst = self.get(instance_id)
        if inst.status in STOPPABLE:
            await self.stop(instance_id, reason="restart")
        return await self.start(instance_id, reason="restart")

    async def cancel(self, instance_id: str) -> Instance:
        inst = self.get(instance_id)
        if inst.status not in {InstanceStatus.STARTING, InstanceStatus.LOADING}:
            raise ConflictError("INVALID_STATE", {"status": inst.status, "action": "cancel"})
        return await self.stop(instance_id, reason="cancel")

    def _spawn(self, instance_id: str, coro: Any) -> None:
        task = asyncio.create_task(coro, name=f"instance-{instance_id}")
        self._tasks[instance_id] = task
        task.add_done_callback(
            lambda t: self._tasks.pop(instance_id, None) if self._tasks.get(instance_id) is t else None
        )

    async def _cancel_task(self, instance_id: str) -> None:
        task = self._tasks.pop(instance_id, None)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def wait_idle(self, instance_id: str) -> None:
        task = self._tasks.get(instance_id)
        if task:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run_start(self, instance_id: str) -> None:
        try:
            inst = self.get(instance_id)
            model = self.catalog.get(inst.model_id)
            if model is None:
                self._set_error(instance_id, make_error(ErrorCode.MODEL_NOT_FOUND, params={"model_id": inst.model_id}))
                return
            params = InstanceParams(**inst.params)
            name = self.container_name(inst)
            if self._load_gate.locked():
                self._update(instance_id, phase=InstancePhase.QUEUED.value, phase_started_at=utcnow())
                self.event(instance_id, "queued")
            async with self._load_gate:
                loaded = await self._create_and_wait(instance_id, inst, model, params, name)
            if loaded:
                await self._mark_ready_and_register(instance_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("start failed for %s", instance_id)
            self._set_error(instance_id, make_error(ErrorCode.UNKNOWN, evidence=[repr(e)[:500]]))

    async def _create_and_wait(
        self, instance_id: str, inst: Instance, model: ModelMeta, params: InstanceParams, name: str
    ) -> bool:
        if self.get(instance_id).phase == InstancePhase.QUEUED.value:
            self._update(instance_id, phase=InstancePhase.PREPARING.value, phase_started_at=utcnow())
        spec = ContainerSpec(
            name=name,
            instance_id=inst.id,
            served_model_name=inst.served_model_name,
            command=build_command(self.profile, model, inst.served_model_name, params),
            host_model_path=model.mount_host_path,
            container_model_path=self.profile.vllm.model_mount,
            host_port=params.host_port,
        )
        self._update(instance_id, phase=InstancePhase.CREATING.value)
        run_fut = asyncio.ensure_future(asyncio.to_thread(self.runtime.run, spec))
        try:
            container_id = await asyncio.shield(run_fut)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await run_fut
            await asyncio.to_thread(self.runtime.stop, name, self.profile.timeouts.stop_s)
            raise
        except Exception as e:
            code = self._classify_run_error(str(e))
            self._set_error(instance_id, make_error(code, evidence=[str(e)[:500]]))
            return False
        self._update(
            instance_id,
            status=InstanceStatus.LOADING,
            phase=InstancePhase.LOADING.value,
            container_id=container_id,
            container_name=name,
        )
        self.event(instance_id, "container_started", container=name)
        return await self._wait_loaded(instance_id, name)

    @staticmethod
    def _classify_run_error(msg: str) -> ErrorCode:
        low = msg.lower()
        rules = [
            (ErrorCode.PORT_CONFLICT, ("port is already allocated", "address already in use")),
            (ErrorCode.IMAGE_UNAVAILABLE, ("no such image", "pull access denied", "manifest unknown")),
            (ErrorCode.GPU_UNAVAILABLE, ("could not select device driver", "nvidia-container-cli")),
            (ErrorCode.DOCKER_UNAVAILABLE, ("connection refused", "connection aborted", "error while fetching server")),
        ]
        for code, needles in rules:
            if any(n in low for n in needles):
                return code
        return ErrorCode.UNKNOWN

    async def _wait_ready(self, instance_id: str, name: str) -> None:
        if await self._wait_loaded(instance_id, name):
            await self._mark_ready_and_register(instance_id)

    async def _wait_loaded(self, instance_id: str, name: str) -> bool:
        inst = self.get(instance_id)
        deadline = time.monotonic() + self.profile.timeouts.health_s
        base = self.internal_base(inst)
        while True:
            st = await asyncio.to_thread(self.runtime.state, name)
            if st is None:
                self._set_error(instance_id, make_error(ErrorCode.CONTAINER_MISSING))
                return False
            if st.status in ("exited", "dead"):
                await self._fail_from_container(instance_id, name, st.exit_code, st.oom_killed)
                return False
            if await self.probe.ready(base, inst.served_model_name):
                return True
            if time.monotonic() > deadline:
                logs = await asyncio.to_thread(self.runtime.logs, name, 300)
                await asyncio.to_thread(self.runtime.stop, name, self.profile.timeouts.stop_s)
                err = make_error(
                    ErrorCode.HEALTH_TIMEOUT, evidence=logs[-5:], params={"timeout_s": self.profile.timeouts.health_s}
                )
                self._set_error(instance_id, err)
                return False
            await asyncio.sleep(self.poll_interval)

    async def _mark_ready_and_register(self, instance_id: str) -> None:
        inst = self.get(instance_id)
        loaded_s = round((utcnow() - (inst.phase_started_at or utcnow()).replace(tzinfo=UTC)).total_seconds(), 1)
        self.event(instance_id, "model_loaded", seconds=loaded_s)
        self._update(
            instance_id,
            status=InstanceStatus.READY,
            phase=InstancePhase.REGISTERING.value,
            gateway_state=GatewayState.PENDING,
        )
        await self._register(instance_id)

    async def _fail_from_container(self, instance_id: str, name: str, exit_code: int | None, oom: bool) -> None:
        logs = await asyncio.to_thread(self.runtime.logs, name, 2000)
        err = self.classifier.classify(exit_code=exit_code, oom_killed=oom, logs=logs)
        inst = self.get(instance_id)
        model = self.catalog.get(inst.model_id)
        mem = self.memory()
        if mem and "total_gib" not in err.params:
            err.params["total_gib"] = f"{mem.total_bytes / 2**30:.2f}"
        err = tailor_suggestions(err, inst.params, model.max_context if model else None)
        await self._deregister(inst)
        self._set_error(instance_id, err)

    async def _register(self, instance_id: str) -> bool:
        inst = self.get(instance_id)
        try:
            model_id = await self.gateway.register_model(
                served_model_name=inst.served_model_name,
                api_base=f"{self.internal_base(inst)}/v1",
                instance_id=inst.id,
            )
        except GatewayError as e:
            code = ErrorCode.GATEWAY_REGISTER_FAILED if e.status_code else ErrorCode.GATEWAY_UNREACHABLE
            err = make_error(code, evidence=[str(e)[:500]], severity="warning")
            was_failed = inst.gateway_state == GatewayState.FAILED
            self._update(
                instance_id,
                phase=InstancePhase.READY.value,
                gateway_state=GatewayState.FAILED,
                phase_started_at=inst.phase_started_at if was_failed else utcnow(),
                last_error=err.model_dump(mode="json"),
            )
            if not was_failed:
                self.event(instance_id, "gateway_failed", code=code.value)
            return False
        self._update(
            instance_id,
            phase=InstancePhase.READY.value,
            phase_started_at=utcnow(),
            gateway_state=GatewayState.REGISTERED,
            gateway_model_id=model_id,
            last_error=None,
        )
        self.event(instance_id, "gateway_registered", model_id=model_id)
        return True

    async def retry_gateway(self, instance_id: str) -> Instance:
        inst = self.get(instance_id)
        if inst.status != InstanceStatus.READY:
            raise ConflictError("INVALID_STATE", {"status": inst.status, "action": "gateway_retry"})
        await self._deregister(inst)
        await self._register(instance_id)
        return self.get(instance_id)

    async def _deregister(self, inst: Instance) -> None:
        ids = {inst.gateway_model_id} if inst.gateway_model_id else set()
        try:
            for m in await self.gateway.list_managed_models():
                info = m.get("model_info") or {}
                if info.get(INSTANCE_FIELD) == inst.id and info.get("id"):
                    ids.add(info["id"])
        except GatewayError:
            pass
        for mid in ids:
            try:
                await self.gateway.delete_model(mid)
                self.event(inst.id, "gateway_removed", model_id=mid)
            except GatewayError as e:
                log.warning("gateway delete failed for %s: %s", mid, e)

    # ------------------------------------------------------------------ test / logs

    async def _test_key(self, regenerate: bool = False) -> str:
        key = None if regenerate else self._get_setting(TEST_KEY_SETTING)
        if key:
            return key
        resp = await self.gateway.generate_key(
            f"dgxsp-system-test-{secrets.token_hex(4)}", {"created_by": "dgxsp", "purpose": "system-test"}
        )
        key = str(resp["key"])
        self._set_setting(TEST_KEY_SETTING, key)
        return key

    async def test(self, instance_id: str, content: str = "你好，請用一句話自我介紹。") -> TestResult:
        inst = self.get(instance_id)
        if inst.status != InstanceStatus.READY or inst.gateway_state != GatewayState.REGISTERED:
            raise ConflictError("INVALID_STATE", {"status": inst.status, "action": "test"})
        for attempt in range(2):
            key = await self._test_key(regenerate=attempt > 0)
            t0 = time.monotonic()
            try:
                resp = await self.gateway.chat(api_key=key, model=inst.served_model_name, content=content)
            except GatewayError as e:
                if e.status_code == 401 and attempt == 0:
                    continue
                code = (
                    ErrorCode.GATEWAY_MODEL_NOT_FOUND
                    if e.status_code in (400, 404)
                    else ErrorCode.TEST_TIMEOUT
                    if e.status_code is None and "timeout" in str(e).lower()
                    else ErrorCode.GATEWAY_UNREACHABLE
                    if e.status_code is None
                    else ErrorCode.UNKNOWN
                )
                self.event(instance_id, "test_failed", code=code.value)
                return TestResult(ok=False, error=code.value)
            latency = int((time.monotonic() - t0) * 1000)
            choices = resp.get("choices") or [{}]
            reply = ((choices[0].get("message") or {}).get("content") or "")[:300]
            self.event(instance_id, "test_ok", latency_ms=latency)
            return TestResult(ok=True, latency_ms=latency, reply_preview=reply)
        return TestResult(ok=False, error=ErrorCode.UNKNOWN.value)

    def logs(self, instance_id: str, tail: int = 500) -> list[str]:
        inst = self.get(instance_id)
        return self.runtime.logs(self.container_name(inst), tail)

    # ------------------------------------------------------------------ reconcile / recovery

    async def reconcile_once(self) -> dict[str, int]:
        stats = {"marked_error": 0, "gateway_removed": 0, "gateway_registered": 0}
        instances = self.all()
        for inst in instances:
            if inst.id in self._tasks or inst.status not in ACTIVE_STATUSES:
                continue
            async with self._lock(inst.id):
                inst = self.get(inst.id)
                if inst.id in self._tasks or inst.status not in ACTIVE_STATUSES:
                    continue
                st = await asyncio.to_thread(self.runtime.state, self.container_name(inst))
                if st is None:
                    await self._deregister(inst)
                    self._set_error(inst.id, make_error(ErrorCode.CONTAINER_MISSING))
                    self._update(inst.id, gateway_state=GatewayState.NONE, gateway_model_id=None)
                    stats["marked_error"] += 1
                elif st.status in ("exited", "dead"):
                    await self._fail_from_container(inst.id, self.container_name(inst), st.exit_code, st.oom_killed)
                    self._update(inst.id, gateway_state=GatewayState.NONE, gateway_model_id=None)
                    stats["marked_error"] += 1
                elif inst.status == InstanceStatus.READY and inst.gateway_state != GatewayState.REGISTERED:
                    if await self._register(inst.id):
                        stats["gateway_registered"] += 1

        try:
            managed = await self.gateway.list_managed_models()
        except GatewayError:
            return stats
        by_id = {i.id: i for i in self.all()}
        seen: set[str] = set()
        for m in managed:
            info = m.get("model_info") or {}
            mid, iid = info.get("id"), info.get(INSTANCE_FIELD)
            if iid in self._tasks:
                continue
            owner = by_id.get(iid) if iid else None
            if (
                owner is not None
                and owner.status == InstanceStatus.READY
                and owner.gateway_model_id == mid
                and m.get("model_name") == owner.served_model_name
            ):
                seen.add(owner.id)
                continue
            if mid:
                with contextlib.suppress(GatewayError):
                    await self.gateway.delete_model(mid)
                    stats["gateway_removed"] += 1
        for inst in by_id.values():
            if (
                inst.status == InstanceStatus.READY
                and inst.gateway_state == GatewayState.REGISTERED
                and inst.id not in seen
                and inst.id not in self._tasks
            ):
                self._update(inst.id, gateway_state=GatewayState.PENDING, gateway_model_id=None)
                if await self._register(inst.id):
                    stats["gateway_registered"] += 1
        return stats

    async def recover(self) -> bool:
        boot = self.boot_time()
        last_boot = self._get_setting(BOOT_SETTING)
        host_rebooted = boot is not None and last_boot is not None and boot != last_boot
        if boot is not None:
            self._set_setting(BOOT_SETTING, boot)

        for inst in self.all():
            if inst.status == InstanceStatus.STOPPING:
                self._update(inst.id, status=InstanceStatus.STOPPED, phase=None)
                continue
            if inst.status not in ACTIVE_STATUSES:
                continue
            st = await asyncio.to_thread(self.runtime.state, self.container_name(inst))
            if st is None or st.status in ("exited", "dead", "created"):
                await self._deregister(inst)
                self._update(
                    inst.id,
                    status=InstanceStatus.STOPPED,
                    phase=None,
                    phase_started_at=None,
                    gateway_state=GatewayState.NONE,
                    gateway_model_id=None,
                )
                self.event(inst.id, "host_restarted" if host_rebooted else "platform_restarted")
            elif inst.status in (InstanceStatus.STARTING, InstanceStatus.LOADING):
                self._update(inst.id, status=InstanceStatus.LOADING, phase=InstancePhase.LOADING.value)
                self._spawn(inst.id, self._resume_wait(inst.id))
        return host_rebooted

    async def _resume_wait(self, instance_id: str) -> None:
        try:
            await self._wait_ready(instance_id, self.container_name(self.get(instance_id)))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("resume failed for %s", instance_id)
            self._set_error(instance_id, make_error(ErrorCode.UNKNOWN, evidence=[repr(e)[:500]]))

    # ------------------------------------------------------------------ autostart

    def start_autostart(self) -> AutostartProgress:
        if self._autostart_task and not self._autostart_task.done():
            return self.autostart
        candidates = sorted(
            (i for i in self.all() if i.autostart and i.status in STARTABLE),
            key=lambda i: (i.autostart_order, i.created_at),
        )
        self.autostart = AutostartProgress(
            state="running" if candidates else "done",
            queue=[i.id for i in candidates],
            started_at=utcnow(),
            finished_at=None if candidates else utcnow(),
        )
        for i in candidates:
            self.event(i.id, "autostart_queued")
        if candidates:
            self._autostart_task = asyncio.create_task(self._run_autostart(), name="autostart")
        return self.autostart

    async def cancel_autostart(self) -> AutostartProgress:
        if self._autostart_task and not self._autostart_task.done():
            self._autostart_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._autostart_task
        if self.autostart.state == "running":
            for iid in self.autostart.queue:
                self.autostart.results.setdefault(iid, "cancelled")
            self.autostart.state = "cancelled"
            self.autostart.current = None
            self.autostart.finished_at = utcnow()
        return self.autostart

    async def _run_autostart(self) -> None:
        for iid in list(self.autostart.queue):
            self.autostart.current = iid
            try:
                inst = self.get(iid)
            except NotFoundError:
                self.autostart.results[iid] = "missing"
                continue
            if inst.status not in STARTABLE:
                self.autostart.results[iid] = "skipped"
                continue
            plan = self.plan(
                PlanInput(
                    model_id=inst.model_id,
                    preset=inst.preset,
                    params=inst.params,
                    display_name=inst.display_name,
                    served_model_name=inst.served_model_name,
                ),
                exclude_id=iid,
            )
            if plan.blocking:
                err = make_error(
                    ErrorCode.AUTOSTART_SKIPPED_MEMORY,
                    params={"warnings": [w.code for w in plan.warnings if w.level == "blocking"]},
                )
                self._set_error(iid, err)
                self.autostart.results[iid] = "skipped"
                continue
            try:
                await self.start(iid, reason="autostart")
            except ConflictError:
                self.autostart.results[iid] = "skipped"
                continue
            await self.wait_idle(iid)
            final = self.get(iid)
            self.autostart.results[iid] = "ready" if final.status == InstanceStatus.READY else "error"
            self.event(iid, "autostart_" + self.autostart.results[iid])
        self.autostart.current = None
        self.autostart.state = "done"
        self.autostart.finished_at = utcnow()

    # ------------------------------------------------------------------ background loop

    async def startup(self) -> None:
        try:
            rebooted = await self.recover()
        except Exception:
            log.exception("recovery failed")
            rebooted = False
        if rebooted:
            self.start_autostart()
        self._background.append(asyncio.create_task(self._reconcile_loop(), name="reconcile"))

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(self.reconcile_interval)
            try:
                await self.reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("reconcile failed")

    async def shutdown(self) -> None:
        tasks = [*self._background, *self._tasks.values()]
        if self._autostart_task:
            tasks.append(self._autostart_task)
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
