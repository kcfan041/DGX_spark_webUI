import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import func, select

from app import __version__
from app.adapters.litellm_client import GatewayError
from app.adapters.metrics import GpuStats
from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.db.models import Instance
from app.db.session import DbSession
from app.domain.instance import InstanceStatus
from app.services.external import ExternalSummary, build_external

router = APIRouter(prefix="/system", tags=["system"])


class Capabilities(BaseModel):
    memory: bool
    disk: bool
    gpu: bool
    docker: bool


class SystemSummary(BaseModel):
    health: str
    capabilities: Capabilities
    memory: dict[str, Any] | None
    disk: dict[str, Any] | None
    gpu: dict[str, Any] | None
    gateway: dict[str, Any]
    counts: dict[str, int]
    external_services: int
    external_gpu_bytes: int = 0


async def gateway_status(svc: Svc) -> dict[str, Any]:
    try:
        r = await svc.litellm.readiness()
        db_ok = str(r.get("db", "")).lower() == "connected"
        return {"reachable": True, "db_connected": db_ok, "version": r.get("litellm_version")}
    except GatewayError as e:
        down = e.status_code is None
        return {
            "reachable": not down,
            "db_connected": False,
            "error": str(e)[:200],
            "reason": "not_running" if down else "not_ready",
        }


@router.get("/info")
async def info(svc: Svc, _: CurrentPrincipal) -> dict[str, Any]:
    docker_ok = await asyncio.to_thread(svc.docker.ping)
    return {
        "version": __version__,
        "profile": svc.profile.name,
        "profile_description": svc.profile.description,
        "vllm_image": svc.profile.vllm.image,
        "timeouts": svc.profile.timeouts.model_dump(),
        "memory_defaults": svc.profile.memory.model_dump(),
        "docker": await asyncio.to_thread(svc.docker.info) if docker_ok else None,
        "image": await asyncio.to_thread(svc.docker.image_info) if docker_ok else None,
        "gateway": await gateway_status(svc),
    }


@router.get("/summary", response_model=SystemSummary)
async def summary(svc: Svc, db: DbSession, _: CurrentPrincipal) -> SystemSummary:
    mem = svc.metrics.memory()
    disk = svc.metrics.disk()
    gpu = await asyncio.to_thread(svc.metrics.gpu)
    docker_ok = await asyncio.to_thread(svc.docker.ping)
    gw = await gateway_status(svc)
    ext = await external_summary(svc, gpu, docker_ok)

    rows = db.exec(select(Instance.status, func.count()).group_by(Instance.status)).all()
    counts = {s.value: 0 for s in InstanceStatus}
    for st, n in rows:
        counts[str(st)] = int(n)

    if not docker_ok:
        health = "runtime_error"
    elif not gw["reachable"]:
        health = "gateway_unreachable"
    elif not gw["db_connected"]:
        health = "gateway_db"
    elif counts[InstanceStatus.ERROR.value] > 0:
        health = "attention"
    else:
        health = "ok"

    return SystemSummary(
        health=health,
        capabilities=Capabilities(memory=mem is not None, disk=disk is not None, gpu=gpu is not None, docker=docker_ok),
        memory=mem.model_dump() | {"used_bytes": mem.used_bytes} if mem else None,
        disk=disk.model_dump() if disk else None,
        gpu=gpu.model_dump(exclude={"processes"}) | {"process_bytes": gpu.process_bytes} if gpu else None,
        gateway=gw,
        counts=counts,
        external_services=len(ext.services),
        external_gpu_bytes=ext.total_gpu_bytes,
    )


async def external_summary(svc: Svc, gpu: GpuStats | None, docker_ok: bool) -> ExternalSummary:
    if not docker_ok:
        return build_external([], gpu, set())
    containers = await asyncio.to_thread(svc.docker.list_external_candidates)
    managed = await asyncio.to_thread(svc.docker.managed_container_ids)
    return build_external(containers, gpu, managed)


@router.get("/external", response_model=ExternalSummary)
async def external(svc: Svc, _: CurrentPrincipal) -> ExternalSummary:
    gpu = await asyncio.to_thread(svc.metrics.gpu)
    docker_ok = await asyncio.to_thread(svc.docker.ping)
    return await external_summary(svc, gpu, docker_ok)
