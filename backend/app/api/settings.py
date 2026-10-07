import asyncio
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.services import api_base
from app.services.api_base import ApiBaseError, ApiBaseInfo, Mode, is_local_host
from app.services.runtime_settings import (
    TIMEOUT_MAX_MINUTES,
    TIMEOUT_MIN_MINUTES,
    SettingError,
    Value,
    normalize_endpoint,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class ApiBaseUpdate(BaseModel):
    mode: Mode | None
    value: str | None = None


@router.get("/api-base", response_model=ApiBaseInfo)
def get_api_base(request: Request, svc: Svc, _: CurrentPrincipal) -> ApiBaseInfo:
    return api_base.resolve(request, svc.settings, request.app.state.engine)


@router.put("/api-base", response_model=ApiBaseInfo)
def put_api_base(body: ApiBaseUpdate, request: Request, svc: Svc, _: CurrentPrincipal) -> ApiBaseInfo:
    try:
        api_base.update(request.app.state.engine, body.mode, body.value)
    except ApiBaseError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": e.code}) from e
    return api_base.resolve(request, svc.settings, request.app.state.engine)


# ---------------------------------------------------------------- advanced (runtime-changeable)


class DeployInfo(BaseModel):
    profile: str
    model_root: str
    model_owner: str | None
    hf_cache_dir: str | None
    gateway_port: int
    gateway_bind: str
    gateway_local_only: bool
    vllm_image: str


class AdvancedSettings(BaseModel):
    verbose_access_log: Value
    hf_endpoint: Value
    health_timeout_min: Value
    timeout_range: tuple[int, int] = (TIMEOUT_MIN_MINUTES, TIMEOUT_MAX_MINUTES)
    deploy: DeployInfo


class AdvancedUpdate(BaseModel):
    verbose_access_log: bool | None = None
    hf_endpoint: str | None = None
    health_timeout_min: int | None = None
    reset: list[Literal["verbose_access_log", "hf_endpoint", "health_timeout_min"]] = Field(default_factory=list)


def _advanced(svc: Svc) -> AdvancedSettings:
    s = svc.settings
    owner = f"{s.model_owner_uid}:{s.model_owner_gid}" if s.model_owner_uid is not None else None
    return AdvancedSettings(
        verbose_access_log=svc.runtime.verbose(),
        hf_endpoint=svc.runtime.hf_endpoint(),
        health_timeout_min=svc.runtime.health_timeout(),
        deploy=DeployInfo(
            profile=svc.profile.name,
            model_root=s.host_model_root,
            model_owner=owner,
            hf_cache_dir=s.host_hf_cache_dir,
            gateway_port=s.gateway_port,
            gateway_bind=s.gateway_bind,
            gateway_local_only=is_local_host(s.gateway_bind),
            vllm_image=svc.profile.vllm.image,
        ),
    )


@router.get("/advanced", response_model=AdvancedSettings)
def get_advanced(svc: Svc, _: CurrentPrincipal) -> AdvancedSettings:
    return _advanced(svc)


@router.put("/advanced", response_model=AdvancedSettings)
def put_advanced(body: AdvancedUpdate, svc: Svc, _: CurrentPrincipal) -> AdvancedSettings:
    rt = svc.runtime
    sent = body.model_fields_set
    try:
        if "verbose_access_log" in body.reset:
            rt.set_verbose(None)
        elif "verbose_access_log" in sent and body.verbose_access_log is not None:
            rt.set_verbose(body.verbose_access_log)
        if "hf_endpoint" in body.reset:
            rt.set_hf_endpoint(None, clear=True)
        elif "hf_endpoint" in sent:
            rt.set_hf_endpoint(body.hf_endpoint)
        if "health_timeout_min" in body.reset:
            rt.set_health_timeout(None)
        elif "health_timeout_min" in sent and body.health_timeout_min is not None:
            rt.set_health_timeout(body.health_timeout_min)
    except SettingError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": e.code, "params": {"field": e.field}}
        ) from e
    return _advanced(svc)


class EndpointTest(BaseModel):
    endpoint: str | None = None


@router.post("/advanced/test-hf-endpoint")
async def test_hf_endpoint(body: EndpointTest, svc: Svc, _: CurrentPrincipal) -> dict[str, Any]:
    endpoint = body.endpoint.strip() if body.endpoint and body.endpoint.strip() else None
    if endpoint:
        try:
            endpoint = normalize_endpoint(endpoint)
        except SettingError as e:
            raise HTTPException(status_code=422, detail={"code": e.code}) from e
    return await asyncio.to_thread(svc.hub.ping, endpoint)
