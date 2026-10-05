import pytest

from app.core.settings import Settings


def test_empty_hf_cache_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGXSP_HF_CACHE_DIR", "")
    monkeypatch.setenv("DGXSP_HOST_HF_CACHE_DIR", "")
    s = Settings(_env_file=None)
    assert s.hf_cache_dir is None
    assert s.host_hf_cache_dir is None


def test_secrets_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DGXSP_ADMIN_TOKEN", "super-secret")
    monkeypatch.setenv("DGXSP_LITELLM_MASTER_KEY", "sk-master")
    s = Settings(_env_file=None)
    assert "super-secret" not in repr(s)
    assert "sk-master" not in repr(s)
    assert s.admin_token.get_secret_value() == "super-secret"
