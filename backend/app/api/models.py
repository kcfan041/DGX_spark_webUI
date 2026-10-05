import asyncio

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.adapters.model_sources import ModelMeta, SourceInfo
from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.db.models import Instance
from app.db.session import DbSession

router = APIRouter(tags=["models"])


class ModelOut(ModelMeta):
    in_use_by: list[str] = []


def _usage(db: DbSession) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    for inst in db.exec(select(Instance)).all():
        usage.setdefault(inst.model_id, []).append(inst.id)
    return usage


@router.get("/models", response_model=list[ModelOut])
def list_models(svc: Svc, db: DbSession, _: CurrentPrincipal) -> list[ModelOut]:
    usage = _usage(db)
    return [ModelOut(**m.model_dump(), in_use_by=usage.get(m.id, [])) for m in svc.catalog.all()]


@router.get("/models/{model_id:path}", response_model=ModelOut)
def get_model(model_id: str, svc: Svc, db: DbSession, _: CurrentPrincipal) -> ModelOut:
    m = svc.catalog.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    return ModelOut(**m.model_dump(), in_use_by=_usage(db).get(m.id, []))


@router.get("/model-sources", response_model=list[SourceInfo])
def list_sources(svc: Svc, _: CurrentPrincipal) -> list[SourceInfo]:
    return svc.catalog.source_infos()


@router.post("/model-sources/rescan", response_model=list[SourceInfo])
async def rescan(svc: Svc, _: CurrentPrincipal) -> list[SourceInfo]:
    await asyncio.to_thread(svc.catalog.rescan)
    return svc.catalog.source_infos()
