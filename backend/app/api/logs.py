import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import Svc
from app.api.instances import NOISE, LogsOut, _line, sse_logs
from app.core.security import CurrentPrincipal
from app.services.instance_manager import NotFoundError

router = APIRouter(prefix="/logs", tags=["logs"])

PLATFORM = {"gateway": "litellm", "backend": "backend"}


class LogSource(BaseModel):
    id: str
    kind: str  # "service" | "platform"
    name: str
    status: str | None = None


def _container(svc: Svc, source: str) -> str:
    if source in PLATFORM:
        name = svc.docker.compose_container(PLATFORM[source])
        if not name:
            raise HTTPException(status_code=404, detail={"code": "LOG_SOURCE_NOT_FOUND"})
        return name
    if source.startswith("service:"):
        try:
            return svc.manager.container_name(svc.manager.get(source.removeprefix("service:")))
        except NotFoundError as e:
            raise HTTPException(status_code=404, detail={"code": "LOG_SOURCE_NOT_FOUND"}) from e
    raise HTTPException(status_code=404, detail={"code": "LOG_SOURCE_NOT_FOUND"})


@router.get("/sources", response_model=list[LogSource])
async def sources(svc: Svc, _: CurrentPrincipal) -> list[LogSource]:
    out = [
        LogSource(id=f"service:{i.id}", kind="service", name=i.display_name, status=i.status) for i in svc.manager.all()
    ]
    for key, service in PLATFORM.items():
        name = await asyncio.to_thread(svc.docker.compose_container, service)
        if name:
            out.append(LogSource(id=key, kind="platform", name=key))
    return out


@router.get("/{source}", response_model=LogsOut)
async def get_logs(
    source: str, svc: Svc, _: CurrentPrincipal, tail: int = Query(500, ge=1, le=10000), noise: bool = False
) -> LogsOut:
    name = await asyncio.to_thread(_container, svc, source)
    raw = await asyncio.to_thread(svc.docker.logs, name, tail)
    return LogsOut(lines=[_line(svc, r) for r in raw if noise or not any(n in r for n in NOISE)])


@router.get("/{source}/stream")
async def stream(
    source: str,
    request: Request,
    svc: Svc,
    _: CurrentPrincipal,
    tail: int = Query(100, ge=0, le=2000),
    noise: bool = False,
) -> StreamingResponse:
    name = await asyncio.to_thread(_container, svc, source)
    return sse_logs(svc, request, name, tail, noise)
