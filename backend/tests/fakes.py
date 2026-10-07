import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.adapters.docker_runtime import ContainerSpec, ContainerState
from app.adapters.litellm_client import INSTANCE_FIELD, MANAGED_FLAG, GatewayError


@dataclass
class FakeContainer:
    spec: ContainerSpec
    status: str = "running"
    exit_code: int | None = None
    oom_killed: bool = False
    logs: list[str] = field(default_factory=list)


class FakeRuntime:
    def __init__(self) -> None:
        self.containers: dict[str, FakeContainer] = {}
        self.run_error: Exception | None = None
        self.fail_with: tuple[int, bool, list[str]] | None = None
        self.runs: list[ContainerSpec] = []

    def ping(self) -> bool:
        return True

    def run(self, spec: ContainerSpec) -> str:
        if self.run_error:
            raise self.run_error
        self.runs.append(spec)
        c = FakeContainer(spec=spec, logs=["INFO Loading model weights"])
        if self.fail_with:
            c.status, c.exit_code, c.oom_killed = "exited", self.fail_with[0], self.fail_with[1]
            c.logs += self.fail_with[2]
        self.containers[spec.name] = c
        return uuid.uuid4().hex

    def state(self, name: str) -> ContainerState | None:
        c = self.containers.get(name)
        if c is None:
            return None
        return ContainerState(
            id=name,
            name=name,
            status=c.status,
            exit_code=c.exit_code,
            oom_killed=c.oom_killed,
            started_at=None,
            finished_at=None,
            labels={},
        )

    def stop(self, name: str, timeout: int) -> None:
        c = self.containers.get(name)
        if c:
            c.status, c.exit_code = "exited", 0

    def remove(self, name: str) -> None:
        self.containers.pop(name, None)

    def logs(self, name: str, tail: int = 500) -> list[str]:
        c = self.containers.get(name)
        return c.logs[-tail:] if c else []

    def stream_logs(self, name: str, tail: int = 100) -> Iterator[str]:
        yield from self.logs(name, tail)


class FakeGateway:
    def __init__(self) -> None:
        self.models: dict[str, dict[str, Any]] = {}
        self.keys: set[str] = set()
        self.key_rows: dict[str, dict[str, Any]] = {}
        self.down = False
        self.register_error: GatewayError | None = None
        self.chats: list[dict[str, Any]] = []
        self.credentials: dict[str, dict[str, Any]] = {}
        self.tests: list[dict[str, Any]] = []
        self.router: dict[str, Any] = {"fallbacks": [], "model_group_alias": {}, "num_retries": 2}
        self.activity: dict[str, Any] = {"results": [], "metadata": {}}
        self.activity_calls: list[tuple[str, str, int | None]] = []
        self.logs: dict[str, Any] = {"data": [], "page": 1, "total_pages": 0, "total": 0}
        self.log_calls: list[dict[str, Any]] = []
        self.key_updates: list[tuple[str, dict[str, Any]]] = []

    async def readiness(self) -> dict[str, Any]:
        return {"status": "healthy", "db": "connected"}

    async def register_model(
        self,
        *,
        served_model_name: str,
        api_base: str,
        instance_id: str,
        input_cost_per_token: float = 0.0,
        output_cost_per_token: float = 0.0,
    ) -> str:
        if self.register_error:
            raise self.register_error
        return await self.add_model(
            served_model_name,
            {
                "api_base": api_base,
                "input_cost_per_token": input_cost_per_token,
                "output_cost_per_token": output_cost_per_token,
            },
            {INSTANCE_FIELD: instance_id, MANAGED_FLAG: True},
        )

    async def add_model(self, model_name: str, litellm_params: dict[str, Any], model_info: dict[str, Any]) -> str:
        if self.down:
            raise GatewayError("connection refused")
        mid = uuid.uuid4().hex
        self.models[mid] = {
            "model_name": model_name,
            "litellm_params": dict(litellm_params),
            "model_info": {"id": mid, **model_info},
        }
        return mid

    async def update_model_params(self, model_id: str, litellm_params: dict[str, Any]) -> None:
        self.models[model_id]["litellm_params"].update(litellm_params)

    async def delete_model(self, model_id: str) -> None:
        self.models.pop(model_id, None)

    async def list_models(self) -> list[dict[str, Any]]:
        if self.down:
            raise GatewayError("connection refused")
        return list(self.models.values())

    async def list_managed_models(self) -> list[dict[str, Any]]:
        return [m for m in await self.list_models() if m["model_info"].get(MANAGED_FLAG)]

    async def list_credentials(self) -> list[dict[str, Any]]:
        if self.down:
            raise GatewayError("connection refused")
        return [
            {
                "credential_name": n,
                "credential_info": c["info"],
                "credential_values": {
                    k: (f"{v[:2]}****{v[-2:]}" if k == "api_key" else v) for k, v in c["values"].items()
                },
            }
            for n, c in self.credentials.items()
        ]

    async def create_credential(self, name: str, info: dict[str, Any], values: dict[str, Any]) -> None:
        self.credentials[name] = {"info": dict(info), "values": dict(values)}

    async def update_credential(self, name: str, info: dict[str, Any], values: dict[str, Any] | None) -> None:
        self.credentials[name]["info"] = dict(info)
        self.credentials[name]["values"].update(values or {})

    async def delete_credential(self, name: str) -> None:
        self.credentials.pop(name, None)

    async def test_connection(self, litellm_params: dict[str, Any]) -> dict[str, Any]:
        self.tests.append(litellm_params)
        key = litellm_params.get("api_key")
        cred = litellm_params.get("litellm_credential_name")
        if cred:
            key = self.credentials[cred]["values"].get("api_key")
        if key == "bad":
            return {"status": "error", "result": {"error": "litellm.AuthenticationError: bad key\nstack trace: x"}}
        return {"status": "success", "result": {"model": litellm_params["model"]}}

    async def cost_map(self) -> dict[str, Any]:
        return {
            "gpt-4o-mini": {
                "litellm_provider": "openai",
                "mode": "chat",
                "input_cost_per_token": 1.5e-07,
                "output_cost_per_token": 6e-07,
                "max_input_tokens": 128000,
            },
            "ft:gpt-4o": {"litellm_provider": "openai", "mode": "chat"},
            "text-embedding-3-small": {"litellm_provider": "openai", "mode": "embedding"},
            "claude-haiku-4-5": {"litellm_provider": "anthropic", "mode": "chat", "input_cost_per_token": 1e-06},
            "gemini/gemini-2.5-flash": {"litellm_provider": "gemini", "mode": "chat"},
        }

    async def router_settings(self) -> dict[str, Any]:
        if self.down:
            raise GatewayError("connection refused")
        return {
            k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
            for k, v in self.router.items()
        }

    async def update_router_settings(self, values: dict[str, Any]) -> None:
        if self.down:
            raise GatewayError("connection refused")
        self.router.update(values)

    async def daily_activity(self, start_date: str, end_date: str, timezone: int | None) -> dict[str, Any]:
        self.activity_calls.append((start_date, end_date, timezone))
        return self.activity

    async def spend_logs(self, params: dict[str, Any]) -> dict[str, Any]:
        self.log_calls.append(params)
        return self.logs

    async def generate_key(self, alias: str, metadata: dict[str, Any], **limits: Any) -> dict[str, Any]:
        if any(r["key_alias"] == alias for r in self.key_rows.values()):
            raise GatewayError(f"Key with alias '{alias}' already exists", 400)
        k = f"sk-{uuid.uuid4().hex}"
        token = uuid.uuid4().hex + uuid.uuid4().hex
        self.keys.add(k)
        expires = None
        if limits.get("duration"):
            expires = "2099-01-01T00:00:00Z"
        row = {
            "token": token,
            "key_name": f"sk-...{k[-4:]}",
            "key_alias": alias,
            "metadata": metadata,
            "blocked": None,
            "created_at": "2026-10-05T06:35:09.767000Z",
            "expires": expires,
            "spend": 0.0,
            **{x: limits.get(x) for x in ("max_budget", "budget_duration", "rpm_limit", "tpm_limit")},
            "models": limits.get("models") or [],
            "_key": k,
        }
        self.key_rows[token] = row
        return {"key": k, **{x: v for x, v in row.items() if x != "_key"}}

    async def update_key(self, key_or_token: str, fields: dict[str, Any]) -> dict[str, Any]:
        row = self.key_rows[key_or_token]
        for x, v in fields.items():
            if x == "duration":
                row["expires"] = "2099-02-02T00:00:00Z" if v else None
            else:
                row[x] = v
        self.key_updates.append((key_or_token, fields))
        return {x: v for x, v in row.items() if x != "_key"}

    async def delete_key(self, key_or_token: str) -> None:
        self.keys.discard(key_or_token)

    async def block_key(self, key_or_token: str) -> None:
        if self.down:
            raise GatewayError("connection refused")
        row = self.key_rows[key_or_token]
        row["blocked"] = True
        self.keys.discard(row["_key"])

    async def list_keys(self, page_size: int = 100) -> list[dict[str, Any]]:
        if self.down:
            raise GatewayError("connection refused")
        return [{k: v for k, v in r.items() if k != "_key"} for r in self.key_rows.values()]

    async def chat(self, *, api_key: str, model: str, content: str, max_tokens: int = 32) -> dict[str, Any]:
        if api_key not in self.keys:
            raise GatewayError("401", 401)
        if not any(m["model_name"] == model for m in self.models.values()):
            raise GatewayError("400 model not found", 400)
        self.chats.append({"model": model, "content": content})
        return {"choices": [{"message": {"content": f"echo: {content}"}}]}


class FakeProbe:
    def __init__(self) -> None:
        self.ready_after = 1
        self.calls: dict[str, int] = {}

    async def ready(self, base_url: str, served_model_name: str) -> bool:
        n = self.calls.get(base_url, 0) + 1
        self.calls[base_url] = n
        return n > self.ready_after
