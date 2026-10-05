from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.adapters.litellm_client import INSTANCE_FIELD, GatewayError
from app.api.deps import Svc
from app.api.system import gateway_status
from app.core.security import CurrentPrincipal
from app.domain.instance import InstanceStatus
from app.services.api_keys import ApiKeyOut, ApiKeyService, CreatedKey, CreateKeyRequest, KeyError_

router = APIRouter(prefix="/gateway", tags=["gateway"])


def _gateway_down(e: GatewayError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"code": "GATEWAY_UNREACHABLE"})


@router.get("/status")
async def gateway_state(svc: Svc, _: CurrentPrincipal) -> dict[str, Any]:
    return await gateway_status(svc)


@router.get("/connection-info")
def connection_info(svc: Svc, _: CurrentPrincipal) -> dict[str, Any]:
    ready = [
        i.served_model_name
        for i in svc.manager.all()
        if i.status == InstanceStatus.READY and i.gateway_model_id is not None
    ]
    return {"api_base": svc.settings.public_api_base, "models": ready}


@router.get("/models")
async def models(svc: Svc, _: CurrentPrincipal) -> list[dict[str, Any]]:
    instances = {i.id: i for i in svc.manager.all()}
    try:
        managed = await svc.litellm.list_managed_models()
    except GatewayError as e:
        raise _gateway_down(e) from e
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


@router.post("/models/{gateway_model_id}/cleanup", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup(gateway_model_id: str, svc: Svc, _: CurrentPrincipal) -> None:
    rows = await models(svc, _)
    row = next((r for r in rows if r["gateway_model_id"] == gateway_model_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "GATEWAY_MODEL_NOT_FOUND"})
    if row["sync"] == "ok":
        raise HTTPException(status_code=409, detail={"code": "GATEWAY_MODEL_IN_USE"})
    try:
        await svc.litellm.delete_model(gateway_model_id)
    except GatewayError as e:
        raise _gateway_down(e) from e


def _keys(svc: Svc) -> ApiKeyService:
    return ApiKeyService(svc.litellm)


def _key_error(e: KeyError_) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code})


@router.get("/keys", response_model=list[ApiKeyOut])
async def list_keys(svc: Svc, _: CurrentPrincipal) -> list[ApiKeyOut]:
    try:
        return await _keys(svc).list()
    except GatewayError as e:
        raise _gateway_down(e) from e


@router.post("/keys", response_model=CreatedKey, status_code=status.HTTP_201_CREATED)
async def create_key(body: CreateKeyRequest, svc: Svc, _: CurrentPrincipal) -> CreatedKey:
    try:
        return await _keys(svc).create(body)
    except GatewayError as e:
        raise _gateway_down(e) from e
    except KeyError_ as e:
        raise _key_error(e) from e


@router.post("/keys/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_key(key_id: str, svc: Svc, _: CurrentPrincipal) -> ApiKeyOut:
    try:
        return await _keys(svc).revoke(key_id)
    except GatewayError as e:
        raise _gateway_down(e) from e
    except KeyError_ as e:
        raise _key_error(e) from e
