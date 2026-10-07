import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.logging import QuietAccessFilter
from app.core.settings import Settings
from app.db.session import build_engine, init_db
from app.profiles import load_profile
from app.services.downloads import Fetcher, HFHubClient
from app.services.runtime_settings import RuntimeSettings, SettingError
from tests.conftest import REPO_ROOT


def rt(tmp_path: Path, **kw: object) -> RuntimeSettings:
    tmp_path.mkdir(parents=True, exist_ok=True)
    e = build_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    init_db(e)
    s = Settings(_env_file=None, admin_token=SecretStr("x"), **kw)  # type: ignore[arg-type]
    return RuntimeSettings(e, s, load_profile(REPO_ROOT / "configs", "spark"))


def quiet_installed() -> bool:
    return any(isinstance(f, QuietAccessFilter) for f in logging.getLogger("uvicorn.access").filters)


def test_verbose_precedence_and_apply(tmp_path: Path) -> None:
    r = rt(tmp_path)
    assert r.verbose().model_dump() == {"value": False, "source": "default", "default": False}
    r.set_verbose(True)
    assert r.verbose().source == "web" and r.verbose().value is True
    assert not quiet_installed()
    r.set_verbose(False)
    assert quiet_installed()
    r.set_verbose(None)
    assert r.verbose().source == "default"

    deploy = rt(tmp_path / "d", verbose_access_log=True)
    assert deploy.verbose().model_dump() == {"value": True, "source": "deploy", "default": True}
    deploy.set_verbose(False)
    assert deploy.verbose().value is False and deploy.verbose().source == "web"
    deploy.apply_logging()
    assert quiet_installed()


def test_hf_endpoint(tmp_path: Path) -> None:
    r = rt(tmp_path, hf_endpoint="https://hf-mirror.com")
    assert r.hf_endpoint().source == "deploy"
    assert r.hf_endpoint_value() == "https://hf-mirror.com"
    r.set_hf_endpoint("  https://mirror.example.org/  ")
    assert r.hf_endpoint().value == "https://mirror.example.org"
    r.set_hf_endpoint("")
    assert r.hf_endpoint().source == "web"
    assert r.hf_endpoint_value() is None
    r.set_hf_endpoint(None, clear=True)
    assert r.hf_endpoint_value() == "https://hf-mirror.com"
    for bad in ["hf-mirror.com", "ftp://x", "http://"]:
        with pytest.raises(SettingError):
            r.set_hf_endpoint(bad)

    hub = HFHubClient(r.hf_endpoint_value)
    fetch = Fetcher(endpoint_source=r.hf_endpoint_value)
    assert hub.endpoint == fetch.endpoint == "https://hf-mirror.com"
    r.set_hf_endpoint("https://other.example")
    assert hub.endpoint == fetch.endpoint == "https://other.example"


def test_health_timeout(tmp_path: Path) -> None:
    r = rt(tmp_path)
    assert r.health_timeout().model_dump() == {"value": 15, "source": "default", "default": 15}
    assert r.health_timeout_s() == 900
    assert r.slow_warning_s() == 300
    r.set_health_timeout(60)
    assert r.health_timeout_s() == 3600
    assert r.slow_warning_s() == 1200
    for bad in (14, 121, 0):
        with pytest.raises(SettingError):
            r.set_health_timeout(bad)
    r.set_health_timeout(None)
    assert r.health_timeout_s() == 900


def test_advanced_api(client: TestClient, auth: dict[str, str]) -> None:
    a = client.get("/api/v1/settings/advanced", headers=auth).json()
    assert a["verbose_access_log"]["source"] == "default"
    assert a["health_timeout_min"] == {"value": 15, "source": "default", "default": 15}
    assert a["timeout_range"] == [15, 120]
    assert a["deploy"]["model_root"] == "/data/models"

    r = client.put(
        "/api/v1/settings/advanced", json={"health_timeout_min": 45, "verbose_access_log": True}, headers=auth
    )
    assert r.status_code == 200
    body = r.json()
    assert body["health_timeout_min"] == {
        "value": 45,
        "source": "web",
        "default": body["health_timeout_min"]["default"],
    }
    assert body["verbose_access_log"]["value"] is True
    info = client.get("/api/v1/system/info", headers=auth).json()
    assert info["timeouts"]["health_s"] == 2700
    assert info["timeouts"]["slow_warning_s"] == 900

    bad = client.put("/api/v1/settings/advanced", json={"health_timeout_min": 200}, headers=auth)
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "TIMEOUT_OUT_OF_RANGE"
    bad = client.put("/api/v1/settings/advanced", json={"hf_endpoint": "nope"}, headers=auth)
    assert bad.json()["detail"]["code"] == "HF_ENDPOINT_INVALID"

    reset = client.put(
        "/api/v1/settings/advanced", json={"reset": ["health_timeout_min", "verbose_access_log"]}, headers=auth
    ).json()
    assert reset["health_timeout_min"]["source"] == "default"
    assert reset["verbose_access_log"]["source"] == "default"
    assert quiet_installed()

    t = client.post("/api/v1/settings/advanced/test-hf-endpoint", json={"endpoint": "bad url"}, headers=auth)
    assert t.status_code == 422
