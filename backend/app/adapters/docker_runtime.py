import contextlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.types import DeviceRequest, Ulimit

from app.profiles import RuntimeProfile

log = logging.getLogger(__name__)

LABEL_MANAGED = "dgxsp.managed"
LABEL_INSTANCE = "dgxsp.instance_id"
LABEL_SERVED = "dgxsp.served_model_name"


@dataclass
class ContainerSpec:
    name: str
    instance_id: str
    served_model_name: str
    command: list[str]
    host_model_path: str
    container_model_path: str
    host_port: int | None = None
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass
class ContainerState:
    id: str
    name: str
    status: str
    exit_code: int | None
    oom_killed: bool
    started_at: str | None
    finished_at: str | None
    labels: dict[str, str]


class DockerUnavailable(Exception):
    pass


class DockerRuntime:
    def __init__(self, profile: RuntimeProfile, network: str) -> None:
        self.profile = profile
        self.network = network
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            try:
                self._client = docker.from_env()
            except DockerException as e:
                raise DockerUnavailable(str(e)) from e
        return self._client

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except (DockerException, DockerUnavailable):
            return False

    def info(self) -> dict[str, Any]:
        info: dict[str, Any] = self.client.info()
        return {
            "server_version": info.get("ServerVersion"),
            "architecture": info.get("Architecture"),
            "os": info.get("OperatingSystem"),
            "ncpu": info.get("NCPU"),
            "mem_total_bytes": info.get("MemTotal"),
        }

    def image_info(self) -> dict[str, Any] | None:
        try:
            img = self.client.images.get(self.profile.vllm.image)
        except (ImageNotFound, APIError, DockerUnavailable):
            return None
        return {
            "id": img.id,
            "repo_digests": img.attrs.get("RepoDigests"),
            "architecture": img.attrs.get("Architecture"),
            "created": img.attrs.get("Created"),
        }

    def ensure_network(self) -> None:
        try:
            self.client.networks.get(self.network)
        except NotFound:
            self.client.networks.create(self.network, driver="bridge")

    def build_run_kwargs(self, spec: ContainerSpec) -> dict[str, Any]:
        v = self.profile.vllm
        kwargs: dict[str, Any] = {
            "name": spec.name,
            "command": spec.command,
            "detach": True,
            "network": self.network,
            "labels": {
                LABEL_MANAGED: "true",
                LABEL_INSTANCE: spec.instance_id,
                LABEL_SERVED: spec.served_model_name,
            },
            "environment": {**v.env, **spec.extra_env},
            "volumes": {spec.host_model_path: {"bind": spec.container_model_path, "mode": "ro"}},
            "ulimits": [Ulimit(name="nofile", soft=v.nofile, hard=v.nofile)],
        }
        if v.gpu:
            kwargs["device_requests"] = [DeviceRequest(count=-1, capabilities=[["gpu"]])]
        if v.ipc_host:
            kwargs["ipc_mode"] = "host"
        else:
            kwargs["shm_size"] = v.shm_size
        if spec.host_port:
            kwargs["ports"] = {f"{v.port}/tcp": spec.host_port}
        return kwargs

    def run(self, spec: ContainerSpec) -> str:
        self.ensure_network()
        self.remove(spec.name)
        container = self.client.containers.run(self.profile.vllm.image, **self.build_run_kwargs(spec))
        return str(container.id)

    def state(self, name_or_id: str) -> ContainerState | None:
        try:
            c = self.client.containers.get(name_or_id)
        except NotFound:
            return None
        s = c.attrs.get("State", {})
        return ContainerState(
            id=str(c.id),
            name=c.name or "",
            status=c.status,
            exit_code=s.get("ExitCode"),
            oom_killed=bool(s.get("OOMKilled")),
            started_at=s.get("StartedAt"),
            finished_at=s.get("FinishedAt"),
            labels=dict(c.labels or {}),
        )

    def stop(self, name_or_id: str, timeout: int) -> None:
        with contextlib.suppress(NotFound):
            self.client.containers.get(name_or_id).stop(timeout=timeout)

    def remove(self, name_or_id: str) -> None:
        with contextlib.suppress(NotFound):
            self.client.containers.get(name_or_id).remove(force=True)

    def logs(self, name_or_id: str, tail: int = 500) -> list[str]:
        try:
            raw = self.client.containers.get(name_or_id).logs(tail=tail, timestamps=True)
        except NotFound:
            return []
        return bytes(raw).decode(errors="replace").splitlines()

    def stream_logs(self, name_or_id: str, tail: int = 100) -> Iterator[str]:
        c = self.client.containers.get(name_or_id)
        buf = b""
        for chunk in c.logs(stream=True, follow=True, tail=tail, timestamps=True):
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                yield line.decode(errors="replace")

    def list_managed(self) -> list[ContainerState]:
        out = []
        for c in self.client.containers.list(all=True, filters={"label": f"{LABEL_MANAGED}=true"}):
            st = self.state(str(c.id))
            if st:
                out.append(st)
        return out

    def list_external_candidates(self) -> list[dict[str, Any]]:
        out = []
        for c in self.client.containers.list():
            labels = c.labels or {}
            if labels.get(LABEL_MANAGED) == "true" or labels.get("com.docker.compose.project", "").startswith("dgxsp"):
                continue
            image = ",".join(c.image.tags) if c.image and c.image.tags else str(c.attrs.get("Config", {}).get("Image"))
            uses_gpu = bool((c.attrs.get("HostConfig") or {}).get("DeviceRequests"))
            if uses_gpu or "vllm" in image.lower():
                out.append({"name": c.name, "image": image, "status": c.status, "uses_gpu": uses_gpu})
        return out
