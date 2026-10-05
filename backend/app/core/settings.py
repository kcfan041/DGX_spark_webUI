from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DGXSP_", env_file=".env", extra="ignore")

    profile: str = "dev"
    config_dir: Path = Path("/app/configs")
    data_dir: Path = Path("/data")

    admin_token: SecretStr = Field(default=SecretStr(""))

    model_root: Path = Path("/models")
    host_model_root: str = "/data/models"
    hf_cache_dir: Path | None = None
    host_hf_cache_dir: str | None = None

    docker_network: str = "dgxsp"
    container_prefix: str = "dgxsp-vllm-"

    litellm_url: str = "http://litellm:4000"
    litellm_master_key: SecretStr = Field(default=SecretStr(""))
    public_api_base: str = ""
    gateway_port: int = 4000
    gateway_bind: str = "0.0.0.0"

    cors_origins: list[str] = Field(default_factory=list)
    manager_enabled: bool = True

    @field_validator("hf_cache_dir", "host_hf_cache_dir", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'dgxsp.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
