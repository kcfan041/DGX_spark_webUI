from typing import Annotated

from fastapi import Depends, Request

from app.services import api_base
from app.services.container import Services, get_services

Svc = Annotated[Services, Depends(get_services)]


def get_public_api_base(request: Request, svc: Svc) -> str:
    return api_base.resolve(request, svc.settings, request.app.state.engine).effective


PublicApiBase = Annotated[str, Depends(get_public_api_base)]
