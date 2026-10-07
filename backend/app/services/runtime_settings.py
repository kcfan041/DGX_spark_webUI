"""Settings that can be changed from the Web Console at runtime.

Precedence: value stored from the Web Console (SystemSetting) > deploy/.env or runtime profile > built-in default.
"""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.core.logging import configure_logging
from app.core.settings import Settings
from app.db.settings_store import get_setting, set_setting
from app.profiles import RuntimeProfile

Source = Literal["web", "deploy", "default"]

VERBOSE_KEY = "verbose_access_log"
HF_ENDPOINT_KEY = "hf_endpoint"
HEALTH_TIMEOUT_KEY = "health_timeout_min"

TIMEOUT_MIN_MINUTES = 15
TIMEOUT_MAX_MINUTES = 120
SLOW_WARNING_MIN_S = 300


class SettingError(ValueError):
    def __init__(self, code: str, field: str) -> None:
        super().__init__(code)
        self.code = code
        self.field = field


class Value(BaseModel):
    value: bool | str | int | None
    source: Source
    default: bool | str | int | None


def normalize_endpoint(v: str) -> str:
    v = v.strip().rstrip("/")
    parts = urlsplit(v)
    if parts.scheme not in ("http", "https") or not parts.hostname or any(c.isspace() for c in v):
        raise SettingError("HF_ENDPOINT_INVALID", "hf_endpoint")
    return v


class RuntimeSettings:
    def __init__(self, engine: Engine, settings: Settings, profile: RuntimeProfile) -> None:
        self.engine = engine
        self.settings = settings
        self.profile = profile

    # ---------------------------------------------------------------- verbose access log

    def verbose(self) -> Value:
        default = self.settings.verbose_access_log
        raw = get_setting(self.engine, VERBOSE_KEY)
        if raw in ("0", "1"):
            return Value(value=raw == "1", source="web", default=default)
        return Value(value=default, source="deploy" if default else "default", default=default)

    def set_verbose(self, value: bool | None) -> None:
        set_setting(self.engine, VERBOSE_KEY, None if value is None else ("1" if value else "0"))
        self.apply_logging()

    def apply_logging(self) -> None:
        configure_logging(bool(self.verbose().value))

    # ---------------------------------------------------------------- HF endpoint

    def hf_endpoint(self) -> Value:
        default = self.settings.hf_endpoint
        raw = get_setting(self.engine, HF_ENDPOINT_KEY)
        if raw is not None:
            return Value(value=raw or None, source="web", default=default)
        return Value(value=default, source="deploy" if default else "default", default=default)

    def hf_endpoint_value(self) -> str | None:
        v = self.hf_endpoint().value
        return v if isinstance(v, str) and v else None

    def set_hf_endpoint(self, value: str | None, clear: bool = False) -> None:
        if clear:
            set_setting(self.engine, HF_ENDPOINT_KEY, None)
            return
        set_setting(self.engine, HF_ENDPOINT_KEY, normalize_endpoint(value) if value and value.strip() else "")

    # ---------------------------------------------------------------- health timeout

    def health_timeout(self) -> Value:
        default_min = max(TIMEOUT_MIN_MINUTES, round(self.profile.timeouts.health_s / 60))
        raw = get_setting(self.engine, HEALTH_TIMEOUT_KEY)
        if raw and raw.isdigit():
            return Value(value=int(raw), source="web", default=default_min)
        return Value(value=default_min, source="default", default=default_min)

    def health_timeout_s(self) -> int:
        return int(self.health_timeout().value or TIMEOUT_MIN_MINUTES) * 60

    def slow_warning_s(self) -> int:
        return max(SLOW_WARNING_MIN_S, self.health_timeout_s() // 3)

    def set_health_timeout(self, minutes: int | None) -> None:
        if minutes is None:
            set_setting(self.engine, HEALTH_TIMEOUT_KEY, None)
            return
        if not TIMEOUT_MIN_MINUTES <= minutes <= TIMEOUT_MAX_MINUTES:
            raise SettingError("TIMEOUT_OUT_OF_RANGE", "health_timeout_min")
        set_setting(self.engine, HEALTH_TIMEOUT_KEY, str(minutes))
