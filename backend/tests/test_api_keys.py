import pytest

from app.services.api_keys import ApiKeyService, CreateKeyRequest, KeyError_
from tests.fakes import FakeGateway


async def test_create_list_revoke() -> None:
    gw = FakeGateway()
    svc = ApiKeyService(gw)
    created = await svc.create(CreateKeyRequest(name="  院內系統 A  "))
    assert created.key.startswith("sk-")
    assert created.name == "院內系統 A"
    assert created.status == "active"
    assert created.masked.startswith("sk-...")
    assert created.key not in created.masked

    await gw.generate_key("foreign", {"created_by": "someone-else"})
    await gw.generate_key("dgxsp-system-test", {"created_by": "dgxsp", "purpose": "system-test"})

    keys = await svc.list()
    assert [k.name for k in keys] == ["院內系統 A"]
    assert all("key" not in k.model_dump() for k in keys)
    assert len(await svc.list(include_system=True)) == 2

    revoked = await svc.revoke(created.id)
    assert revoked.status == "revoked"
    assert created.key not in gw.keys
    assert (await svc.list())[0].status == "revoked"
    assert (await svc.revoke(created.id)).status == "revoked"


async def test_revoke_guards() -> None:
    gw = FakeGateway()
    svc = ApiKeyService(gw)
    with pytest.raises(KeyError_) as e:
        await svc.revoke("nope")
    assert e.value.code == "KEY_NOT_FOUND"

    sys = await gw.generate_key("dgxsp-system-test", {"created_by": "dgxsp", "purpose": "system-test"})
    with pytest.raises(KeyError_) as e:
        await svc.revoke(sys["token"])
    assert e.value.code == "KEY_SYSTEM"

    foreign = await gw.generate_key("x", {"created_by": "other"})
    with pytest.raises(KeyError_) as e:
        await svc.revoke(foreign["token"])
    assert e.value.code == "KEY_NOT_FOUND"


def test_name_validation() -> None:
    with pytest.raises(ValueError):
        CreateKeyRequest(name="   ")
    with pytest.raises(ValueError):
        CreateKeyRequest(name="x" * 81)
