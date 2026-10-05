import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.adapters.litellm_client import GatewayError
from app.services.ports import GatewayPort

CREATED_BY = "dgxsp"
PURPOSE_USER = "user"
PURPOSE_SYSTEM = "system-test"
MAX_NAME = 80


class ApiKeyOut(BaseModel):
    id: str
    name: str
    masked: str
    status: Literal["active", "revoked"]
    created_at: datetime | None
    last_active: datetime | None = None
    system: bool = False


class CreateKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v


class CreatedKey(ApiKeyOut):
    key: str


class KeyError_(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _alias(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "key"
    return f"dgxsp-{slug}"


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_out(k: dict[str, Any]) -> ApiKeyOut:
    md = k.get("metadata") or {}
    return ApiKeyOut(
        id=str(k.get("token") or k.get("token_id") or ""),
        name=str(md.get("display_name") or k.get("key_alias") or ""),
        masked=str(k.get("key_name") or "sk-…"),
        status="revoked" if k.get("blocked") else "active",
        created_at=_parse_dt(k.get("created_at")),
        last_active=_parse_dt(k.get("last_active")),
        system=md.get("purpose") == PURPOSE_SYSTEM,
    )


class ApiKeyService:
    def __init__(self, gateway: GatewayPort) -> None:
        self.gateway = gateway

    async def list(self, include_system: bool = False) -> list[ApiKeyOut]:
        keys = await self.gateway.list_keys()
        out = [_to_out(k) for k in keys if (k.get("metadata") or {}).get("created_by") == CREATED_BY]
        if not include_system:
            out = [k for k in out if not k.system]
        return sorted(out, key=lambda k: (k.status != "active", -(k.created_at.timestamp() if k.created_at else 0)))

    async def create(self, req: CreateKeyRequest) -> CreatedKey:
        resp = await self.gateway.generate_key(
            _alias(req.name), {"created_by": CREATED_BY, "purpose": PURPOSE_USER, "display_name": req.name}
        )
        key = str(resp.get("key") or "")
        if not key:
            raise KeyError_("GATEWAY_REGISTER_FAILED", 502)
        resp.setdefault("metadata", {"created_by": CREATED_BY, "purpose": PURPOSE_USER, "display_name": req.name})
        out = _to_out(resp)
        return CreatedKey(**out.model_dump(), key=key)

    async def revoke(self, key_id: str) -> ApiKeyOut:
        mine = {k.id: k for k in await self.list(include_system=True)}
        target = mine.get(key_id)
        if target is None:
            raise KeyError_("KEY_NOT_FOUND", 404)
        if target.system:
            raise KeyError_("KEY_SYSTEM", 409)
        if target.status == "revoked":
            return target
        try:
            await self.gateway.block_key(key_id)
        except GatewayError as e:
            raise KeyError_("GATEWAY_UNREACHABLE" if e.status_code is None else "GATEWAY_REGISTER_FAILED", 502) from e
        return target.model_copy(update={"status": "revoked"})
