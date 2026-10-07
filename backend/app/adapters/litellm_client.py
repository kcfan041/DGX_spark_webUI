import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

MANAGED_FLAG = "dgxsp_managed"
INSTANCE_FIELD = "dgxsp_instance_id"
CLOUD_FLAG = "dgxsp_cloud"
PROVIDER_FIELD = "dgxsp_provider"


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

    async def register_model(
        self,
        *,
        served_model_name: str,
        api_base: str,
        instance_id: str,
        input_cost_per_token: float = 0.0,
        output_cost_per_token: float = 0.0,
    ) -> str:
        return await self.add_model(
            served_model_name,
            {
                "model": f"hosted_vllm/{served_model_name}",
                "api_base": api_base,
                "input_cost_per_token": input_cost_per_token,
                "output_cost_per_token": output_cost_per_token,
            },
            {INSTANCE_FIELD: instance_id, MANAGED_FLAG: True},
        )

    async def add_model(self, model_name: str, litellm_params: dict[str, Any], model_info: dict[str, Any]) -> str:
        body = {"model_name": model_name, "litellm_params": litellm_params, "model_info": model_info}
        resp = await self._request("POST", "/model/new", json=body)
        model_id = (resp or {}).get("model_id") or ((resp or {}).get("model_info") or {}).get("id")
        if not model_id:
            raise GatewayError(f"/model/new returned no id: {resp}")
        return str(model_id)

    async def update_model_params(self, model_id: str, litellm_params: dict[str, Any]) -> None:
        await self._request("PATCH", f"/model/{model_id}/update", json={"litellm_params": litellm_params})

    async def delete_model(self, model_id: str) -> None:
        await self._request("POST", "/model/delete", json={"id": model_id})

    async def list_models(self) -> list[dict[str, Any]]:
        """Deployments only. /model/info also lists each model_group_alias as a copy of its target (same id)."""
        data = await self._request("GET", "/model/info")
        rows = [m for m in (data or {}).get("data", []) if isinstance(m, dict)]
        aliases: set[str] = set()
        if any(r.get("model_info", {}).get("id") for r in rows):
            ids = [(r.get("model_info") or {}).get("id") for r in rows]
            if len(ids) != len(set(ids)):
                aliases = set((await self.router_settings()).get("model_group_alias") or {})
        return [m for m in rows if m.get("model_name") not in aliases]

    async def list_managed_models(self) -> list[dict[str, Any]]:
        return [m for m in await self.list_models() if (m.get("model_info") or {}).get(MANAGED_FLAG)]

    # ---------------------------------------------------------------- credentials (provider API keys)

    async def list_credentials(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/credentials")
        return [c for c in (data or {}).get("credentials", []) if isinstance(c, dict)]

    async def create_credential(self, name: str, info: dict[str, Any], values: dict[str, Any]) -> None:
        body = {"credential_name": name, "credential_info": info, "credential_values": values}
        await self._request("POST", "/credentials", json=body)

    async def update_credential(self, name: str, info: dict[str, Any], values: dict[str, Any] | None) -> None:
        body: dict[str, Any] = {"credential_name": name, "credential_info": info}
        if values:
            body["credential_values"] = values
        await self._request("PATCH", f"/credentials/{name}", json=body)

    async def delete_credential(self, name: str) -> None:
        await self._request("DELETE", f"/credentials/{name}")

    async def test_connection(self, litellm_params: dict[str, Any]) -> dict[str, Any]:
        resp: dict[str, Any] = await self._request(
            "POST", "/health/test_connection", json={"litellm_params": litellm_params, "mode": "chat"}, timeout=60
        )
        return resp

    async def cost_map(self) -> dict[str, Any]:
        data: dict[str, Any] = await self._request("GET", "/public/litellm_model_cost_map", admin=False, timeout=30)
        return data

    # ---------------------------------------------------------------- router settings (fallbacks / aliases)

    async def router_settings(self) -> dict[str, Any]:
        data = await self._request("GET", "/router/settings")
        return {f["field_name"]: f.get("field_value") for f in (data or {}).get("fields", []) if "field_name" in f}

    async def update_router_settings(self, values: dict[str, Any]) -> None:
        await self._request("POST", "/config/update", json={"router_settings": values})

    # ---------------------------------------------------------------- usage

    async def daily_activity(self, start_date: str, end_date: str, timezone: int | None) -> dict[str, Any]:
        params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, "page_size": 1000}
        if timezone is not None:
            params["timezone"] = timezone
        results: list[dict[str, Any]] = []
        meta: dict[str, Any] = {}
        page = 1
        while True:
            data = await self._request("GET", "/user/daily/activity", params={**params, "page": page}, timeout=60)
            results += (data or {}).get("results", [])
            meta = (data or {}).get("metadata", {}) or {}
            if not meta.get("has_more") or page >= 20:
                return {"results": results, "metadata": meta}
            page += 1

    async def spend_logs(self, params: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = await self._request("GET", "/spend/logs/v2", params=params, timeout=60)
        return data

    # ---------------------------------------------------------------- keys

    async def generate_key(self, alias: str, metadata: dict[str, Any], **limits: Any) -> dict[str, Any]:
        resp: dict[str, Any] = await self._request(
            "POST", "/key/generate", json={"key_alias": alias, "metadata": metadata, **limits}
        )
        return resp

    async def update_key(self, key_or_token: str, fields: dict[str, Any]) -> dict[str, Any]:
        resp: dict[str, Any] = await self._request("POST", "/key/update", json={"key": key_or_token, **fields})
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
