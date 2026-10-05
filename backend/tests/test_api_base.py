from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.settings import Settings
from app.db.session import build_engine, init_db
from app.services import api_base
from app.services.api_base import ApiBaseError, normalize


def req(host: str, forwarded: str | None = None) -> Request:
    headers = [(b"host", host.encode())]
    if forwarded:
        headers.append((b"x-forwarded-host", forwarded.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


@pytest.fixture
def engine(tmp_path: Path):  # type: ignore[no-untyped-def]
    e = build_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    init_db(e)
    yield e
    e.dispose()


def test_normalize() -> None:
    assert normalize(" http://10.0.0.5:4000/v1/ ") == "http://10.0.0.5:4000/v1"
    assert normalize("https://llm.hospital.local/v1") == "https://llm.hospital.local/v1"
    for bad in ["10.0.0.5:4000", "ftp://x/v1", "http://", "http://a b/v1", "http://x:99999/v1", "http://x/v1?a=1"]:
        with pytest.raises(ApiBaseError):
            normalize(bad)


def test_auto_from_request_host(engine) -> None:  # type: ignore[no-untyped-def]
    s = Settings(_env_file=None, public_api_base="", gateway_port=4000, gateway_bind="0.0.0.0")
    info = api_base.resolve(req("192.168.50.240:8088"), s, engine)
    assert info.effective == "http://192.168.50.240:4000/v1"
    assert info.source == "auto"
    assert info.warnings == []

    fwd = api_base.resolve(req("backend:8080", forwarded="spark.lan:8088"), s, engine)
    assert fwd.effective == "http://spark.lan:4000/v1"

    v6 = api_base.resolve(req("[fe80::1]:8088"), s, engine)
    assert v6.effective == "http://[fe80::1]:4000/v1"

    local = api_base.resolve(req("localhost:8088"), s, engine)
    assert "API_BASE_LOCALHOST" in local.warnings


def test_priority_manual_deploy_auto(engine) -> None:  # type: ignore[no-untyped-def]
    s = Settings(_env_file=None, public_api_base="http://10.1.1.1:4000/v1/", gateway_bind="127.0.0.1")
    r = req("192.168.50.240:8088")

    info = api_base.resolve(r, s, engine)
    assert (info.source, info.effective) == ("deploy", "http://10.1.1.1:4000/v1")
    assert "GATEWAY_LOCAL_BIND" in info.warnings

    api_base.update(engine, "manual", "https://llm.example.org/v1/")
    info = api_base.resolve(r, s, engine)
    assert (info.source, info.effective, info.mode) == ("manual", "https://llm.example.org/v1", "manual")

    api_base.update(engine, "auto", None)
    info = api_base.resolve(r, s, engine)
    assert (info.source, info.effective) == ("auto", "http://192.168.50.240:4000/v1")
    assert info.manual == "https://llm.example.org/v1"

    api_base.update(engine, None, None)
    assert api_base.resolve(r, s, engine).source == "deploy"

    with pytest.raises(ApiBaseError):
        api_base.update(engine, "manual", "")


def test_not_v1_warning(engine) -> None:  # type: ignore[no-untyped-def]
    s = Settings(_env_file=None)
    api_base.update(engine, "manual", "http://10.0.0.5:4000")
    assert "API_BASE_NOT_V1" in api_base.resolve(req("x"), s, engine).warnings


def test_api_endpoints_follow_setting(client: TestClient, auth: dict[str, str]) -> None:
    headers = {**auth, "host": "192.168.50.240:8088"}
    info = client.get("/api/v1/settings/api-base", headers=headers).json()
    assert info["source"] == "auto"
    assert info["effective"] == "http://192.168.50.240:4000/v1"
    assert client.get("/api/v1/gateway/connection-info", headers=headers).json()["api_base"] == info["effective"]

    bad = client.put("/api/v1/settings/api-base", json={"mode": "manual", "value": "nope"}, headers=headers)
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "API_BASE_INVALID"

    ok = client.put(
        "/api/v1/settings/api-base", json={"mode": "manual", "value": "http://llm.lan:4000/v1"}, headers=headers
    )
    assert ok.json()["effective"] == "http://llm.lan:4000/v1"
    conn = client.get("/api/v1/gateway/connection-info", headers=headers).json()
    assert conn["api_base"] == "http://llm.lan:4000/v1"
    assert conn["source"] == "manual"

    created = client.post(
        "/api/v1/instances",
        json={"model_id": "local:Qwen2.5-0.5B-Instruct", "start": False},
        headers=headers,
    ).json()
    assert created["endpoint"]["api_base"] == "http://llm.lan:4000/v1"
