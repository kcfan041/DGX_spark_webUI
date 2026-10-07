from typing import Any

from pydantic import BaseModel, Field

from app.adapters.metrics import GpuStats


class ExternalService(BaseModel):
    kind: str  # "container" | "process"
    name: str
    image: str | None = None
    status: str | None = None
    started_at: str | None = None
    ports: list[int] = Field(default_factory=list)
    compose_project: str | None = None
    pids: list[int] = Field(default_factory=list)
    gpu_bytes: int | None = None
    hint_key: str


class ExternalSummary(BaseModel):
    services: list[ExternalService]
    total_gpu_bytes: int


def hint_for(c: dict[str, Any]) -> str:
    if c.get("compose_project"):
        return "external.hint.compose"
    if "vllm" in (c.get("image") or "").lower():
        return "external.hint.vllm"
    return "external.hint.container"


def build_external(containers: list[dict[str, Any]], gpu: GpuStats | None, managed_ids: set[str]) -> ExternalSummary:
    by_id: dict[str, ExternalService] = {}
    for c in containers:
        by_id[c["id"]] = ExternalService(
            kind="container",
            name=c["name"],
            image=c.get("image"),
            status=c.get("status"),
            started_at=c.get("started_at"),
            ports=c.get("ports") or [],
            compose_project=c.get("compose_project"),
            hint_key=hint_for(c),
        )
    loose: dict[str, ExternalService] = {}
    for p in gpu.processes if gpu else []:
        cid = p.container_id
        if cid and cid in managed_ids:
            continue
        if cid and cid in by_id:
            svc = by_id[cid]
        elif cid:
            svc = by_id.setdefault(
                cid,
                ExternalService(kind="container", name=cid[:12], hint_key="external.hint.container"),
            )
        else:
            key = f"{p.pid}:{p.name}"
            svc = loose.setdefault(key, ExternalService(kind="process", name=p.name, hint_key="external.hint.process"))
        svc.pids.append(p.pid)
        if p.used_bytes is not None:
            svc.gpu_bytes = (svc.gpu_bytes or 0) + p.used_bytes
    services = [*by_id.values(), *loose.values()]
    services = [s for s in services if s.kind == "container" or (s.gpu_bytes or 0) > 256 * 2**20]
    services.sort(key=lambda s: -(s.gpu_bytes or 0))
    return ExternalSummary(services=services, total_gpu_bytes=sum(s.gpu_bytes or 0 for s in services))
