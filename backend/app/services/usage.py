from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from app.adapters.litellm_client import GatewayError
from app.services.api_keys import CREATED_BY, PURPOSE_SYSTEM
from app.services.ports import GatewayPort

MAX_DAYS = 90
KeyKind = Literal["key", "revoked", "system", "admin", "unknown"]
MASTER = "litellm_proxy_master_key"
INTERNAL_PREFIX = "litellm-internal"


class UsageError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class Metrics(BaseModel):
    requests: int = 0
    successful: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    spend: float = 0.0


class Row(BaseModel):
    id: str
    label: str
    kind: Literal["model"] | KeyKind = "model"
    metrics: Metrics


class Day(BaseModel):
    date: str
    metrics: Metrics


class UsageSummary(BaseModel):
    start: str
    end: str
    totals: Metrics
    days: list[Day]
    by_model: list[Row]
    by_key: list[Row]


class LogRow(BaseModel):
    request_id: str
    time: str | None
    model: str | None
    key_name: str | None
    status: str
    prompt_tokens: int
    completion_tokens: int
    spend: float
    duration_ms: int | None


class LogPage(BaseModel):
    items: list[LogRow]
    page: int
    total_pages: int
    total: int
    capped: bool


def _metrics(m: dict[str, Any] | None) -> Metrics:
    m = m or {}
    return Metrics(
        requests=int(m.get("api_requests") or 0),
        successful=int(m.get("successful_requests") or 0),
        failed=int(m.get("failed_requests") or 0),
        prompt_tokens=int(m.get("prompt_tokens") or 0),
        completion_tokens=int(m.get("completion_tokens") or 0),
        total_tokens=int(m.get("total_tokens") or 0),
        spend=float(m.get("spend") or 0.0),
    )


def _add(a: Metrics, b: Metrics) -> Metrics:
    return Metrics(**{k: getattr(a, k) + getattr(b, k) for k in Metrics.model_fields})


def _range(start: date, end: date) -> None:
    if end < start:
        raise UsageError("RANGE_INVALID", 422)
    if (end - start).days >= MAX_DAYS:
        raise UsageError("RANGE_TOO_LONG", 422)


class UsageService:
    def __init__(self, gateway: GatewayPort) -> None:
        self.gateway = gateway

    async def _key_names(self) -> dict[str, tuple[str, KeyKind]]:
        names: dict[str, tuple[str, KeyKind]] = {}
        try:
            keys = await self.gateway.list_keys()
        except GatewayError:
            return names
        for k in keys:
            md = k.get("metadata") or {}
            token = str(k.get("token") or "")
            if not token:
                continue
            if md.get("created_by") == CREATED_BY and md.get("purpose") == PURPOSE_SYSTEM:
                names[token] = ("", "system")
            else:
                label = str(md.get("display_name") or k.get("key_alias") or k.get("key_name") or "")
                names[token] = (label, "revoked" if k.get("blocked") else "key")
        return names

    async def summary(self, start: date, end: date, tz_offset_min: int | None) -> UsageSummary:
        _range(start, end)
        try:
            data = await self.gateway.daily_activity(start.isoformat(), end.isoformat(), tz_offset_min)
        except GatewayError as e:
            raise UsageError("GATEWAY_UNREACHABLE" if e.status_code is None else "GATEWAY_REQUEST_FAILED", 502) from e
        names = await self._key_names()
        totals = Metrics()
        kind: KeyKind
        per_day: dict[str, Metrics] = {}
        models: dict[str, Metrics] = {}
        keys: dict[str, Metrics] = {}
        key_meta: dict[str, dict[str, Any]] = {}
        for r in data.get("results", []):
            ds = str(r.get("date"))
            m = _metrics(r.get("metrics"))
            totals = _add(totals, m)
            per_day[ds] = _add(per_day.get(ds, Metrics()), m)
            br = r.get("breakdown") or {}
            for name, v in (br.get("model_groups") or {}).items():
                models[name] = _add(models.get(name, Metrics()), _metrics((v or {}).get("metrics")))
            for token, v in (br.get("api_keys") or {}).items():
                keys[token] = _add(keys.get(token, Metrics()), _metrics((v or {}).get("metrics")))
                key_meta.setdefault(token, (v or {}).get("metadata") or {})
        days = []
        d = start
        while d <= end:
            days.append(Day(date=d.isoformat(), metrics=per_day.get(d.isoformat(), Metrics())))
            d += timedelta(days=1)
        by_key = []
        for token, m in keys.items():
            label, kind = names.get(token, ("", "unknown"))
            if token == MASTER:
                kind = "admin"
            elif token.startswith(INTERNAL_PREFIX):
                kind = "system"
            elif not label and kind != "system":
                label = str(key_meta.get(token, {}).get("key_alias") or "")
            by_key.append(Row(id=token, label=label, kind=kind, metrics=m))
        return UsageSummary(
            start=start.isoformat(),
            end=end.isoformat(),
            totals=totals,
            days=days,
            by_model=sorted(
                (Row(id=k, label=k, metrics=m) for k, m in models.items()), key=lambda r: -r.metrics.total_tokens
            ),
            by_key=sorted(by_key, key=lambda r: -r.metrics.total_tokens),
        )

    async def logs(
        self,
        start: date,
        end: date,
        page: int,
        page_size: int,
        model: str | None,
        key_id: str | None,
        status: str | None,
        tz_offset_min: int | None = None,
    ) -> LogPage:
        _range(start, end)
        shift = timedelta(minutes=tz_offset_min or 0)
        start_utc = datetime.combine(start, time.min) + shift
        end_utc = datetime.combine(end, time.max).replace(microsecond=0) + shift
        params: dict[str, Any] = {
            "start_date": start_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "end_date": end_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "page": page,
            "page_size": page_size,
            "sort_by": "startTime",
            "sort_order": "desc",
            "exclude_internal_health_checks": "true",
        }
        if model:
            params["model_group"] = model
        if key_id:
            params["api_key"] = key_id
        if status in ("success", "failure"):
            params["status_filter"] = status
        try:
            data = await self.gateway.spend_logs(params)
        except GatewayError as e:
            raise UsageError("GATEWAY_UNREACHABLE" if e.status_code is None else "GATEWAY_REQUEST_FAILED", 502) from e
        names = await self._key_names()
        items = []
        for r in data.get("data", []) or []:
            md = r.get("metadata") or {}
            token = str(r.get("api_key") or "")
            label, kind = names.get(token, ("", "unknown"))
            if token == MASTER:
                label = "admin"
            elif kind == "system" or token.startswith(INTERNAL_PREFIX):
                label = "system"
            items.append(
                LogRow(
                    request_id=str(r.get("request_id") or ""),
                    time=r.get("startTime"),
                    model=r.get("model_group") or r.get("model"),
                    key_name=label or md.get("user_api_key_alias") or None,
                    status=str(r.get("status") or md.get("status") or "success"),
                    prompt_tokens=int(r.get("prompt_tokens") or 0),
                    completion_tokens=int(r.get("completion_tokens") or 0),
                    spend=float(r.get("spend") or 0.0),
                    duration_ms=r.get("request_duration_ms"),
                )
            )
        return LogPage(
            items=items,
            page=int(data.get("page") or page),
            total_pages=int(data.get("total_pages") or 0),
            total=int(data.get("total") or 0),
            capped=bool(data.get("total_is_capped")),
        )
