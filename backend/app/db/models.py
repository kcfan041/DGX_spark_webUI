import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.domain.instance import GatewayState, InstanceStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Instance(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    display_name: str
    served_model_name: str = Field(index=True, unique=True)
    model_id: str
    preset: str = "balanced"
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    autostart: bool = False
    autostart_order: int = 100

    status: InstanceStatus = InstanceStatus.CREATED
    phase: str | None = None
    phase_started_at: datetime | None = None
    last_error: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    container_id: str | None = None
    container_name: str | None = None
    gateway_state: GatewayState = GatewayState.NONE
    gateway_model_id: str | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Download(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    repo_id: str = Field(index=True)
    revision: str | None = None
    target_dir: str
    allow_patterns: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "queued"
    bytes_total: int | None = None
    bytes_done: int = 0
    files_total: int | None = None
    error: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SystemSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=utcnow)


class InstanceEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    instance_id: str = Field(index=True)
    type: str
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
