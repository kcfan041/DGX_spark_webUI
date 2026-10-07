from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from app.adapters.litellm_client import CLOUD_FLAG, PROVIDER_FIELD
from app.db.session import build_engine, init_db
from app.domain.instance import GatewayState, InstanceStatus
from app.services.cloud import CloudError, CloudModelIn, CloudService, ConnTestIn, ProviderIn, ProviderUpdate
from app.services.instance_manager import NotFoundError
from app.services.pricing import LocalPrice, get_price
from app.services.routing import FallbackIn, RetriesIn, RoutingError, RoutingService
from tests.fakes import FakeGateway
from tests.test_manager import Env


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    e = build_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    init_db(e)
    yield e
    e.dispose()


async def test_provider_crud_masks_key() -> None:
    gw = FakeGateway()
    svc = CloudService(gw)
    p = await svc.create_provider(ProviderIn(type="openai", name=" My OpenAI ", api_key="sk-secret-1234"))
    assert p.name == "My OpenAI"
    assert p.type == "openai"
    assert p.masked_key and "secret" not in p.masked_key
    assert p.id.startswith("dgxsp-")
    cred = gw.credentials[p.id]
    assert cred["info"]["custom_llm_provider"] == "openai"
    assert cred["values"]["api_key"] == "sk-secret-1234"

    await gw.create_credential("foreign", {"custom_llm_provider": "openai"}, {"api_key": "x"})
    assert [x.id for x in await svc.list_providers()] == [p.id]

    with pytest.raises(CloudError) as e:
        await svc.create_provider(ProviderIn(type="anthropic", name="my openai", api_key="k"))
    assert e.value.code == "PROVIDER_NAME_TAKEN"

    p2 = await svc.update_provider(p.id, ProviderUpdate(api_key="sk-new-9999"))
    assert gw.credentials[p.id]["values"]["api_key"] == "sk-new-9999"
    assert p2.name == "My OpenAI"
    p3 = await svc.update_provider(p.id, ProviderUpdate(name="Renamed"))
    assert p3.name == "Renamed"
    assert gw.credentials[p.id]["values"]["api_key"] == "sk-new-9999"


async def test_provider_validation() -> None:
    svc = CloudService(FakeGateway())
    with pytest.raises(CloudError) as e:
        await svc.create_provider(ProviderIn(type="openai", name="a"))
    assert e.value.code == "API_KEY_REQUIRED"
    with pytest.raises(CloudError) as e:
        await svc.create_provider(ProviderIn(type="openai_compatible", name="b"))
    assert e.value.code == "API_BASE_REQUIRED"
    with pytest.raises(CloudError) as e:
        await svc.create_provider(ProviderIn(type="openai_compatible", name="b", api_base="ftp://x"))
    assert e.value.code == "API_BASE_INVALID"
    p = await svc.create_provider(
        ProviderIn(type="openai_compatible", name="groq", api_base="https://api.groq.com/openai/v1/")
    )
    assert p.api_base == "https://api.groq.com/openai/v1"
    assert p.masked_key is not None


async def test_test_connection_unsaved_and_saved() -> None:
    gw = FakeGateway()
    svc = CloudService(gw)
    ok = await svc.test(ConnTestIn(type="openai", api_key="sk-good"))
    assert ok.ok and ok.model == "gpt-4o-mini"
    assert gw.tests[-1] == {"api_key": "sk-good", "model": "openai/gpt-4o-mini"}
    bad = await svc.test(ConnTestIn(type="anthropic", api_key="bad"))
    assert not bad.ok
    assert bad.error == "bad key"
    with pytest.raises(CloudError) as e:
        await svc.test(ConnTestIn(type="openai_compatible", api_base="http://x/v1"))
    assert e.value.code == "TEST_MODEL_REQUIRED"
    r = await svc.test(ConnTestIn(type="openai_compatible", api_base="http://x/v1", model="llama-3"))
    assert r.ok
    assert gw.tests[-1] == {"api_key": "none", "api_base": "http://x/v1", "model": "openai/llama-3"}

    p = await svc.create_provider(ProviderIn(type="gemini", name="g", api_key="k"))
    saved = await svc.test(ConnTestIn(), p.id)
    assert saved.ok
    assert gw.tests[-1] == {"litellm_credential_name": p.id, "model": "gemini/gemini-2.5-flash"}


async def test_catalog_filters_chat_models() -> None:
    svc = CloudService(FakeGateway())
    oa = await svc.catalog("openai")
    assert [m.id for m in oa] == ["gpt-4o-mini"]
    assert oa[0].input_per_mtok == 0.15 and oa[0].output_per_mtok == 0.6
    assert [m.id for m in await svc.catalog("gemini")] == ["gemini-2.5-flash"]
    assert await svc.catalog("openai_compatible") == []


async def test_cloud_models_add_list_delete() -> None:
    gw = FakeGateway()
    svc = CloudService(gw)
    p = await svc.create_provider(ProviderIn(type="openai", name="oa", api_key="k"))
    m = await svc.add_model(CloudModelIn(provider_id=p.id, model="gpt-4o-mini"), taken=set())
    assert m.name == "gpt-4o-mini"
    raw = gw.models[m.id]
    assert raw["litellm_params"] == {"model": "openai/gpt-4o-mini", "litellm_credential_name": p.id}
    assert raw["model_info"][CLOUD_FLAG] and raw["model_info"][PROVIDER_FIELD] == p.id
    assert m.provider_name == "oa" and not m.custom_price

    with pytest.raises(CloudError) as e:
        await svc.add_model(CloudModelIn(provider_id=p.id, model="gpt-4o-mini"), taken=set())
    assert e.value.code == "NAME_DUPLICATE"
    with pytest.raises(CloudError) as e:
        await svc.add_model(CloudModelIn(provider_id=p.id, model="x", name="qwen"), taken={"qwen"})
    assert e.value.code == "NAME_DUPLICATE"
    with pytest.raises(CloudError) as e:
        await svc.add_model(CloudModelIn(provider_id=p.id, model="x", name="bad name"), taken=set())
    assert e.value.code == "NAME_INVALID"

    priced = await svc.add_model(
        CloudModelIn(provider_id=p.id, model="gpt-x", name="cheap", input_per_mtok=1, output_per_mtok=2), taken=set()
    )
    assert priced.custom_price and priced.input_per_mtok == 1 and priced.output_per_mtok == 2
    assert (await svc.list_providers())[0].models == 2

    compat = await svc.create_provider(ProviderIn(type="openai_compatible", name="c", api_base="http://h/v1"))
    free = await svc.add_model(CloudModelIn(provider_id=compat.id, model="llama"), taken=set())
    assert free.input_per_mtok == 0 and free.output_per_mtok == 0

    assert await svc.delete_model(m.id) == "gpt-4o-mini"
    removed = await svc.delete_provider(p.id)
    assert removed == ["cheap"]
    assert p.id not in gw.credentials
    assert [x.name for x in await svc.list_models()] == ["llama"]
    with pytest.raises(CloudError):
        await svc.delete_model("nope")


# ---------------------------------------------------------------- routing


def _routing(engine: Engine, gw: FakeGateway, local: set[str], registered: set[str]) -> RoutingService:
    return RoutingService(engine, gw, lambda: set(local), lambda: set(registered))


async def test_fallback_set_validate_clear(engine: Engine) -> None:
    gw = FakeGateway()
    await gw.add_model("cloud-a", {}, {})
    await gw.add_model("cloud-b", {}, {})
    local, reg = {"qwen"}, {"qwen"}
    r = _routing(engine, gw, local, reg)
    out = await r.set_fallback(FallbackIn(model="qwen", targets=["cloud-a", "cloud-b", "cloud-a"]))
    assert gw.router["fallbacks"] == [{"qwen": ["cloud-a", "cloud-b"]}]
    assert out.fallbacks[0].targets == ["cloud-a", "cloud-b"]
    assert "qwen" in out.models and "cloud-a" in out.models

    with pytest.raises(RoutingError) as e:
        await r.set_fallback(FallbackIn(model="qwen", targets=["nope"]))
    assert e.value.code == "ROUTING_TARGET_INVALID"
    with pytest.raises(RoutingError) as e:
        await r.set_fallback(FallbackIn(model="qwen", targets=["qwen"]))
    assert e.value.code == "ROUTING_TARGET_INVALID"
    with pytest.raises(RoutingError) as e:
        await r.set_fallback(FallbackIn(model="ghost", targets=["cloud-a"]))
    assert e.value.code == "ROUTING_MODEL_UNKNOWN"

    await r.set_fallback(FallbackIn(model="qwen", targets=[]))
    assert gw.router["fallbacks"] == []

    out = await r.set_retries(RetriesIn(num_retries=0))
    assert gw.router["num_retries"] == 0 and out.num_retries == 0


async def test_alias_covers_stopped_local_model(engine: Engine) -> None:
    gw = FakeGateway()
    await gw.add_model("cloud-a", {}, {})
    gw.router["model_group_alias"] = {"user-alias": "cloud-a"}
    local, reg = {"qwen"}, {"qwen"}
    r = _routing(engine, gw, local, reg)
    await r.set_fallback(FallbackIn(model="qwen", targets=["cloud-a"]))
    assert gw.router["model_group_alias"] == {"user-alias": "cloud-a"}

    reg.clear()
    assert await r.sync_aliases()
    assert gw.router["model_group_alias"] == {"user-alias": "cloud-a", "qwen": "cloud-a"}
    out = await r.get()
    assert out.fallbacks[0].active_alias == "cloud-a"
    assert not await r.sync_aliases()

    reg.add("qwen")
    assert await r.sync_aliases()
    assert gw.router["model_group_alias"] == {"user-alias": "cloud-a"}
    assert (await r.get()).fallbacks[0].active_alias is None

    reg.clear()
    await r.sync_aliases()
    await r.remove_model_references("cloud-a")
    assert gw.router["fallbacks"] == []
    assert gw.router["model_group_alias"] == {"user-alias": "cloud-a"}


async def test_remove_references_keeps_other_targets(engine: Engine) -> None:
    gw = FakeGateway()
    for n in ("a", "b", "c"):
        await gw.add_model(n, {}, {})
    r = _routing(engine, gw, set(), set())
    gw.router["fallbacks"] = [{"a": ["b", "c"]}, {"b": ["c"]}]
    await r.remove_model_references("b")
    assert gw.router["fallbacks"] == [{"a": ["c"]}]


async def test_gateway_down(engine: Engine) -> None:
    gw = FakeGateway()
    gw.down = True
    r = _routing(engine, gw, set(), set())
    with pytest.raises(RoutingError) as e:
        await r.get()
    assert e.value.code == "GATEWAY_UNREACHABLE"
    assert not await r.sync_aliases()
    with pytest.raises(CloudError) as ce:
        await CloudService(gw).list_providers()
    assert ce.value.code == "GATEWAY_UNREACHABLE"


# ---------------------------------------------------------------- local price + manager hook


async def test_local_price_applied_on_register_and_live(tmp_path: Path, engine: Engine) -> None:
    env = Env(tmp_path, engine)
    calls: list[str] = []

    async def hook() -> None:
        calls.append("x")

    env.mgr.on_gateway_change = hook
    iid = env.create()
    assert env.mgr.local_price(iid) == LocalPrice()
    await env.mgr.set_local_price(iid, LocalPrice(input_per_mtok=0.5, output_per_mtok=1.5))
    await env.mgr.start(iid)
    await env.mgr.wait_idle(iid)
    inst = env.mgr.get(iid)
    assert inst.status == InstanceStatus.READY and inst.gateway_state == GatewayState.REGISTERED
    params = env.gateway.models[inst.gateway_model_id or ""]["litellm_params"]
    assert params["input_cost_per_token"] == pytest.approx(0.5e-6)
    assert params["output_cost_per_token"] == pytest.approx(1.5e-6)
    assert calls

    await env.mgr.set_local_price(iid, LocalPrice(input_per_mtok=0, output_per_mtok=0))
    params = env.gateway.models[inst.gateway_model_id or ""]["litellm_params"]
    assert params["input_cost_per_token"] == 0 and params["output_cost_per_token"] == 0

    n = len(calls)
    await env.mgr.stop(iid)
    assert len(calls) > n
    await env.mgr.set_local_price(iid, LocalPrice(input_per_mtok=3))
    await env.mgr.delete(iid)
    with pytest.raises(NotFoundError):
        env.mgr.local_price(iid)
    assert get_price(engine, iid) == LocalPrice()
