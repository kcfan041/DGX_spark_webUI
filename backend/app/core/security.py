import hmac
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.settings import get_settings


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]


class AuthProvider(Protocol):
    def authenticate(self, credential: str) -> Principal | None: ...


class AdminTokenAuth:
    def __init__(self, token: str) -> None:
        self._token = token.encode()

    def authenticate(self, credential: str) -> Principal | None:
        if not self._token or not credential:
            return None
        if hmac.compare_digest(self._token, credential.encode()):
            return Principal(subject="admin", roles=frozenset({"admin"}))
        return None


def build_auth_provider() -> AuthProvider:
    return AdminTokenAuth(get_settings().admin_token.get_secret_value())


def get_auth_provider(request: Request) -> AuthProvider:
    provider: AuthProvider = request.app.state.auth_provider
    return provider


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def require_principal(
    provider: Annotated[AuthProvider, Depends(get_auth_provider)],
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    principal = provider.authenticate(_bearer(authorization))
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
