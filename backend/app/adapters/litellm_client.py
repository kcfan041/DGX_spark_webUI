import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

MANAGED_FLAG = "dgxsp_managed"
INSTANCE_FIELD = "dgxsp_instance_id"


class GatewayError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LiteLLMClient:
    def __init__(self, base_url: str, master_key: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {master_key}"}
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, *, admin: bool = True, **kw: Any) -> Any:
        headers = kw.pop("headers", {})
        if admin:
            headers = {**self._headers, **headers}
        try:
            r = await self._http.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as e:
            raise GatewayError(f"{method} {path}: {e!r}") from e
        if r.status_code >= 300:
            raise GatewayError(f"{method} {path} -> {r.status_code}: {r.text[:300]}", r.status_code)
        return r.json() if r.content else None

    async def readiness(self) -> dict[str, Any]:
        data: dict[str, Any] = await self._request("GET", "/health/readiness", admin=False)
        return data

    async def register_model(self, *, served_model_name: str, api_base: str, instance_id: str) -> str:
        body = {
            "model_name": served_model_name,
            "litellm_params": {"model": f"hosted_vllm/{served_model_name}", "api_base": api_base},
            "model_info": {INSTANCE_FIELD: instance_id, MANAGED_FLAG: True},
        }
        resp = await self._request("POST", "/model/new", json=body)
        model_id = (resp or {}).get("model_id") or ((resp or {}).get("model_info") or {}).get("id")
        if not model_id:
            raise GatewayError(f"/model/new returned no id: {resp}")
        return str(model_id)

    async def delete_model(self, model_id: str) -> None:
        await self._request("POST", "/model/delete", json={"id": model_id})

    async def list_managed_models(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/model/info")
        return [m for m in (data or {}).get("data", []) if (m.get("model_info") or {}).get(MANAGED_FLAG)]

    async def generate_key(self, alias: str, metadata: dict[str, Any]) -> dict[str, Any]:
        resp: dict[str, Any] = await self._request(
            "POST", "/key/generate", json={"key_alias": alias, "metadata": metadata}
        )
        return resp

    async def delete_key(self, key_or_token: str) -> None:
        await self._request("POST", "/key/delete", json={"keys": [key_or_token]})

    async def block_key(self, key_or_token: str) -> None:
        await self._request("POST", "/key/block", json={"key": key_or_token})

    async def list_keys(self, page_size: int = 100) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._request(
                "GET", "/key/list", params={"return_full_object": "true", "size": page_size, "page": page}
            )
            out += [k for k in (data or {}).get("keys", []) if isinstance(k, dict)]
            if page >= int((data or {}).get("total_pages") or 1):
                return out
            page += 1

    async def chat(self, *, api_key: str, model: str, content: str, max_tokens: int = 32) -> dict[str, Any]:
        body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens}
        resp: dict[str, Any] = await self._request(
            "POST",
            "/v1/chat/completions",
            admin=False,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=120,
        )
        return resp
