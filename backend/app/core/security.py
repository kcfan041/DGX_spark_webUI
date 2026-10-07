import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.settings import get_settings

MIN_TOKEN_LEN = 12
MAX_TOKEN_LEN = 256
_ITERATIONS = 200_000


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]


class AuthProvider(Protocol):
    def authenticate(self, credential: str) -> Principal | None: ...


def hash_token(token: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_hash(token: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        got = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, got)


class AdminTokenAuth:
    """Web-set token (stored as a hash) takes precedence over DGXSP_ADMIN_TOKEN from deploy/.env."""

    def __init__(self, token: str, stored_hash: Callable[[], str | None] | None = None) -> None:
        self._token = token.encode()
        self._stored_hash = stored_hash or (lambda: None)
        self._cache: tuple[str, str] | None = None

    def source(self) -> str:
        return "web" if self._stored_hash() else "env"

    def authenticate(self, credential: str) -> Principal | None:
        if not credential:
            return None
        stored = self._stored_hash()
        if stored:
            if self._cache and self._cache[0] == stored and hmac.compare_digest(self._cache[1], credential):
                ok = True
            else:
                ok = verify_hash(credential, stored)
                if ok:
                    self._cache = (stored, credential)
        else:
            ok = bool(self._token) and hmac.compare_digest(self._token, credential.encode())
        return Principal(subject="admin", roles=frozenset({"admin"})) if ok else None


def build_auth_provider(stored_hash: Callable[[], str | None] | None = None) -> AdminTokenAuth:
    return AdminTokenAuth(get_settings().admin_token.get_secret_value(), stored_hash)


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
