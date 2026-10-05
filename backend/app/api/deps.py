from typing import Annotated

from fastapi import Depends

from app.services.container import Services, get_services

Svc = Annotated[Services, Depends(get_services)]
