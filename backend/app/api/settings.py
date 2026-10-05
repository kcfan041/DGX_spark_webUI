from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.services import api_base
from app.services.api_base import ApiBaseError, ApiBaseInfo, Mode

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
