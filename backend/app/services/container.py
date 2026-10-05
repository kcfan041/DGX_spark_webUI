from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from app.adapters.docker_runtime import DockerRuntime
from app.adapters.litellm_client import LiteLLMClient
from app.adapters.metrics import MetricsProvider
from app.adapters.model_sources import HFCacheSource, LocalDirSource, ModelCatalog, ModelSource
from app.core.settings import Settings
from app.profiles import RuntimeProfile, load_profile


@dataclass
class Services:
    settings: Settings
    profile: RuntimeProfile
    docker: DockerRuntime
    litellm: LiteLLMClient
    catalog: ModelCatalog
    metrics: MetricsProvider


def build_services(settings: Settings) -> Services:
    profile = load_profile(settings.config_dir, settings.profile)
    sources: list[ModelSource] = [LocalDirSource("local", settings.model_root, settings.host_model_root)]
    if settings.hf_cache_dir and settings.host_hf_cache_dir:
        sources.append(HFCacheSource("hf_cache", settings.hf_cache_dir, settings.host_hf_cache_dir))
    return Services(
        settings=settings,
        profile=profile,
        docker=DockerRuntime(profile, settings.docker_network),
        litellm=LiteLLMClient(settings.litellm_url, settings.litellm_master_key.get_secret_value()),
        catalog=ModelCatalog(sources),
        metrics=MetricsProvider(profile.monitoring.gpu_source, Path("/proc/meminfo"), settings.model_root),
    )


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
