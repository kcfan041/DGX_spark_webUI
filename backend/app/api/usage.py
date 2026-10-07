from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.services.usage import LogPage, UsageError, UsageService, UsageSummary

router = APIRouter(prefix="/usage", tags=["usage"])


def _err(e: UsageError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code})


@router.get("/summary", response_model=UsageSummary)
async def summary(
    svc: Svc,
    _: CurrentPrincipal,
    start: date,
    end: date,
    tz: int | None = Query(None, ge=-840, le=840, description="JS getTimezoneOffset() minutes"),
) -> UsageSummary:
    try:
        return await UsageService(svc.litellm).summary(start, end, tz)
    except UsageError as e:
        raise _err(e) from e


@router.get("/logs", response_model=LogPage)
async def logs(
    svc: Svc,
    _: CurrentPrincipal,
    start: date,
    end: date,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(50, ge=1, le=200),
    model: str | None = None,
    key_id: str | None = None,
    status: Literal["success", "failure"] | None = None,
    tz: int | None = Query(None, ge=-840, le=840),
) -> LogPage:
    try:
        return await UsageService(svc.litellm).logs(start, end, page, page_size, model, key_id, status, tz)
    except UsageError as e:
        raise _err(e) from e
