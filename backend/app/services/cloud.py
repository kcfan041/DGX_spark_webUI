import logging
import re
import secrets
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.adapters.litellm_client import CLOUD_FLAG, MANAGED_FLAG, PROVIDER_FIELD, GatewayError
from app.services.ports import GatewayPort
from app.services.pricing import MAX_PRICE, PER

log = logging.getLogger(__name__)

ProviderType = Literal["openai", "anthropic", "gemini", "openai_compatible"]
CRED_PREFIX = "dgxsp-"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")
COST_MAP_TTL_S = 24 * 3600


class ProviderSpec(BaseModel):
    type: ProviderType
    litellm_provider: str
    model_prefix: str
    needs_api_base: bool
    api_key_required: bool
    test_model: str | None
    catalog_provider: str | None
    key_url: str | None


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        type="openai",
        litellm_provider="openai",
        model_prefix="openai/",
        needs_api_base=False,
        api_key_required=True,
        test_model="gpt-4o-mini",
        catalog_provider="openai",
        key_url="https://platform.openai.com/api-keys",
    ),
    "anthropic": ProviderSpec(
        type="anthropic",
        litellm_provider="anthropic",
        model_prefix="anthropic/",
        needs_api_base=False,
        api_key_required=True,
        test_model="claude-haiku-4-5",
        catalog_provider="anthropic",
        key_url="https://console.anthropic.com/settings/keys",
    ),
    "gemini": ProviderSpec(
        type="gemini",
        litellm_provider="gemini",
        model_prefix="gemini/",
        needs_api_base=False,
        api_key_required=True,
        test_model="gemini-2.5-flash",
        catalog_provider="gemini",
        key_url="https://aistudio.google.com/apikey",
    ),
    "openai_compatible": ProviderSpec(
        type="openai_compatible",
        litellm_provider="openai",
        model_prefix="openai/",
        needs_api_base=True,
        api_key_required=False,
        test_model=None,
        catalog_provider=None,
        key_url=None,
    ),
}


class CloudError(Exception):
    def __init__(self, code: str, status: int = 400, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.params = params or {}


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


class ProviderIn(BaseModel):
    type: ProviderType
    name: str = Field(min_length=1, max_length=60)
    api_key: str | None = Field(default=None, max_length=500)
    api_base: str | None = Field(default=None, max_length=300)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v

    @field_validator("api_key", "api_base")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _clean(v)


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    api_key: str | None = Field(default=None, max_length=500)
    api_base: str | None = Field(default=None, max_length=300)

    @field_validator("name", "api_key", "api_base")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _clean(v)


class ProviderOut(BaseModel):
    id: str
    type: ProviderType
    name: str
    api_base: str | None
    masked_key: str | None
    models: int


class ConnTestIn(BaseModel):
    type: ProviderType | None = None
    api_key: str | None = None
    api_base: str | None = None
    model: str | None = None

    @field_validator("api_key", "api_base", "model")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _clean(v)


class ConnTestOut(BaseModel):
    ok: bool
    model: str
    error: str | None = None


class CatalogModel(BaseModel):
    id: str
    input_per_mtok: float | None
    output_per_mtok: float | None
    max_input_tokens: int | None


class CloudModelIn(BaseModel):
    provider_id: str
    model: str = Field(min_length=1, max_length=200)
    name: str | None = Field(default=None, max_length=100)
    input_per_mtok: float | None = Field(default=None, ge=0, le=MAX_PRICE)
    output_per_mtok: float | None = Field(default=None, ge=0, le=MAX_PRICE)

    @field_validator("model", "name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return _clean(v)


class CloudModelOut(BaseModel):
    id: str
    name: str
    model: str
    provider_id: str | None
    provider_name: str | None
    provider_type: str | None
    input_per_mtok: float | None
    output_per_mtok: float | None
    custom_price: bool


def _check_api_base(v: str | None) -> str | None:
    if v is None:
        return None
    if not re.match(r"^https?://[^\s/]+", v):
        raise CloudError("API_BASE_INVALID", 422)
    return v.rstrip("/")


def _gateway_error(e: GatewayError) -> CloudError:
    if e.status_code is None:
        return CloudError("GATEWAY_UNREACHABLE", 502)
    return CloudError("GATEWAY_REQUEST_FAILED", 502, {"detail": str(e)[:300]})


def _short_error(raw: str) -> str:
    first = raw.split("stack trace:")[0].strip()
    first = re.sub(r"^litellm\.\w+:\s*", "", first)
    return first[:400]


def _per_m(v: Any) -> float | None:
    try:
        return round(float(v) * PER, 6) if v is not None else None
    except (TypeError, ValueError):
        return None


def _first(a: dict[str, Any], b: dict[str, Any], key: str) -> Any:
    return a[key] if a.get(key) is not None else b.get(key)


class CloudService:
    def __init__(self, gateway: GatewayPort) -> None:
        self.gateway = gateway
        self._cost_map: dict[str, Any] | None = None
        self._cost_map_at = 0.0

    # ------------------------------------------------------------------ providers

    async def _credentials(self) -> list[dict[str, Any]]:
        try:
            creds = await self.gateway.list_credentials()
        except GatewayError as e:
            raise _gateway_error(e) from e
        return [c for c in creds if (c.get("credential_info") or {}).get(MANAGED_FLAG)]

    async def _credential(self, provider_id: str) -> dict[str, Any]:
        for c in await self._credentials():
            if c.get("credential_name") == provider_id:
                return c
        raise CloudError("PROVIDER_NOT_FOUND", 404)

    async def cloud_models_raw(self) -> list[dict[str, Any]]:
        try:
            models = await self.gateway.list_models()
        except GatewayError as e:
            raise _gateway_error(e) from e
        return [m for m in models if (m.get("model_info") or {}).get(CLOUD_FLAG)]

    async def list_providers(self) -> list[ProviderOut]:
        creds = await self._credentials()
        models = await self.cloud_models_raw()
        out = []
        for c in creds:
            info = c.get("credential_info") or {}
            values = c.get("credential_values") or {}
            cid = str(c.get("credential_name"))
            used = sum(1 for m in models if (m.get("model_info") or {}).get(PROVIDER_FIELD) == cid)
            out.append(
                ProviderOut(
                    id=cid,
                    type=info.get(PROVIDER_FIELD) or "openai_compatible",
                    name=str(info.get("display_name") or cid),
                    api_base=info.get("api_base"),
                    masked_key=values.get("api_key"),
                    models=used,
                )
            )
        return sorted(out, key=lambda p: p.name.lower())

    async def create_provider(self, body: ProviderIn) -> ProviderOut:
        spec = PROVIDERS[body.type]
        api_base = _check_api_base(body.api_base)
        if spec.needs_api_base and not api_base:
            raise CloudError("API_BASE_REQUIRED", 422)
        if spec.api_key_required and not body.api_key:
            raise CloudError("API_KEY_REQUIRED", 422)
        if any(p.name.lower() == body.name.lower() for p in await self.list_providers()):
            raise CloudError("PROVIDER_NAME_TAKEN", 409)
        slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:30] or body.type
        cid = f"{CRED_PREFIX}{slug}-{secrets.token_hex(3)}"
        info: dict[str, Any] = {
            "custom_llm_provider": spec.litellm_provider,
            MANAGED_FLAG: True,
            PROVIDER_FIELD: body.type,
            "display_name": body.name,
        }
        values: dict[str, Any] = {"api_key": body.api_key or "none"}
        if api_base:
            info["api_base"] = api_base
            values["api_base"] = api_base
        try:
            await self.gateway.create_credential(cid, info, values)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return next(p for p in await self.list_providers() if p.id == cid)

    async def update_provider(self, provider_id: str, body: ProviderUpdate) -> ProviderOut:
        cred = await self._credential(provider_id)
        info = dict(cred.get("credential_info") or {})
        spec = PROVIDERS.get(str(info.get(PROVIDER_FIELD)), PROVIDERS["openai_compatible"])
        values: dict[str, Any] = {}
        if body.name:
            others = [p for p in await self.list_providers() if p.id != provider_id]
            if any(p.name.lower() == body.name.lower() for p in others):
                raise CloudError("PROVIDER_NAME_TAKEN", 409)
            info["display_name"] = body.name
        if body.api_base is not None and spec.needs_api_base:
            base = _check_api_base(body.api_base)
            info["api_base"] = base
            values["api_base"] = base
        if body.api_key:
            values["api_key"] = body.api_key
        try:
            await self.gateway.update_credential(provider_id, info, values or None)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return next(p for p in await self.list_providers() if p.id == provider_id)

    async def delete_provider(self, provider_id: str) -> list[str]:
        await self._credential(provider_id)
        removed = []
        for m in await self.cloud_models_raw():
            info = m.get("model_info") or {}
            if info.get(PROVIDER_FIELD) == provider_id and info.get("id"):
                try:
                    await self.gateway.delete_model(str(info["id"]))
                except GatewayError as e:
                    raise _gateway_error(e) from e
                removed.append(str(m.get("model_name")))
        try:
            await self.gateway.delete_credential(provider_id)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return removed

    async def test(self, body: ConnTestIn, provider_id: str | None = None) -> ConnTestOut:
        if provider_id:
            cred = await self._credential(provider_id)
            ptype = str((cred.get("credential_info") or {}).get(PROVIDER_FIELD) or "openai_compatible")
            spec = PROVIDERS[ptype]
            model = body.model or spec.test_model or self._first_model(await self.cloud_models_raw(), provider_id)
            params: dict[str, Any] = {"litellm_credential_name": provider_id}
        else:
            if body.type is None:
                raise CloudError("PROVIDER_TYPE_REQUIRED", 422)
            spec = PROVIDERS[body.type]
            api_base = _check_api_base(body.api_base)
            if spec.needs_api_base and not api_base:
                raise CloudError("API_BASE_REQUIRED", 422)
            if spec.api_key_required and not body.api_key:
                raise CloudError("API_KEY_REQUIRED", 422)
            model = body.model or spec.test_model
            params = {"api_key": body.api_key or "none"}
            if api_base:
                params["api_base"] = api_base
        if not model:
            raise CloudError("TEST_MODEL_REQUIRED", 422)
        params["model"] = self._litellm_model(spec, model)
        try:
            resp = await self.gateway.test_connection(params)
        except GatewayError as e:
            if e.status_code is None:
                raise CloudError("GATEWAY_UNREACHABLE", 502) from e
            return ConnTestOut(ok=False, model=model, error=_short_error(str(e)))
        ok = resp.get("status") == "success"
        err = None if ok else _short_error(str((resp.get("result") or {}).get("error") or resp))
        return ConnTestOut(ok=ok, model=model, error=err)

    @staticmethod
    def _first_model(models: list[dict[str, Any]], provider_id: str) -> str | None:
        for m in models:
            info = m.get("model_info") or {}
            if info.get(PROVIDER_FIELD) == provider_id:
                return str(info.get("dgxsp_upstream") or "") or None
        return None

    @staticmethod
    def _litellm_model(spec: ProviderSpec, model: str) -> str:
        return model if model.startswith(spec.model_prefix) else f"{spec.model_prefix}{model}"

    # ------------------------------------------------------------------ catalog

    async def _costs(self) -> dict[str, Any]:
        if self._cost_map is None or time.monotonic() - self._cost_map_at > COST_MAP_TTL_S:
            try:
                self._cost_map = await self.gateway.cost_map()
                self._cost_map_at = time.monotonic()
            except GatewayError as e:
                if self._cost_map is None:
                    raise _gateway_error(e) from e
        return self._cost_map or {}

    async def catalog(self, ptype: ProviderType) -> list[CatalogModel]:
        spec = PROVIDERS[ptype]
        if not spec.catalog_provider:
            return []
        out = []
        for name, v in (await self._costs()).items():
            if not isinstance(v, dict) or v.get("litellm_provider") != spec.catalog_provider:
                continue
            if v.get("mode") != "chat" or name.startswith("ft:") or name == "sample_spec":
                continue
            mid = name.removeprefix(spec.model_prefix)
            out.append(
                CatalogModel(
                    id=mid,
                    input_per_mtok=_per_m(v.get("input_cost_per_token")),
                    output_per_mtok=_per_m(v.get("output_cost_per_token")),
                    max_input_tokens=v.get("max_input_tokens") if isinstance(v.get("max_input_tokens"), int) else None,
                )
            )
        return sorted(out, key=lambda m: m.id)

    async def _list_price(self, spec: ProviderSpec, model: str) -> tuple[float | None, float | None]:
        if not spec.catalog_provider:
            return None, None
        costs = await self._costs()
        v = costs.get(self._litellm_model(spec, model)) or costs.get(model)
        if not isinstance(v, dict):
            return None, None
        return _per_m(v.get("input_cost_per_token")), _per_m(v.get("output_cost_per_token"))

    # ------------------------------------------------------------------ cloud models

    async def list_models(self) -> list[CloudModelOut]:
        providers = {p.id: p for p in await self.list_providers()}
        out = []
        for m in await self.cloud_models_raw():
            info = m.get("model_info") or {}
            params = m.get("litellm_params") or {}
            pid = info.get(PROVIDER_FIELD)
            prov = providers.get(pid) if pid else None
            custom = bool(info.get("dgxsp_custom_price"))
            out.append(
                CloudModelOut(
                    id=str(info.get("id")),
                    name=str(m.get("model_name")),
                    model=str(info.get("dgxsp_upstream") or params.get("model") or ""),
                    provider_id=pid,
                    provider_name=prov.name if prov else None,
                    provider_type=prov.type if prov else None,
                    input_per_mtok=_per_m(_first(params, info, "input_cost_per_token")),
                    output_per_mtok=_per_m(_first(params, info, "output_cost_per_token")),
                    custom_price=custom,
                )
            )
        return sorted(out, key=lambda m: m.name.lower())

    async def add_model(self, body: CloudModelIn, taken: set[str]) -> CloudModelOut:
        cred = await self._credential(body.provider_id)
        ptype = str((cred.get("credential_info") or {}).get(PROVIDER_FIELD) or "openai_compatible")
        spec = PROVIDERS[ptype]
        upstream = body.model.removeprefix(spec.model_prefix) if body.model else ""
        if not upstream:
            raise CloudError("MODEL_REQUIRED", 422)
        name = body.name or upstream.split("/")[-1]
        if not NAME_RE.match(name):
            raise CloudError("NAME_INVALID", 422, {"name": name})
        existing = {m.name for m in await self.list_models()}
        if name in existing or name in taken:
            raise CloudError("NAME_DUPLICATE", 409, {"name": name})
        params: dict[str, Any] = {
            "model": self._litellm_model(spec, upstream),
            "litellm_credential_name": body.provider_id,
        }
        custom = body.input_per_mtok is not None or body.output_per_mtok is not None
        if custom:
            params["input_cost_per_token"] = (body.input_per_mtok or 0) / PER
            params["output_cost_per_token"] = (body.output_per_mtok or 0) / PER
        elif not spec.catalog_provider:
            params["input_cost_per_token"] = 0.0
            params["output_cost_per_token"] = 0.0
        info = {CLOUD_FLAG: True, PROVIDER_FIELD: body.provider_id, "dgxsp_upstream": upstream}
        if custom:
            info["dgxsp_custom_price"] = True
        try:
            mid = await self.gateway.add_model(name, params, info)
        except GatewayError as e:
            raise _gateway_error(e) from e
        return next(m for m in await self.list_models() if m.id == mid)

    async def delete_model(self, model_id: str) -> str:
        for m in await self.cloud_models_raw():
            if (m.get("model_info") or {}).get("id") == model_id:
                try:
                    await self.gateway.delete_model(model_id)
                except GatewayError as e:
                    raise _gateway_error(e) from e
                return str(m.get("model_name"))
        raise CloudError("CLOUD_MODEL_NOT_FOUND", 404)
