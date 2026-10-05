from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class VllmRuntime(BaseModel):
    image: str
    pull: bool = True
    command_prefix: list[str] = Field(default_factory=lambda: ["vllm", "serve"])
    gpu: bool = True
    ipc_host: bool = False
    shm_size: str = "16g"
    nofile: int = 1048576
    port: int = 8000
    model_mount: str = "/models"
    env: dict[str, str] = Field(default_factory=dict)


class Timeouts(BaseModel):
    health_s: int = 900
    stop_s: int = 30
    slow_warning_s: int = 300


class MemoryDefaults(BaseModel):
    low: float = 0.4
    default: float = 0.7
    high: float = 0.85
    min: float = 0.1
    max: float = 0.95
    total_warning: float = 0.9


class Monitoring(BaseModel):
    memory_source: Literal["procfs", "mock"] = "procfs"
    gpu_source: Literal["nvidia_smi", "none", "mock"] = "nvidia_smi"


class RuntimeProfile(BaseModel):
    name: str
    description: str = ""
    vllm: VllmRuntime
    timeouts: Timeouts = Field(default_factory=Timeouts)
    memory: MemoryDefaults = Field(default_factory=MemoryDefaults)
    monitoring: Monitoring = Field(default_factory=Monitoring)


def load_profile(config_dir: Path, name: str) -> RuntimeProfile:
    path = config_dir / "profiles" / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"runtime profile not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RuntimeProfile.model_validate(data)
