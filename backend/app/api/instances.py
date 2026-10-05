import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.adapters.model_sources import ModelMeta
from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.db.models import Instance, InstanceEvent
from app.domain.instance import GatewayState, InstanceStatus
from app.domain.params import InstanceParams, ParamField, build_command, param_schema
from app.services.instance_manager import AutostartProgress, ConflictError, NotFoundError, TestResult
from app.services.planner import Plan, PlanInput, PlanningError
from app.services.presets import ResolvedPreset

router = APIRouter(tags=["instances"])
log = logging.getLogger(__name__)


class Endpoint(BaseModel):
    api_base: str
    model: str


class Diagnostics(BaseModel):
    container_name: str | None
    container_id: str | None
    internal_url: str
    image: str
    gateway_model_id: str | None
    command: list[str] | None


class InstanceOut(BaseModel):
    id: str
    display_name: str
    served_model_name: str
    model_id: str
    preset: str
    params: dict[str, Any]
    autostart: bool
    autostart_order: int
    status: InstanceStatus
    phase: str | None
    phase_started_at: datetime | None
    last_error: dict[str, Any] | None
    gateway_state: GatewayState
    created_at: datetime
    updated_at: datetime
    endpoint: Endpoint
    diagnostics: Diagnostics | None = None


class CreateRequest(PlanInput):
    start: bool = True


class UpdateRequest(BaseModel):
    model_id: str | None = None
    preset: str | None = None
    params: dict[str, Any] | None = None
    display_name: str | None = None
    served_model_name: str | None = None
    autostart: bool | None = None
    autostart_order: int | None = None
    restart: bool = False


class UpdateResponse(BaseModel):
    instance: InstanceOut
    restart_required: bool


class EventOut(BaseModel):
    id: int | None
    type: str
    data: dict[str, Any]
    created_at: datetime


class TestRequest(BaseModel):
    content: str = Field(default="你好，請用一句話自我介紹。", max_length=2000)


class LogsOut(BaseModel):
    lines: list[dict[str, Any]]


def _out(svc: Svc, inst: Instance, detail: bool = False) -> InstanceOut:
    mgr = svc.manager
    diag = None
    if detail:
        cmd = None
        model = svc.catalog.get(inst.model_id)
        if model:
            with contextlib.suppress(ValueError):
                cmd = build_command(svc.profile, model, inst.served_model_name, InstanceParams(**inst.params))
        diag = Diagnostics(
            container_name=inst.container_name,
            container_id=inst.container_id,
            internal_url=mgr.internal_base(inst),
            image=svc.profile.vllm.image,
            gateway_model_id=inst.gateway_model_id,
            command=cmd,
        )
    return InstanceOut(
        **inst.model_dump(
            include={
                "id",
                "display_name",
                "served_model_name",
                "model_id",
                "preset",
                "params",
                "autostart",
                "autostart_order",
                "status",
                "phase",
                "phase_started_at",
                "last_error",
                "gateway_state",
                "created_at",
                "updated_at",
            }
        ),
        endpoint=Endpoint(api_base=svc.settings.public_api_base, model=inst.served_model_name),
        diagnostics=diag,
    )


def _planning_error(e: PlanningError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if e.code.endswith("NOT_FOUND") else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail={"code": e.code, "params": e.params})


def _conflict(e: ConflictError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": e.code, "params": e.params})


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "INSTANCE_NOT_FOUND"})


def _model_or_404(svc: Svc, model_id: str) -> ModelMeta:
    m = svc.catalog.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    return m


# ---------------------------------------------------------------- presets / schema


@router.get("/presets", response_model=list[ResolvedPreset])
def list_presets(svc: Svc, _: CurrentPrincipal, model_id: str = Query(...)) -> list[ResolvedPreset]:
    return svc.presets.resolve_all(_model_or_404(svc, model_id))


@router.get("/param-schema", response_model=list[ParamField])
def get_param_schema(
    svc: Svc, _: CurrentPrincipal, model_id: str | None = None, preset: str = "balanced"
) -> list[ParamField]:
    model = _model_or_404(svc, model_id) if model_id else None
    defaults = svc.presets.resolve(preset, model).params if model and preset in svc.presets.ids() else None
    return param_schema(svc.profile, model, defaults)


# ---------------------------------------------------------------- instances


@router.post("/instances/preview", response_model=Plan)
def preview(body: PlanInput, svc: Svc, _: CurrentPrincipal, exclude_id: str | None = None) -> Plan:
    try:
        return svc.manager.plan(body, exclude_id=exclude_id)
    except PlanningError as e:
        raise _planning_error(e) from e


@router.get("/instances", response_model=list[InstanceOut])
def list_instances(svc: Svc, _: CurrentPrincipal) -> list[InstanceOut]:
    return [_out(svc, i) for i in svc.manager.all()]


@router.post("/instances", response_model=InstanceOut, status_code=status.HTTP_201_CREATED)
async def create_instance(body: CreateRequest, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    try:
        plan = svc.manager.plan(body)
        inst = svc.manager.create(plan)
        if body.start:
            inst = await svc.manager.start(inst.id, reason="created")
    except PlanningError as e:
        raise _planning_error(e) from e
    except ConflictError as e:
        raise _conflict(e) from e
    return _out(svc, inst, detail=True)


@router.get("/instances/{instance_id}", response_model=InstanceOut)
def get_instance(instance_id: str, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    try:
        return _out(svc, svc.manager.get(instance_id), detail=True)
    except NotFoundError as e:
        raise _not_found() from e


@router.patch("/instances/{instance_id}", response_model=UpdateResponse)
async def update_instance(instance_id: str, body: UpdateRequest, svc: Svc, _: CurrentPrincipal) -> UpdateResponse:
    mgr = svc.manager
    try:
        cur = mgr.get(instance_id)
        inp = PlanInput(
            model_id=body.model_id or cur.model_id,
            preset=body.preset or cur.preset,
            params={**cur.params, **(body.params or {})},
            display_name=body.display_name or cur.display_name,
            served_model_name=body.served_model_name or cur.served_model_name,
            autostart=cur.autostart if body.autostart is None else body.autostart,
            autostart_order=cur.autostart_order if body.autostart_order is None else body.autostart_order,
        )
        plan = mgr.plan(inp, exclude_id=instance_id)
        inst, restart_required = mgr.update(instance_id, plan)
        if body.restart and restart_required:
            inst = await mgr.restart(instance_id)
            restart_required = False
    except NotFoundError as e:
        raise _not_found() from e
    except PlanningError as e:
        raise _planning_error(e) from e
    except ConflictError as e:
        raise _conflict(e) from e
    return UpdateResponse(instance=_out(svc, inst, detail=True), restart_required=restart_required)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(instance_id: str, svc: Svc, _: CurrentPrincipal) -> None:
    try:
        await svc.manager.delete(instance_id)
    except NotFoundError as e:
        raise _not_found() from e
    except ConflictError as e:
        raise _conflict(e) from e


async def _action(svc: Svc, instance_id: str, action: str) -> InstanceOut:
    mgr = svc.manager
    fns: dict[str, Callable[[str], Awaitable[Instance]]] = {
        "start": mgr.start,
        "stop": mgr.stop,
        "restart": mgr.restart,
        "cancel": mgr.cancel,
        "gateway/retry": mgr.retry_gateway,
    }
    try:
        inst = await fns[action](instance_id)
    except NotFoundError as e:
        raise _not_found() from e
    except ConflictError as e:
        raise _conflict(e) from e
    return _out(svc, inst, detail=True)


@router.post("/instances/{instance_id}/start", response_model=InstanceOut, status_code=202)
async def start(instance_id: str, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    return await _action(svc, instance_id, "start")


@router.post("/instances/{instance_id}/stop", response_model=InstanceOut, status_code=202)
async def stop(instance_id: str, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    return await _action(svc, instance_id, "stop")


@router.post("/instances/{instance_id}/restart", response_model=InstanceOut, status_code=202)
async def restart(instance_id: str, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    return await _action(svc, instance_id, "restart")


@router.post("/instances/{instance_id}/cancel", response_model=InstanceOut, status_code=202)
async def cancel(instance_id: str, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    return await _action(svc, instance_id, "cancel")


@router.post("/instances/{instance_id}/gateway/retry", response_model=InstanceOut)
async def gateway_retry(instance_id: str, svc: Svc, _: CurrentPrincipal) -> InstanceOut:
    return await _action(svc, instance_id, "gateway/retry")


@router.get("/instances/{instance_id}/events", response_model=list[EventOut])
def events(instance_id: str, svc: Svc, _: CurrentPrincipal) -> list[InstanceEvent]:
    try:
        svc.manager.get(instance_id)
    except NotFoundError as e:
        raise _not_found() from e
    return svc.manager.events(instance_id)


@router.post("/instances/{instance_id}/test", response_model=TestResult)
async def test(instance_id: str, body: TestRequest, svc: Svc, _: CurrentPrincipal) -> TestResult:
    try:
        return await svc.manager.test(instance_id, body.content)
    except NotFoundError as e:
        raise _not_found() from e
    except ConflictError as e:
        raise _conflict(e) from e


# ---------------------------------------------------------------- logs


NOISE = ('"GET /health', '"GET /v1/models', '"GET /metrics')


def _split_ts(raw: str) -> tuple[str | None, str]:
    ts, sep, rest = raw.partition(" ")
    return (ts, rest) if sep and ts[:4].isdigit() and "T" in ts else (None, raw)


def _line(svc: Svc, raw: str) -> dict[str, Any]:
    ts, text = _split_ts(raw)
    return {"ts": ts, "text": text, "annotation": svc.classifier.annotate(text)}


@router.get("/instances/{instance_id}/logs", response_model=LogsOut)
async def get_logs(
    instance_id: str, svc: Svc, _: CurrentPrincipal, tail: int = Query(500, ge=1, le=10000), noise: bool = False
) -> LogsOut:
    try:
        raw = await asyncio.to_thread(svc.manager.logs, instance_id, tail)
    except NotFoundError as e:
        raise _not_found() from e
    lines = [_line(svc, r) for r in raw if noise or not any(n in r for n in NOISE)]
    return LogsOut(lines=lines)


@router.get("/instances/{instance_id}/logs/stream")
async def stream_logs(
    instance_id: str,
    request: Request,
    svc: Svc,
    _: CurrentPrincipal,
    tail: int = Query(100, ge=0, le=2000),
    noise: bool = False,
) -> StreamingResponse:
    try:
        inst = svc.manager.get(instance_id)
    except NotFoundError as e:
        raise _not_found() from e
    name = svc.manager.container_name(inst)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=1000)
    stop = threading.Event()

    def pump() -> None:
        try:
            for line in svc.docker.stream_logs(name, tail=tail):
                if stop.is_set():
                    break
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as e:
            log.debug("log stream ended for %s: %s", name, e)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=pump, daemon=True).start()

    async def gen() -> AsyncIterator[bytes]:
        try:
            while not await request.is_disconnected():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield b": ping\n\n"
                    continue
                if item is None:
                    yield b"event: end\ndata: {}\n\n"
                    break
                if not noise and any(n in item for n in NOISE):
                    continue
                yield f"data: {json.dumps(_line(svc, item), ensure_ascii=False)}\n\n".encode()
        finally:
            stop.set()

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ---------------------------------------------------------------- autostart


@router.get("/system/autostart", response_model=AutostartProgress)
def autostart_status(svc: Svc, _: CurrentPrincipal) -> AutostartProgress:
    return svc.manager.autostart


@router.post("/system/autostart/run", response_model=AutostartProgress)
def autostart_run(svc: Svc, _: CurrentPrincipal) -> AutostartProgress:
    return svc.manager.start_autostart()


@router.post("/system/autostart/cancel", response_model=AutostartProgress)
async def autostart_cancel(svc: Svc, _: CurrentPrincipal) -> AutostartProgress:
    return await svc.manager.cancel_autostart()
