from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.security import (
    MAX_TOKEN_LEN,
    MIN_TOKEN_LEN,
    AdminTokenAuth,
    AuthProvider,
    CurrentPrincipal,
    get_auth_provider,
    hash_token,
)
from app.db.settings_store import set_setting

ADMIN_HASH_KEY = "admin_token_hash"

Provider = Annotated[AuthProvider, Depends(get_auth_provider)]

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    token: str


class MeResponse(BaseModel):
    subject: str
    roles: list[str]


class TokenInfo(BaseModel):
    source: Literal["web", "env"]


class ChangeTokenRequest(BaseModel):
    current: str = Field(max_length=MAX_TOKEN_LEN)
    new: str = Field(min_length=MIN_TOKEN_LEN, max_length=MAX_TOKEN_LEN)


@router.post("/login", response_model=MeResponse)
def login(body: LoginRequest, provider: Provider) -> MeResponse:
    principal = provider.authenticate(body.token)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "INVALID_TOKEN"})
    return MeResponse(subject=principal.subject, roles=sorted(principal.roles))


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(subject=principal.subject, roles=sorted(principal.roles))


def _admin(provider: AuthProvider) -> AdminTokenAuth:
    if not isinstance(provider, AdminTokenAuth):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "TOKEN_CHANGE_UNSUPPORTED"})
    return provider


@router.get("/token", response_model=TokenInfo)
def token_info(provider: Provider, _: CurrentPrincipal) -> TokenInfo:
    return TokenInfo(source="web" if _admin(provider).source() == "web" else "env")


@router.put("/token", response_model=TokenInfo)
def change_token(body: ChangeTokenRequest, request: Request, provider: Provider, _: CurrentPrincipal) -> TokenInfo:
    auth = _admin(provider)
    if auth.authenticate(body.current) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "TOKEN_CURRENT_WRONG"})
    new = body.new.strip()
    if len(new) < MIN_TOKEN_LEN or new != body.new or any(c.isspace() for c in new):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "TOKEN_WEAK"})
    if new == body.current:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "TOKEN_SAME"})
    set_setting(request.app.state.engine, ADMIN_HASH_KEY, hash_token(new))
    return TokenInfo(source="web")
