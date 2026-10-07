import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.adapters.litellm_client import GatewayError
from app.db.settings_store import get_setting, set_setting
from app.services.ports import GatewayPort

log = logging.getLogger(__name__)

ALIAS_KEY = "routing_managed_aliases"
MAX_RETRIES = 5
MAX_TARGETS = 5


class RoutingError(Exception):
    def __init__(self, code: str, status: int = 400, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.params = params or {}


class FallbackRule(BaseModel):
    model: str
    targets: list[str]
    active_alias: str | None = None


class RoutingOut(BaseModel):
    fallbacks: list[FallbackRule]
    num_retries: int | None
    models: list[str]


class FallbackIn(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    targets: list[str] = Field(default_factory=list, max_length=MAX_TARGETS)


class RetriesIn(BaseModel):
    num_retries: int = Field(ge=0, le=MAX_RETRIES)


def _parse_fallbacks(raw: Any) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in raw or []:
        if isinstance(item, dict):
            for k, v in item.items():
                if isinstance(v, list):
                    out[str(k)] = [str(x) for x in v]
    return out


class RoutingService:
    """Fallbacks are stored in LiteLLM router_settings (DB-backed via /config/update).

    LiteLLM only falls back when the model group exists. A stopped local service is removed from the
    gateway, so requests would fail with "invalid model". To cover that case we point a model_group_alias
    from the missing name to its first fallback target while (and only while) the model is not registered.
    """

    def __init__(
        self,
        engine: Engine,
        gateway: GatewayPort,
        local_names: Callable[[], set[str]],
        registered_names: Callable[[], set[str]],
        interval: float = 10.0,
    ) -> None:
        self.engine = engine
        self.gateway = gateway
        self.local_names = local_names
        self.registered_names = registered_names
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def _managed_aliases(self) -> set[str]:
        raw = get_setting(self.engine, ALIAS_KEY)
        try:
            return set(json.loads(raw)) if raw else set()
        except ValueError:
            return set()

    def _set_managed_aliases(self, names: set[str]) -> None:
        set_setting(self.engine, ALIAS_KEY, json.dumps(sorted(names)) if names else None)

    async def _settings(self) -> dict[str, Any]:
        try:
            return await self.gateway.router_settings()
        except GatewayError as e:
            raise RoutingError("GATEWAY_UNREACHABLE" if e.status_code is None else "GATEWAY_REQUEST_FAILED", 502) from e

    async def _gateway_models(self) -> set[str]:
        try:
            return {str(m.get("model_name")) for m in await self.gateway.list_models() if m.get("model_name")}
        except GatewayError as e:
            raise RoutingError("GATEWAY_UNREACHABLE" if e.status_code is None else "GATEWAY_REQUEST_FAILED", 502) from e

    async def get(self) -> RoutingOut:
        rs = await self._settings()
        fallbacks = _parse_fallbacks(rs.get("fallbacks"))
        aliases = rs.get("model_group_alias") or {}
        managed = self._managed_aliases()
        names = (await self._gateway_models()) | self.local_names()
        rules = [
            FallbackRule(model=k, targets=v, active_alias=aliases.get(k) if k in managed else None)
            for k, v in sorted(fallbacks.items())
        ]
        retries = rs.get("num_retries")
        return RoutingOut(
            fallbacks=rules, num_retries=int(retries) if isinstance(retries, int) else None, models=sorted(names)
        )

    async def set_fallback(self, body: FallbackIn) -> RoutingOut:
        async with self._lock:
            rs = await self._settings()
            fallbacks = _parse_fallbacks(rs.get("fallbacks"))
            targets = list(dict.fromkeys(t.strip() for t in body.targets if t.strip()))
            if targets:
                known = (await self._gateway_models()) | self.local_names()
                if body.model not in known:
                    raise RoutingError("ROUTING_MODEL_UNKNOWN", 422, {"name": body.model})
                bad = [t for t in targets if t not in known or t == body.model]
                if bad:
                    raise RoutingError("ROUTING_TARGET_INVALID", 422, {"names": bad})
                fallbacks[body.model] = targets
            else:
                fallbacks.pop(body.model, None)
            try:
                await self.gateway.update_router_settings({"fallbacks": [{k: v} for k, v in sorted(fallbacks.items())]})
            except GatewayError as e:
                raise RoutingError("GATEWAY_REQUEST_FAILED", 502, {"detail": str(e)[:300]}) from e
        await self.sync_aliases()
        return await self.get()

    async def set_retries(self, body: RetriesIn) -> RoutingOut:
        try:
            await self.gateway.update_router_settings({"num_retries": body.num_retries})
        except GatewayError as e:
            raise RoutingError("GATEWAY_REQUEST_FAILED", 502, {"detail": str(e)[:300]}) from e
        return await self.get()

    async def remove_model_references(self, name: str) -> None:
        """Drop rules that use `name` (as source or target) after a cloud model is deleted."""
        async with self._lock:
            try:
                rs = await self.gateway.router_settings()
            except GatewayError:
                return
            fallbacks = _parse_fallbacks(rs.get("fallbacks"))
            changed: dict[str, list[str]] = {}
            for k, v in fallbacks.items():
                if k == name:
                    continue
                kept = [t for t in v if t != name]
                if kept:
                    changed[k] = kept
            if changed != fallbacks:
                with contextlib.suppress(GatewayError):
                    await self.gateway.update_router_settings(
                        {"fallbacks": [{k: v} for k, v in sorted(changed.items())]}
                    )
        await self.sync_aliases()

    async def sync_aliases(self) -> bool:
        async with self._lock:
            try:
                rs = await self.gateway.router_settings()
            except GatewayError:
                return False
            fallbacks = _parse_fallbacks(rs.get("fallbacks"))
            current: dict[str, str] = dict(rs.get("model_group_alias") or {})
            managed = self._managed_aliases()
            local = self.local_names()
            registered = self.registered_names()
            desired: dict[str, str] = {}
            for src, targets in fallbacks.items():
                if src in local and src not in registered and targets:
                    desired[src] = targets[0]
            new = {k: v for k, v in current.items() if k not in managed}
            new.update(desired)
            if new == current and set(desired) == managed:
                return False
            try:
                await self.gateway.update_router_settings({"model_group_alias": new})
            except GatewayError as e:
                log.warning("alias sync failed: %s", e)
                return False
            self._set_managed_aliases(set(desired))
            log.info("fallback aliases now %s", desired)
            return True

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.sync_aliases()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("alias sync failed")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="routing-sync")

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
