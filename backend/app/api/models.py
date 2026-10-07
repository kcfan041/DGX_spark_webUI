import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.adapters.model_sources import ModelMeta, SourceInfo, parse_config
from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.db.models import Instance
from app.db.session import DbSession
from app.services.presets import ResolvedPreset

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


class ModelFile(BaseModel):
    name: str
    size: int


class ModelDetails(BaseModel):
    model: ModelOut
    config: dict[str, Any]
    files: list[ModelFile]
    presets: list[ResolvedPreset]


CONFIG_KEYS = (
    "architectures",
    "model_type",
    "torch_dtype",
    "hidden_size",
    "num_hidden_layers",
    "num_attention_heads",
    "num_key_value_heads",
    "head_dim",
    "intermediate_size",
    "vocab_size",
    "max_position_embeddings",
    "rope_scaling",
    "sliding_window",
    "quantization_config",
    "tie_word_embeddings",
)


def _model_dir(svc: Svc, m: ModelMeta) -> Path | None:
    if m.source == "local":
        return svc.settings.model_root / m.container_subpath
    if m.source == "hf_cache" and svc.settings.hf_cache_dir:
        return svc.settings.hf_cache_dir / m.container_subpath
    return None


def _details(svc: Svc, m: ModelMeta, in_use: list[str]) -> ModelDetails:
    d = _model_dir(svc, m)
    cfg = parse_config(d) if d and d.is_dir() else {}
    text_cfg = cfg.get("text_config")
    src: dict[str, Any] = text_cfg if isinstance(text_cfg, dict) else cfg
    picked = {k: src.get(k, cfg.get(k)) for k in CONFIG_KEYS if src.get(k, cfg.get(k)) is not None}
    files: list[ModelFile] = []
    if d and d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_file():
                with contextlib.suppress(OSError):
                    files.append(ModelFile(name=p.name, size=p.stat().st_size))
    return ModelDetails(
        model=ModelOut(**m.model_dump(), in_use_by=in_use),
        config=picked,
        files=files[:200],
        presets=svc.presets.resolve_all(m),
    )


@router.get("/model-details/{model_id:path}", response_model=ModelDetails)
async def model_details(model_id: str, svc: Svc, db: DbSession, _: CurrentPrincipal) -> ModelDetails:
    m = svc.catalog.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    return await asyncio.to_thread(_details, svc, m, _usage(db).get(m.id, []))


@router.get("/model-sources", response_model=list[SourceInfo])
def list_sources(svc: Svc, _: CurrentPrincipal) -> list[SourceInfo]:
    return svc.catalog.source_infos()


@router.post("/model-sources/rescan", response_model=list[SourceInfo])
async def rescan(svc: Svc, _: CurrentPrincipal) -> list[SourceInfo]:
    await asyncio.to_thread(svc.catalog.rescan)
    return svc.catalog.source_infos()
