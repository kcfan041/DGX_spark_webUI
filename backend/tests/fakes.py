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

    async def readiness(self) -> dict[str, Any]:
        return {"status": "healthy", "db": "connected"}

    async def register_model(self, *, served_model_name: str, api_base: str, instance_id: str) -> str:
        if self.register_error:
            raise self.register_error
        mid = uuid.uuid4().hex
        self.models[mid] = {
            "model_name": served_model_name,
            "litellm_params": {"api_base": api_base},
            "model_info": {"id": mid, INSTANCE_FIELD: instance_id, MANAGED_FLAG: True},
        }
        return mid

    async def delete_model(self, model_id: str) -> None:
        self.models.pop(model_id, None)

    async def list_managed_models(self) -> list[dict[str, Any]]:
        return list(self.models.values())

    async def generate_key(self, alias: str, metadata: dict[str, Any]) -> dict[str, Any]:
        if any(r["key_alias"] == alias for r in self.key_rows.values()):
            raise GatewayError(f"Key with alias '{alias}' already exists", 400)
        k = f"sk-{uuid.uuid4().hex}"
        token = uuid.uuid4().hex + uuid.uuid4().hex
        self.keys.add(k)
        self.key_rows[token] = {
            "token": token,
            "key_name": f"sk-...{k[-4:]}",
            "key_alias": alias,
            "metadata": metadata,
            "blocked": None,
            "created_at": "2026-10-05T06:35:09.767000Z",
            "_key": k,
        }
        return {
            "key": k,
            "key_alias": alias,
            "token": token,
            "key_name": f"sk-...{k[-4:]}",
            "created_at": "2026-10-05T06:35:09.767000Z",
        }

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
