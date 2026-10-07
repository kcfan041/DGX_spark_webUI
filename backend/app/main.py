import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import auth, downloads, gateway, instances, logs, models, system
from app.api import settings as settings_api
from app.core.security import build_auth_provider
from app.core.settings import Settings, get_settings
from app.db.session import build_engine, init_db
from app.services.container import build_services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dgxsp")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = build_engine(settings.db_url)
        init_db(engine)
        app.state.engine = engine
        services = build_services(settings, engine)
        app.state.services = services
        app.state.auth_provider = build_auth_provider()
        if not settings.admin_token.get_secret_value():
            log.warning("DGXSP_ADMIN_TOKEN is empty: all authenticated endpoints will reject requests")
        if settings.manager_enabled:
            await services.manager.startup()
            await services.downloads.startup()
        log.info("started profile=%s image=%s", settings.profile, services.profile.vllm.image)
        try:
            yield
        finally:
            await services.aclose()
            engine.dispose()

    app = FastAPI(title="DGX Spark LLM Control Platform", version=__version__, lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(system.router)
    api.include_router(downloads.router)
    api.include_router(models.router)
    api.include_router(instances.router)
    api.include_router(gateway.router)
    api.include_router(logs.router)
    api.include_router(settings_api.router)
    app.include_router(api)
    return app


app = create_app()
