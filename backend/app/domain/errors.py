from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    OOM = "OOM"
    MEMORY_PRECHECK = "MEMORY_PRECHECK"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    MODEL_UNSUPPORTED = "MODEL_UNSUPPORTED"
    REMOTE_CODE_REQUIRED = "REMOTE_CODE_REQUIRED"
    HEALTH_TIMEOUT = "HEALTH_TIMEOUT"
    CRASHED = "CRASHED"
    PORT_CONFLICT = "PORT_CONFLICT"
    IMAGE_UNAVAILABLE = "IMAGE_UNAVAILABLE"
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE"
    DOCKER_UNAVAILABLE = "DOCKER_UNAVAILABLE"
    CONTAINER_MISSING = "CONTAINER_MISSING"
    GATEWAY_UNREACHABLE = "GATEWAY_UNREACHABLE"
    GATEWAY_REGISTER_FAILED = "GATEWAY_REGISTER_FAILED"
    GATEWAY_MODEL_NOT_FOUND = "GATEWAY_MODEL_NOT_FOUND"
    GATEWAY_PORT_IN_USE = "GATEWAY_PORT_IN_USE"
    TEST_TIMEOUT = "TEST_TIMEOUT"
    AUTOSTART_SKIPPED_MEMORY = "AUTOSTART_SKIPPED_MEMORY"
    UNKNOWN = "UNKNOWN"


class Suggestion(BaseModel):
    action: str
    label_key: str
    patch: dict[str, Any] | None = None
    preset: str | None = None
    target: str | None = None


class InstanceError(BaseModel):
    code: ErrorCode
    severity: str = "error"
    params: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    occurred_at: datetime
