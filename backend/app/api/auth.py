from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.security import AuthProvider, CurrentPrincipal, get_auth_provider

Provider = Annotated[AuthProvider, Depends(get_auth_provider)]

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    token: str


class MeResponse(BaseModel):
    subject: str
    roles: list[str]


@router.post("/login", response_model=MeResponse)
def login(body: LoginRequest, provider: Provider) -> MeResponse:
    principal = provider.authenticate(body.token)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"})
    return MeResponse(subject=principal.subject, roles=sorted(principal.roles))


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(subject=principal.subject, roles=sorted(principal.roles))
