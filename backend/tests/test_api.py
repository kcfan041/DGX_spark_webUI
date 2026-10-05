from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_requires_auth(client: TestClient) -> None:
    r = client.get("/api/v1/models")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "UNAUTHORIZED"
    assert client.get("/api/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_login(client: TestClient) -> None:
    assert client.post("/api/v1/auth/login", json={"token": "nope"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"token": "test-admin-token"})
    assert r.status_code == 200
    assert r.json() == {"subject": "admin", "roles": ["admin"]}


def test_me(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/v1/auth/me", headers=auth).json()["subject"] == "admin"


def test_models(client: TestClient, auth: dict[str, str]) -> None:
    r = client.get("/api/v1/models", headers=auth)
    assert r.status_code == 200
    models = r.json()
    assert len(models) == 1
    m = models[0]
    assert m["id"] == "local:Qwen2.5-0.5B-Instruct"
    assert m["architecture"] == "Qwen2ForCausalLM"
    assert m["max_context"] == 32768
    assert m["host_path"] == "/data/models/Qwen2.5-0.5B-Instruct"
    assert m["in_use_by"] == []

    one = client.get("/api/v1/models/local:Qwen2.5-0.5B-Instruct", headers=auth)
    assert one.status_code == 200
    assert client.get("/api/v1/models/local:missing", headers=auth).status_code == 404


def test_model_sources(client: TestClient, auth: dict[str, str]) -> None:
    r = client.post("/api/v1/model-sources/rescan", headers=auth)
    assert r.status_code == 200
    assert r.json()[0] == {
        "id": "local",
        "type": "local_dir",
        "path": "/data/models",
        "model_count": 1,
        "available": True,
    }


def test_instances_empty(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/v1/instances", headers=auth).json() == []
    assert client.get("/api/v1/instances/nope", headers=auth).status_code == 404


MODEL = "local:Qwen2.5-0.5B-Instruct"


def test_presets_and_schema(client: TestClient, auth: dict[str, str]) -> None:
    presets = client.get("/api/v1/presets", params={"model_id": MODEL}, headers=auth).json()
    assert [p["id"] for p in presets][0] == "balanced"
    schema = client.get("/api/v1/param-schema", params={"model_id": MODEL}, headers=auth).json()
    by_name = {f["name"]: f for f in schema}
    assert by_name["max_model_len"]["max"] == 32768
    assert by_name["max_model_len"]["level"] == "basic"
    assert by_name["dtype"]["level"] == "advanced"
    assert client.get("/api/v1/presets", params={"model_id": "local:x"}, headers=auth).status_code == 404


def test_preview_create_update_delete(client: TestClient, auth: dict[str, str]) -> None:
    pv = client.post("/api/v1/instances/preview", json={"model_id": MODEL}, headers=auth)
    assert pv.status_code == 200
    assert pv.json()["blocking"] is False
    assert pv.json()["command"][:2] == ["python", "/app/mock_vllm.py"]

    bad = client.post(
        "/api/v1/instances", json={"model_id": MODEL, "params": {"max_model_len": 999999}, "start": False}, headers=auth
    )
    assert bad.status_code == 409
    assert bad.json()["detail"]["code"] == "PLAN_BLOCKED"

    r = client.post("/api/v1/instances", json={"model_id": MODEL, "start": False, "autostart": True}, headers=auth)
    assert r.status_code == 201
    inst = r.json()
    assert inst["status"] == "CREATED"
    assert inst["autostart"] is True
    assert inst["endpoint"]["model"] == "qwen2.5-0.5b-instruct"
    assert inst["diagnostics"]["command"]

    dup = client.post("/api/v1/instances", json={"model_id": MODEL, "start": False}, headers=auth)
    assert dup.status_code == 409

    up = client.patch(f"/api/v1/instances/{inst['id']}", json={"params": {"max_model_len": 4096}}, headers=auth)
    assert up.status_code == 200
    assert up.json()["instance"]["params"]["max_model_len"] == 4096
    assert up.json()["restart_required"] is False

    ev = client.get(f"/api/v1/instances/{inst['id']}/events", headers=auth).json()
    assert {e["type"] for e in ev} == {"created", "updated"}

    assert client.post(f"/api/v1/instances/{inst['id']}/stop", headers=auth).status_code == 409
    assert client.post(f"/api/v1/instances/{inst['id']}/test", json={}, headers=auth).status_code == 409
    assert client.delete(f"/api/v1/instances/{inst['id']}", headers=auth).status_code == 204
    assert client.get("/api/v1/instances", headers=auth).json() == []


def test_autostart_status(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/v1/system/autostart", headers=auth).json()["state"] == "idle"


def test_summary_without_docker_or_gateway(client: TestClient, auth: dict[str, str]) -> None:
    r = client.get("/api/v1/system/summary", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["gateway"]["reachable"] is False
    assert body["counts"]["READY"] == 0
    assert body["health"] in {"runtime_error", "gateway_unreachable"}
