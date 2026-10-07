from fastapi import APIRouter, HTTPException, status

from app.api.deps import Svc
from app.core.security import CurrentPrincipal
from app.services.cloud import (
    PROVIDERS,
    CatalogModel,
    CloudError,
    CloudModelIn,
    CloudModelOut,
    ConnTestIn,
    ConnTestOut,
    ProviderIn,
    ProviderOut,
    ProviderSpec,
    ProviderType,
    ProviderUpdate,
)
from app.services.routing import FallbackIn, RetriesIn, RoutingError, RoutingOut

router = APIRouter(prefix="/cloud", tags=["cloud"])


def _err(e: CloudError | RoutingError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"code": e.code, "params": e.params})


@router.get("/provider-types", response_model=list[ProviderSpec])
def provider_types(_: CurrentPrincipal) -> list[ProviderSpec]:
    return list(PROVIDERS.values())


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(svc: Svc, _: CurrentPrincipal) -> list[ProviderOut]:
    try:
        return await svc.cloud.list_providers()
    except CloudError as e:
        raise _err(e) from e


@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(body: ProviderIn, svc: Svc, _: CurrentPrincipal) -> ProviderOut:
    try:
        return await svc.cloud.create_provider(body)
    except CloudError as e:
        raise _err(e) from e


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderUpdate, svc: Svc, _: CurrentPrincipal) -> ProviderOut:
    try:
        return await svc.cloud.update_provider(provider_id, body)
    except CloudError as e:
        raise _err(e) from e


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, svc: Svc, _: CurrentPrincipal) -> dict[str, list[str]]:
    try:
        removed = await svc.cloud.delete_provider(provider_id)
    except CloudError as e:
        raise _err(e) from e
    for name in removed:
        await svc.routing.remove_model_references(name)
    return {"removed_models": removed}


@router.post("/test", response_model=ConnTestOut)
async def test_new(body: ConnTestIn, svc: Svc, _: CurrentPrincipal) -> ConnTestOut:
    try:
        return await svc.cloud.test(body)
    except CloudError as e:
        raise _err(e) from e


@router.post("/providers/{provider_id}/test", response_model=ConnTestOut)
async def test_saved(provider_id: str, body: ConnTestIn, svc: Svc, _: CurrentPrincipal) -> ConnTestOut:
    try:
        return await svc.cloud.test(body, provider_id)
    except CloudError as e:
        raise _err(e) from e


@router.get("/catalog/{ptype}", response_model=list[CatalogModel])
async def catalog(ptype: ProviderType, svc: Svc, _: CurrentPrincipal) -> list[CatalogModel]:
    try:
        return await svc.cloud.catalog(ptype)
    except CloudError as e:
        raise _err(e) from e


@router.get("/models", response_model=list[CloudModelOut])
async def list_models(svc: Svc, _: CurrentPrincipal) -> list[CloudModelOut]:
    try:
        return await svc.cloud.list_models()
    except CloudError as e:
        raise _err(e) from e


@router.post("/models", response_model=CloudModelOut, status_code=status.HTTP_201_CREATED)
async def add_model(body: CloudModelIn, svc: Svc, _: CurrentPrincipal) -> CloudModelOut:
    taken = {i.served_model_name for i in svc.manager.all()}
    try:
        out = await svc.cloud.add_model(body, taken)
    except CloudError as e:
        raise _err(e) from e
    await svc.routing.sync_aliases()
    return out


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: str, svc: Svc, _: CurrentPrincipal) -> None:
    try:
        name = await svc.cloud.delete_model(model_id)
    except CloudError as e:
        raise _err(e) from e
    await svc.routing.remove_model_references(name)


# ---------------------------------------------------------------- routing (fallback / retries)


@router.get("/routing", response_model=RoutingOut)
async def get_routing(svc: Svc, _: CurrentPrincipal) -> RoutingOut:
    try:
        return await svc.routing.get()
    except RoutingError as e:
        raise _err(e) from e


@router.put("/routing/fallbacks", response_model=RoutingOut)
async def set_fallback(body: FallbackIn, svc: Svc, _: CurrentPrincipal) -> RoutingOut:
    try:
        return await svc.routing.set_fallback(body)
    except RoutingError as e:
        raise _err(e) from e


@router.put("/routing/retries", response_model=RoutingOut)
async def set_retries(body: RetriesIn, svc: Svc, _: CurrentPrincipal) -> RoutingOut:
    try:
        return await svc.routing.set_retries(body)
    except RoutingError as e:
        raise _err(e) from e
