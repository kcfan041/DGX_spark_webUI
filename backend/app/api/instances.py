from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import col, select

from app.core.security import CurrentPrincipal
from app.db.models import Instance
from app.db.session import DbSession
from app.domain.instance import GatewayState, InstanceStatus

router = APIRouter(prefix="/instances", tags=["instances"])


class InstanceOut(BaseModel):
    id: str
    display_name: str
    served_model_name: str
    model_id: str
    preset: str
    params: dict[str, Any]
    autostart: bool
    autostart_order: int
    status: InstanceStatus
    phase: str | None
    phase_started_at: datetime | None
    last_error: dict[str, Any] | None
    gateway_state: GatewayState
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[InstanceOut])
def list_instances(db: DbSession, _: CurrentPrincipal) -> list[Instance]:
    return list(db.exec(select(Instance).order_by(col(Instance.created_at))).all())


@router.get("/{instance_id}", response_model=InstanceOut)
def get_instance(instance_id: str, db: DbSession, _: CurrentPrincipal) -> Instance:
    inst = db.get(Instance, instance_id)
    if inst is None:
        raise HTTPException(status_code=404, detail={"code": "INSTANCE_NOT_FOUND"})
    return inst
