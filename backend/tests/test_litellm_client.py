from typing import Any

import httpx

from app.adapters.litellm_client import LiteLLMClient


def _client(handler: Any) -> LiteLLMClient:
    c = LiteLLMClient("http://litellm:4000", "sk-master")
    c._http = httpx.AsyncClient(base_url="http://litellm:4000", transport=httpx.MockTransport(handler))
    return c


async def test_list_models_drops_alias_copies() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Bearer sk-master"
        if req.url.path == "/model/info":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"model_name": "cloud-a", "model_info": {"id": "1"}},
                        {"model_name": "local-q", "model_info": {"id": "1"}},
                        {"model_name": "other", "model_info": {"id": "2"}},
                    ]
                },
            )
        if req.url.path == "/router/settings":
            return httpx.Response(
                200, json={"fields": [{"field_name": "model_group_alias", "field_value": {"local-q": "cloud-a"}}]}
            )
        return httpx.Response(404)

    names = [m["model_name"] for m in await _client(handler).list_models()]
    assert names == ["cloud-a", "other"]


async def test_list_models_no_router_call_without_duplicates() -> None:
    paths: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        return httpx.Response(200, json={"data": [{"model_name": "a", "model_info": {"id": "1"}}]})

    assert len(await _client(handler).list_models()) == 1
    assert paths == ["/model/info"]
