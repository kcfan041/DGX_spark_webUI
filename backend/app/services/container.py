from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from sqlalchemy.engine import Engine

from app.adapters.docker_runtime import DockerRuntime
from app.adapters.litellm_client import LiteLLMClient
from app.adapters.metrics import MetricsProvider
from app.adapters.model_sources import HFCacheSource, LocalDirSource, ModelCatalog, ModelSource
from app.core.settings import Settings
from app.db.settings_store import get_setting
from app.domain.instance import GatewayState, InstanceStatus
from app.profiles import RuntimeProfile, load_profile
from app.services.cloud import CloudService
from app.services.downloads import DownloadManager, Fetcher, HFHubClient
from app.services.error_classifier import ErrorClassifier
from app.services.instance_manager import InstanceManager
from app.services.planner import Planner
from app.services.presets import PresetResolver
from app.services.probe import VllmProbe
from app.services.routing import RoutingService
from app.services.runtime_settings import RuntimeSettings

HF_TOKEN_KEY = "hf_token"


@dataclass
class Services:
    settings: Settings
    profile: RuntimeProfile
    docker: DockerRuntime
    litellm: LiteLLMClient
    catalog: ModelCatalog
    metrics: MetricsProvider
    presets: PresetResolver
    planner: Planner
    classifier: ErrorClassifier
    probe: VllmProbe
    manager: InstanceManager
    downloads: DownloadManager
    runtime: RuntimeSettings
    hub: HFHubClient
    cloud: CloudService
    routing: RoutingService

    async def aclose(self) -> None:
        await self.routing.shutdown()
        await self.downloads.shutdown()
        await self.manager.shutdown()
        await self.probe.aclose()
        await self.litellm.aclose()


def build_services(settings: Settings, engine: Engine) -> Services:
    profile = load_profile(settings.config_dir, settings.profile)
    sources: list[ModelSource] = [LocalDirSource("local", settings.model_root, settings.host_model_root)]
    if settings.hf_cache_dir and settings.host_hf_cache_dir:
        sources.append(HFCacheSource("hf_cache", settings.hf_cache_dir, settings.host_hf_cache_dir))
    docker = DockerRuntime(profile, settings.docker_network)
    litellm = LiteLLMClient(settings.litellm_url, settings.litellm_master_key.get_secret_value())
    catalog = ModelCatalog(sources)
    metrics = MetricsProvider(profile.monitoring.gpu_source, Path("/proc/meminfo"), settings.model_root)

    def total_memory() -> int | None:
        m = metrics.memory()
        return m.total_bytes if m else None

    presets = PresetResolver.from_file(settings.config_dir / "presets.yaml", profile, total_memory)
    planner = Planner(profile, presets)
    classifier = ErrorClassifier.from_file(settings.config_dir / "error-patterns.yaml")
    probe = VllmProbe()

    def hf_token() -> str | None:
        return get_setting(engine, HF_TOKEN_KEY) or settings.hf_token.get_secret_value() or None

    owner = (
        (settings.model_owner_uid, settings.model_owner_gid)
        if settings.model_owner_uid is not None and settings.model_owner_gid is not None
        else None
    )
    runtime_settings = RuntimeSettings(engine, settings, profile)
    hub = HFHubClient(runtime_settings.hf_endpoint_value)
    downloads = DownloadManager(
        engine=engine,
        model_root=settings.model_root,
        hub=hub,
        fetcher=Fetcher(endpoint_source=runtime_settings.hf_endpoint_value),
        token=hf_token,
        on_complete=catalog.rescan,
        owner=owner,
    )
    manager = InstanceManager(
        engine=engine,
        profile=profile,
        runtime=docker,
        gateway=litellm,
        catalog=catalog,
        planner=planner,
        classifier=classifier,
        probe=probe,
        memory=metrics.memory,
        container_prefix=settings.container_prefix,
        health_timeout_s=runtime_settings.health_timeout_s,
    )
    routing = RoutingService(
        engine,
        litellm,
        local_names=lambda: {i.served_model_name for i in manager.all()},
        registered_names=lambda: {
            i.served_model_name
            for i in manager.all()
            if i.status == InstanceStatus.READY and i.gateway_state in (GatewayState.PENDING, GatewayState.REGISTERED)
        },
    )
    manager.on_gateway_change = routing.sync_aliases
    return Services(
        settings=settings,
        profile=profile,
        docker=docker,
        litellm=litellm,
        catalog=catalog,
        metrics=metrics,
        presets=presets,
        planner=planner,
        classifier=classifier,
        probe=probe,
        manager=manager,
        downloads=downloads,
        runtime=runtime_settings,
        hub=hub,
        cloud=CloudService(litellm),
        routing=routing,
    )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
