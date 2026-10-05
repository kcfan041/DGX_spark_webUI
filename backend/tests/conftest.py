import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.settings import Settings, get_settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN = "test-admin-token"
QWEN_CONFIG: dict[str, object] = {
    "architectures": ["Qwen2ForCausalLM"],
    "model_type": "qwen2",
    "max_position_embeddings": 32768,
    "torch_dtype": "bfloat16",
    "num_hidden_layers": 24,
    "num_attention_heads": 14,
    "num_key_value_heads": 2,
    "hidden_size": 896,
}


def make_model(root: Path, name: str, config: dict[str, object], weights: str = "model.safetensors") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (d / weights).write_bytes(b"\0" * 1024)
    return d


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    models = tmp_path / "models"
    models.mkdir()
    make_model(models, "Qwen2.5-0.5B-Instruct", QWEN_CONFIG)
    s = Settings(
        profile="dev",
        config_dir=REPO_ROOT / "configs",
        data_dir=tmp_path / "data",
        admin_token=SecretStr(TOKEN),
        model_root=models,
        host_model_root="/data/models",
        litellm_url="http://127.0.0.1:9",
        manager_enabled=False,
    )
    monkeypatch.setenv("DGXSP_ADMIN_TOKEN", TOKEN)
    get_settings.cache_clear()
    return s


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}
