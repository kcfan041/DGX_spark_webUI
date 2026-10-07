from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.services.api_keys import ApiKeyService, CreateKeyRequest, KeyError_, UpdateKeyRequest
from app.services.usage import MASTER, UsageError, UsageService
from tests.conftest import TOKEN
from tests.fakes import FakeGateway


def _m(req: int, pt: int, ct: int, spend: float, ok: int | None = None) -> dict[str, float]:
    return {
        "api_requests": req,
        "successful_requests": req if ok is None else ok,
        "failed_requests": 0 if ok is None else req - ok,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": pt + ct,
        "spend": spend,
    }


async def test_summary_aggregates_and_fills_days() -> None:
    gw = FakeGateway()
    user = await gw.generate_key("a", {"created_by": "dgxsp", "purpose": "user", "display_name": "App A"})
    sys_ = await gw.generate_key("s", {"created_by": "dgxsp", "purpose": "system-test"})
    old = await gw.generate_key("o", {"created_by": "dgxsp", "purpose": "user", "display_name": "Old"})
    await gw.block_key(old["token"])
    gw.activity = {
        "results": [
            {
                "date": "2026-10-05",
                "metrics": _m(3, 30, 60, 0.5),
                "breakdown": {
                    "model_groups": {"qwen": {"metrics": _m(2, 20, 40, 0)}, "gpt": {"metrics": _m(1, 10, 20, 0.5)}},
                    "api_keys": {
                        user["token"]: {"metrics": _m(2, 20, 40, 0.5)},
                        sys_["token"]: {"metrics": _m(1, 10, 20, 0)},
                    },
                },
            },
            {
                "date": "2026-10-07",
                "metrics": _m(2, 5, 5, 0, ok=1),
                "breakdown": {
                    "model_groups": {"qwen": {"metrics": _m(2, 5, 5, 0, ok=1)}},
                    "api_keys": {
                        MASTER: {"metrics": _m(1, 1, 1, 0)},
                        "litellm-internal-health-check": {"metrics": _m(1, 1, 1, 0)},
                        old["token"]: {"metrics": _m(1, 1, 1, 0)},
                        "deadbeef": {"metrics": _m(1, 4, 4, 0), "metadata": {"key_alias": "gone"}},
                    },
                },
            },
        ]
    }
    s = await UsageService(gw).summary(date(2026, 10, 5), date(2026, 10, 7), -480)
    assert gw.activity_calls[-1] == ("2026-10-05", "2026-10-07", -480)
    assert s.totals.requests == 5 and s.totals.failed == 1 and s.totals.total_tokens == 100
    assert s.totals.spend == pytest.approx(0.5)
    assert [d.date for d in s.days] == ["2026-10-05", "2026-10-06", "2026-10-07"]
    assert s.days[1].metrics.requests == 0
    assert [r.id for r in s.by_model] == ["qwen", "gpt"]
    assert s.by_model[0].metrics.requests == 4
    kinds = {r.id: (r.kind, r.label) for r in s.by_key}
    assert kinds[user["token"]] == ("key", "App A")
    assert kinds[sys_["token"]][0] == "system"
    assert kinds[MASTER][0] == "admin"
    assert kinds["deadbeef"] == ("unknown", "gone")
    assert kinds["litellm-internal-health-check"][0] == "system"
    assert kinds[old["token"]] == ("revoked", "Old")


async def test_summary_range_validation() -> None:
    svc = UsageService(FakeGateway())
    with pytest.raises(UsageError) as e:
        await svc.summary(date(2026, 10, 7), date(2026, 10, 1), None)
    assert e.value.code == "RANGE_INVALID"
    with pytest.raises(UsageError) as e:
        await svc.summary(date(2026, 1, 1), date(2026, 10, 1), None)
    assert e.value.code == "RANGE_TOO_LONG"


async def test_logs_params_and_labels() -> None:
    gw = FakeGateway()
    k = await gw.generate_key("a", {"created_by": "dgxsp", "purpose": "user", "display_name": "App A"})
    gw.logs = {
        "data": [
            {
                "request_id": "r1",
                "startTime": "2026-10-07T01:00:00Z",
                "model_group": "qwen",
                "api_key": k["token"],
                "status": "success",
                "prompt_tokens": 3,
                "completion_tokens": 4,
                "spend": 0.0,
                "request_duration_ms": 12,
                "metadata": {},
            },
            {"request_id": "r2", "api_key": MASTER, "metadata": {"status": "failure"}, "status": None},
        ],
        "page": 1,
        "total_pages": 1,
        "total": 2,
        "total_is_capped": False,
    }
    page = await UsageService(gw).logs(date(2026, 10, 7), date(2026, 10, 7), 1, 50, "qwen", None, "failure", -480)
    p = gw.log_calls[-1]
    assert p["start_date"] == "2026-10-06 16:00:00" and p["end_date"] == "2026-10-07 15:59:59"
    assert p["model_group"] == "qwen" and p["status_filter"] == "failure"
    assert page.items[0].key_name == "App A" and page.items[0].duration_ms == 12
    assert page.items[1].key_name == "admin" and page.items[1].status == "failure"


async def test_key_limits_update_rotate() -> None:
    gw = FakeGateway()
    svc = ApiKeyService(gw)
    k = await svc.create(
        CreateKeyRequest(
            name="App",
            max_budget=5,
            budget_duration="30d",
            rpm_limit=10,
            tpm_limit=1000,
            models=["qwen"],
            expires_in="30d",
        )
    )
    row = gw.key_rows[k.id]
    assert row["max_budget"] == 5 and row["budget_duration"] == "30d" and row["rpm_limit"] == 10
    assert row["models"] == ["qwen"]
    assert k.expires_at is not None and k.limits.max_budget == 5

    plain = await svc.create(CreateKeyRequest(name="Plain"))
    assert gw.key_rows[plain.id]["max_budget"] is None and plain.expires_at is None

    up = await svc.update(k.id, UpdateKeyRequest(name="App 2", rpm_limit=20))
    assert up.name == "App 2" and up.limits.rpm_limit == 20
    assert up.limits.max_budget is None and up.limits.models == []
    assert gw.key_rows[k.id]["budget_duration"] is None

    await svc.update(k.id, UpdateKeyRequest(max_budget=3, budget_duration="7d", rpm_limit=20, models=["qwen"]))
    new = await svc.rotate(k.id)
    assert new.id != k.id and new.key.startswith("sk-")
    assert new.name == "App 2" and new.limits.max_budget == 3 and new.limits.budget_duration == "7d"
    assert new.limits.rpm_limit == 20 and new.limits.models == ["qwen"]
    assert gw.key_rows[k.id]["blocked"] is True
    assert new.expires_at is not None
    assert any(f.get("duration") for t, f in gw.key_updates if t == new.id)

    with pytest.raises(KeyError_) as e:
        await svc.rotate(k.id)
    assert e.value.code == "KEY_REVOKED"
    with pytest.raises(KeyError_) as e:
        await svc.update(k.id, UpdateKeyRequest(rpm_limit=1))
    assert e.value.code == "KEY_REVOKED"
    sys_ = await gw.generate_key("s", {"created_by": "dgxsp", "purpose": "system-test"})
    with pytest.raises(KeyError_) as e:
        await svc.rotate(sys_["token"])
    assert e.value.code == "KEY_SYSTEM"


def test_limit_validation() -> None:
    with pytest.raises(ValueError):
        CreateKeyRequest(name="x", rpm_limit=0)
    with pytest.raises(ValueError):
        CreateKeyRequest(name="x", max_budget=-1)
    with pytest.raises(ValueError):
        CreateKeyRequest(name="x", budget_duration="2h")  # type: ignore[arg-type]


# ---------------------------------------------------------------- admin token


def test_change_admin_token(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/v1/auth/token", headers=auth).json() == {"source": "env"}
    r = client.put("/api/v1/auth/token", headers=auth, json={"current": "wrong", "new": "brand-new-token-123"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "TOKEN_CURRENT_WRONG"
    r = client.put("/api/v1/auth/token", headers=auth, json={"current": TOKEN, "new": "short"})
    assert r.status_code == 422
    r = client.put("/api/v1/auth/token", headers=auth, json={"current": TOKEN, "new": "has space inside!!"})
    assert r.json()["detail"]["code"] == "TOKEN_WEAK"
    r = client.put("/api/v1/auth/token", headers=auth, json={"current": TOKEN, "new": TOKEN})
    assert r.json()["detail"]["code"] == "TOKEN_SAME"

    r = client.put("/api/v1/auth/token", headers=auth, json={"current": TOKEN, "new": "brand-new-token-123"})
    assert r.status_code == 200 and r.json() == {"source": "web"}
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401
    assert client.post("/api/v1/auth/login", json={"token": TOKEN}).status_code == 401
    new = {"Authorization": "Bearer brand-new-token-123"}
    assert client.get("/api/v1/auth/me", headers=new).status_code == 200
    assert client.get("/api/v1/auth/token", headers=new).json() == {"source": "web"}


def test_new_routes_require_auth(client: TestClient) -> None:
    for path in (
        "/api/v1/cloud/providers",
        "/api/v1/cloud/routing",
        "/api/v1/usage/summary?start=2026-10-01&end=2026-10-02",
    ):
        assert client.get(path).status_code == 401
