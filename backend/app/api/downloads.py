import asyncio
import shutil

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.db.models import Instance
from app.db.session import DbSession
from app.db.settings_store import get_setting, set_setting
from app.services.container import HF_TOKEN_KEY
from app.services.downloads import DownloadError, DownloadOut, DownloadPreview

router = APIRouter(tags=["downloads"])


class DownloadRequest(BaseModel):
    repo_id: str = Field(min_length=3, max_length=200)
    target_dir: str | None = Field(default=None, max_length=128)
    revision: str | None = Field(default=None, max_length=100)


class HfTokenStatus(BaseModel):
    configured: bool
    source: str | None


class HfTokenUpdate(BaseModel):
    token: str | None = Field(default=None, max_length=500)


def _err(e: DownloadError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "params": e.params})


@router.post("/downloads/preview", response_model=DownloadPreview)
async def preview(body: DownloadRequest, svc: Svc, _: CurrentPrincipal) -> DownloadPreview:
    try:
        return await asyncio.to_thread(svc.downloads.preview, body.repo_id, body.target_dir, body.revision)
    except DownloadError as e:
        raise _err(e) from e


@router.get("/downloads", response_model=list[DownloadOut])
def list_downloads(svc: Svc, _: CurrentPrincipal) -> list[DownloadOut]:
    return [svc.downloads.out(d) for d in svc.downloads.all()]


@router.post("/downloads", response_model=DownloadOut, status_code=status.HTTP_201_CREATED)
async def create(body: DownloadRequest, svc: Svc, _: CurrentPrincipal) -> DownloadOut:
    try:
        d = await asyncio.to_thread(svc.downloads.create, body.repo_id, body.target_dir, body.revision)
    except DownloadError as e:
        raise _err(e) from e
    return svc.downloads.out(d)


@router.post("/downloads/{download_id}/cancel", response_model=DownloadOut)
async def cancel(download_id: str, svc: Svc, _: CurrentPrincipal) -> DownloadOut:
    try:
        return svc.downloads.out(await svc.downloads.cancel(download_id))
    except DownloadError as e:
        raise _err(e) from e


@router.post("/downloads/{download_id}/retry", response_model=DownloadOut)
def retry(download_id: str, svc: Svc, _: CurrentPrincipal) -> DownloadOut:
    try:
        return svc.downloads.out(svc.downloads.retry(download_id))
    except DownloadError as e:
        raise _err(e) from e


@router.delete("/downloads/{download_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(download_id: str, svc: Svc, _: CurrentPrincipal) -> None:
    try:
        svc.downloads.delete(download_id)
    except DownloadError as e:
        raise _err(e) from e


@router.delete("/models/{model_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: str, svc: Svc, db: DbSession, _: CurrentPrincipal) -> None:
    m = svc.catalog.get(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND"})
    if m.source != "local":
        raise HTTPException(status_code=409, detail={"code": "MODEL_NOT_DELETABLE"})
    users = [i.display_name for i in db.exec(select(Instance).where(Instance.model_id == model_id)).all()]
    if users:
        raise HTTPException(status_code=409, detail={"code": "MODEL_IN_USE", "params": {"services": users}})
    root = svc.settings.model_root.resolve()
    target = (svc.settings.model_root / m.locator).resolve()
    if root not in target.parents:
        raise HTTPException(status_code=409, detail={"code": "MODEL_NOT_DELETABLE"})
    top = target.relative_to(root).parts[0]
    if svc.downloads.is_busy(top) or svc.downloads.is_busy(top.removeprefix(".").removesuffix(".partial")):
        raise HTTPException(status_code=409, detail={"code": "DOWNLOAD_ACTIVE"})
    try:
        await asyncio.to_thread(shutil.rmtree, target)
    except FileNotFoundError:
        pass  # already gone (e.g. a cancelled download cleaned it up): just refresh the list
    except PermissionError as e:
        await asyncio.to_thread(svc.catalog.rescan)
        raise HTTPException(
            status_code=500, detail={"code": "MODEL_DELETE_PERMISSION", "params": {"error": str(e)[:300]}}
        ) from e
    except OSError as e:
        await asyncio.to_thread(svc.catalog.rescan)
        raise HTTPException(
            status_code=500, detail={"code": "MODEL_DELETE_FAILED", "params": {"error": str(e)[:300]}}
        ) from e
    await asyncio.to_thread(svc.catalog.rescan)


@router.get("/settings/hf-token", response_model=HfTokenStatus)
def hf_token_status(request: Request, svc: Svc, _: CurrentPrincipal) -> HfTokenStatus:
    if get_setting(request.app.state.engine, HF_TOKEN_KEY):
        return HfTokenStatus(configured=True, source="web")
    if svc.settings.hf_token.get_secret_value():
        return HfTokenStatus(configured=True, source="deploy")
    return HfTokenStatus(configured=False, source=None)


@router.put("/settings/hf-token", response_model=HfTokenStatus)
def set_hf_token(body: HfTokenUpdate, request: Request, svc: Svc, p: CurrentPrincipal) -> HfTokenStatus:
    value = (body.token or "").strip() or None
    set_setting(request.app.state.engine, HF_TOKEN_KEY, value)
    return hf_token_status(request, svc, p)
