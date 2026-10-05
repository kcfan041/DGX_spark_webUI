from typing import Protocol

import httpx


class Probe(Protocol):
    async def ready(self, base_url: str, served_model_name: str) -> bool: ...


class VllmProbe:
    def __init__(self, timeout: float = 5.0) -> None:
        self._http = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def ready(self, base_url: str, served_model_name: str) -> bool:
        try:
            r = await self._http.get(f"{base_url}/health")
            if r.status_code != 200:
                return False
            m = await self._http.get(f"{base_url}/v1/models")
            if m.status_code != 200:
                return False
            return any(item.get("id") == served_model_name for item in m.json().get("data", []))
        except (httpx.HTTPError, ValueError):
            return False
