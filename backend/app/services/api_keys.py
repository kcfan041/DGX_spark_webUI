import contextlib
import re
import secrets
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.adapters.litellm_client import GatewayError
from app.services.ports import GatewayPort

CREATED_BY = "dgxsp"
PURPOSE_USER = "user"
PURPOSE_SYSTEM = "system-test"
MAX_NAME = 80

BudgetPeriod = Literal["1d", "7d", "30d"]
Expiry = Literal["7d", "30d", "90d", "365d"]


class KeyLimits(BaseModel):
    max_budget: float | None = Field(default=None, gt=0, le=1_000_000)
    budget_duration: BudgetPeriod | None = None
    rpm_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    tpm_limit: int | None = Field(default=None, ge=1, le=1_000_000_000)
    models: list[str] = Field(default_factory=list, max_length=200)


class ApiKeyOut(BaseModel):
    id: str
    name: str
    masked: str
    status: Literal["active", "revoked", "expired"]
    created_at: datetime | None
    last_active: datetime | None = None
    expires_at: datetime | None = None
    system: bool = False
    spend: float = 0.0
    limits: KeyLimits = Field(default_factory=KeyLimits)
    budget_reset_at: datetime | None = None


class CreateKeyRequest(KeyLimits):
    name: str = Field(min_length=1, max_length=MAX_NAME)
    expires_in: Expiry | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v


class UpdateKeyRequest(KeyLimits):
    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
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
    return f"dgxsp-{slug}-{secrets.token_hex(4)}"


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _limits(k: dict[str, Any]) -> KeyLimits:
    budget = k.get("max_budget")
    return KeyLimits(
        max_budget=float(budget) if budget else None,
        budget_duration=k.get("budget_duration") if k.get("budget_duration") in ("1d", "7d", "30d") else None,
        rpm_limit=k.get("rpm_limit") or None,
        tpm_limit=k.get("tpm_limit") or None,
        models=[str(m) for m in (k.get("models") or [])],
    )


def _to_out(k: dict[str, Any], now: datetime | None = None) -> ApiKeyOut:
    md = k.get("metadata") or {}
    expires = _parse_dt(k.get("expires"))
    status: Literal["active", "revoked", "expired"] = "active"
    if k.get("blocked"):
        status = "revoked"
    elif expires and expires <= (now or datetime.now(expires.tzinfo)):
        status = "expired"
    return ApiKeyOut(
        id=str(k.get("token") or k.get("token_id") or ""),
        name=str(md.get("display_name") or k.get("key_alias") or ""),
        masked=str(k.get("key_name") or "sk-…"),
        status=status,
        created_at=_parse_dt(k.get("created_at")),
        last_active=_parse_dt(k.get("last_active")),
        expires_at=expires,
        system=md.get("purpose") == PURPOSE_SYSTEM,
        spend=float(k.get("spend") or 0.0),
        limits=_limits(k),
        budget_reset_at=_parse_dt(k.get("budget_reset_at")),
    )


def _limit_fields(req: KeyLimits) -> dict[str, Any]:
    return {
        "max_budget": req.max_budget,
        "budget_duration": req.budget_duration if req.max_budget else None,
        "rpm_limit": req.rpm_limit,
        "tpm_limit": req.tpm_limit,
        "models": req.models,
    }


def _gateway_error(e: GatewayError) -> KeyError_:
    return KeyError_("GATEWAY_UNREACHABLE" if e.status_code is None else "GATEWAY_REGISTER_FAILED", 502)


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
        md = {"created_by": CREATED_BY, "purpose": PURPOSE_USER, "display_name": req.name}
        fields = {k: v for k, v in _limit_fields(req).items() if v not in (None, [])}
        if req.expires_in:
            fields["duration"] = req.expires_in
        try:
            resp = await self.gateway.generate_key(_alias(req.name), md, **fields)
        except GatewayError as e:
            if e.status_code is None:
                raise
            raise KeyError_("GATEWAY_REGISTER_FAILED", 502) from e
        key = str(resp.get("key") or "")
        if not key:
            raise KeyError_("GATEWAY_REGISTER_FAILED", 502)
        resp.setdefault("metadata", md)
        out = _to_out(resp)
        return CreatedKey(**out.model_dump(), key=key)

    async def _mine(self, key_id: str) -> ApiKeyOut:
        mine = {k.id: k for k in await self.list(include_system=True)}
        target = mine.get(key_id)
        if target is None:
            raise KeyError_("KEY_NOT_FOUND", 404)
        if target.system:
            raise KeyError_("KEY_SYSTEM", 409)
        return target

    async def update(self, key_id: str, req: UpdateKeyRequest) -> ApiKeyOut:
        target = await self._mine(key_id)
        if target.status == "revoked":
            raise KeyError_("KEY_REVOKED", 409)
        fields = _limit_fields(req)
        if req.name and req.name != target.name:
            fields["metadata"] = {"created_by": CREATED_BY, "purpose": PURPOSE_USER, "display_name": req.name}
        try:
            await self.gateway.update_key(key_id, fields)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return await self._mine(key_id)

    async def revoke(self, key_id: str) -> ApiKeyOut:
        target = await self._mine(key_id)
        if target.status == "revoked":
            return target
        try:
            await self.gateway.block_key(key_id)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return target.model_copy(update={"status": "revoked"})

    async def rotate(self, key_id: str) -> CreatedKey:
        """New key with the same name and limits; the old key is revoked. (LiteLLM's regenerate is Enterprise.)"""
        target = await self._mine(key_id)
        if target.status == "revoked":
            raise KeyError_("KEY_REVOKED", 409)
        req = CreateKeyRequest(name=target.name, **target.limits.model_dump())
        created = await self.create(req)
        if target.expires_at and target.status == "active":
            remaining = target.expires_at - datetime.now(target.expires_at.tzinfo)
            days = max(1, int(remaining.total_seconds() // 86400))
            with contextlib.suppress(GatewayError):
                await self.gateway.update_key(created.id, {"duration": f"{days}d"})
            created = created.model_copy(update={"expires_at": target.expires_at})
        try:
            await self.gateway.block_key(key_id)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return created
