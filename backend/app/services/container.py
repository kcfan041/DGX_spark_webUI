from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from sqlalchemy.engine import Engine

from app.adapters.docker_runtime import DockerRuntime
from app.adapters.litellm_client import LiteLLMClient
from app.adapters.metrics import MetricsProvider
from app.adapters.model_sources import HFCacheSource, LocalDirSource, ModelCatalog, ModelSource
from app.core.settings import Settings
from app.profiles import RuntimeProfile, load_profile
from app.services.error_classifier import ErrorClassifier
from app.services.instance_manager import InstanceManager
from app.services.planner import Planner
from app.services.presets import PresetResolver
from app.services.probe import VllmProbe


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

    async def aclose(self) -> None:
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
    presets = PresetResolver.from_file(settings.config_dir / "presets.yaml", profile)
    planner = Planner(profile, presets)
    classifier = ErrorClassifier.from_file(settings.config_dir / "error-patterns.yaml")
    probe = VllmProbe()
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
    )
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
    )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
