import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from starlette.requests import Request

from app.core.settings import Settings
from app.db.settings_store import get_setting, set_setting

MODE_KEY = "api_base_mode"
MANUAL_KEY = "api_base_manual"

Mode = Literal["auto", "manual"]
Source = Literal["manual", "deploy", "auto"]


class ApiBaseInfo(BaseModel):
    effective: str
    source: Source
    mode: Mode | None
    manual: str | None
    deploy: str | None
    auto: str
    warnings: list[str] = Field(default_factory=list)


class ApiBaseError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize(value: str) -> str:
    v = value.strip().rstrip("/")
    parts = urlsplit(v)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ApiBaseError("API_BASE_INVALID")
    if parts.query or parts.fragment or any(c.isspace() for c in v):
        raise ApiBaseError("API_BASE_INVALID")
    try:
        _ = parts.port
    except ValueError as e:
        raise ApiBaseError("API_BASE_INVALID") from e
    return v


def is_local_host(host: str | None) -> bool:
    if not host:
        return True
    h = host.strip("[]").lower()
    if h == "localhost" or h.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def request_hostname(request: Request) -> str:
    raw = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    raw = raw.split(",")[0].strip()
    host = urlsplit(f"//{raw}").hostname if raw else None
    return host or "localhost"


def format_host(host: str) -> str:
    try:
        return f"[{host}]" if ipaddress.ip_address(host).version == 6 else host
    except ValueError:
        return host


def auto_base(request: Request, settings: Settings) -> str:
    return f"http://{format_host(request_hostname(request))}:{settings.gateway_port}/v1"


def resolve(request: Request, settings: Settings, engine: Engine) -> ApiBaseInfo:
    mode_raw = get_setting(engine, MODE_KEY)
    mode: Mode | None = "auto" if mode_raw == "auto" else "manual" if mode_raw == "manual" else None
    manual = get_setting(engine, MANUAL_KEY)
    deploy = settings.public_api_base.strip().rstrip("/") or None
    auto = auto_base(request, settings)

    effective: str
    source: Source
    if mode == "manual" and manual:
        effective, source = manual, "manual"
    elif mode == "auto":
        effective, source = auto, "auto"
    elif deploy:
        effective, source = deploy, "deploy"
    else:
        effective, source = auto, "auto"

    warnings: list[str] = []
    if is_local_host(urlsplit(effective).hostname):
        warnings.append("API_BASE_LOCALHOST")
    if is_local_host(settings.gateway_bind):
        warnings.append("GATEWAY_LOCAL_BIND")
    if not urlsplit(effective).path.rstrip("/").endswith("/v1"):
        warnings.append("API_BASE_NOT_V1")

    return ApiBaseInfo(
        effective=effective,
        source=source,
        mode=mode,
        manual=manual,
        deploy=deploy,
        auto=auto,
        warnings=warnings,
    )


def update(engine: Engine, mode: Mode | None, value: str | None) -> None:
    if mode == "manual":
        if not value:
            raise ApiBaseError("API_BASE_INVALID")
        set_setting(engine, MANUAL_KEY, normalize(value))
        set_setting(engine, MODE_KEY, "manual")
    elif mode == "auto":
        set_setting(engine, MODE_KEY, "auto")
    else:
        set_setting(engine, MODE_KEY, None)
