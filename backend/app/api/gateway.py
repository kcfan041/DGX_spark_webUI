from typing import Any

from fastapi import APIRouter

from app.adapters.litellm_client import INSTANCE_FIELD, GatewayError
from app.api.deps import Svc
from app.api.system import gateway_status
from app.core.security import CurrentPrincipal
from app.domain.instance import InstanceStatus

router = APIRouter(prefix="/gateway", tags=["gateway"])


@router.get("/status")
async def status(svc: Svc, _: CurrentPrincipal) -> dict[str, Any]:
    return await gateway_status(svc)


@router.get("/connection-info")
def connection_info(svc: Svc, _: CurrentPrincipal) -> dict[str, Any]:
    ready = [i.served_model_name for i in svc.manager.all() if i.status == InstanceStatus.READY]
    return {"api_base": svc.settings.public_api_base, "models": ready}


@router.get("/models")
async def models(svc: Svc, _: CurrentPrincipal) -> list[dict[str, Any]]:
    instances = {i.id: i for i in svc.manager.all()}
    try:
        managed = await svc.litellm.list_managed_models()
    except GatewayError:
        return []
    out = []
    for m in managed:
        info = m.get("model_info") or {}
        inst = instances.get(info.get(INSTANCE_FIELD) or "")
        in_sync = bool(inst and inst.status == InstanceStatus.READY and inst.gateway_model_id == info.get("id"))
        out.append(
            {
                "model_name": m.get("model_name"),
                "gateway_model_id": info.get("id"),
                "instance_id": inst.id if inst else None,
                "instance_name": inst.display_name if inst else None,
                "instance_status": inst.status if inst else None,
                "sync": "ok" if in_sync else "orphan",
            }
        )
    return out


@router.post("/resync")
async def resync(svc: Svc, _: CurrentPrincipal) -> dict[str, int]:
    return await svc.manager.reconcile_once()
