import argparse
import json
import os
import platform
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import docker
import httpx
import yaml
from docker.errors import APIError, ImageNotFound, NotFound
from docker.types import DeviceRequest, Ulimit

LABEL_KEY = "dgxsp.smoke"
VLLM_NAME = "dgxsp-smoke-vllm"
PROBE_NAME = "dgxsp-smoke-probe"
ERRPROBE_NAME = "dgxsp-smoke-errprobe"
NETWORK = "dgxsp-smoke"
HOST_MODELS = Path("/host-models")
ERROR_HINT = re.compile(r"(ERROR|Error:|Exception|out of memory|OutOfMemory|No available memory|insufficient|CUDA error)")


class StepFailed(Exception):
    pass


class Smoke:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.env = os.environ
        self.profile = yaml.safe_load(Path(args.profile_dir, f"{args.profile}.yaml").read_text())
        vcfg = self.profile["vllm"]
        self.image = self.env.get("SMOKE_VLLM_IMAGE") or vcfg["image"]
        self.model_root = self.env["MODEL_ROOT"]
        self.model_dir = self.env["SMOKE_MODEL_DIR"]
        self.served = self.env.get("SMOKE_SERVED_NAME", "smoke-model")
        self.gpu_mem = self.env.get("SMOKE_GPU_MEM_UTIL", "0.3")
        self.max_len = self.env.get("SMOKE_MAX_MODEL_LEN", "4096")
        self.extra = self.env.get("SMOKE_VLLM_EXTRA_ARGS", "").split()
        self.health_timeout = int(self.env.get("SMOKE_HEALTH_TIMEOUT") or vcfg["health_timeout_s"])
        self.ipc_host = self.env.get("SMOKE_IPC_HOST") == "1" or vcfg.get("ipc_host", False)
        self.litellm_url = self.env.get("LITELLM_URL", "http://litellm:4000")
        self.master_key = self.env["LITELLM_MASTER_KEY"]
        self.vllm_url = f"http://{VLLM_NAME}:{vcfg['port']}"
        self.client = docker.from_env()
        self.http = httpx.Client(timeout=30)
        self.results: dict[str, Any] = {
            "started_at": now_iso(),
            "profile": args.profile,
            "config": {
                "image": self.image,
                "model_root": self.model_root,
                "model_dir": self.model_dir,
                "served_model_name": self.served,
                "gpu_memory_utilization": self.gpu_mem,
                "max_model_len": self.max_len,
                "extra_args": self.extra,
                "ipc_host": self.ipc_host,
                "health_timeout_s": self.health_timeout,
            },
            "steps": [],
        }
        self.litellm_model_id: str | None = None
        self.virtual_key: str | None = None
        self.failed = False

    def admin_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.master_key}"}

    def step(self, name: str, fn: Callable[[], dict[str, Any]], required: bool = True) -> bool:
        if self.failed and required:
            self.results["steps"].append({"name": name, "status": "SKIP"})
            print(f"[SKIP] {name}", flush=True)
            return False
        print(f"[....] {name}", flush=True)
        t0 = time.monotonic()
        rec: dict[str, Any] = {"name": name}
        try:
            rec["data"] = fn()
            rec["status"] = "PASS"
        except StepFailed as e:
            rec["status"] = "FAIL"
            rec["error"] = str(e)
        except Exception as e:
            rec["status"] = "FAIL"
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["traceback"] = traceback.format_exc()
        rec["duration_s"] = round(time.monotonic() - t0, 2)
        self.results["steps"].append(rec)
        print(f"[{rec['status']}] {name} ({rec['duration_s']}s)" + (f" -> {rec.get('error')}" if rec.get("error") else ""), flush=True)
        if rec["status"] == "FAIL" and required:
            self.failed = True
        return rec["status"] == "PASS"

    def s_docker_info(self) -> dict[str, Any]:
        info = self.client.info()
        return {
            "server_version": info.get("ServerVersion"),
            "architecture": info.get("Architecture"),
            "os": info.get("OperatingSystem"),
            "kernel": info.get("KernelVersion"),
            "ncpu": info.get("NCPU"),
            "mem_total_gb": round(info.get("MemTotal", 0) / 2**30, 1),
            "runtimes": sorted((info.get("Runtimes") or {}).keys()),
            "default_runtime": info.get("DefaultRuntime"),
            "cgroup_version": info.get("CgroupVersion"),
            "runner_python": platform.python_version(),
        }

    def s_model_dir(self) -> dict[str, Any]:
        path = HOST_MODELS / self.model_dir
        cfg_path = path / "config.json"
        if not cfg_path.is_file():
            raise StepFailed(f"config.json not found at {self.model_root}/{self.model_dir}")
        cfg = json.loads(cfg_path.read_text())
        files = [p for p in path.rglob("*") if p.is_file()]
        stat = path.stat()
        return {
            "files": len(files),
            "size_gb": round(sum(p.stat().st_size for p in files) / 2**30, 2),
            "has_safetensors": any(p.suffix == ".safetensors" for p in files),
            "owner_uid": stat.st_uid,
            "owner_gid": stat.st_gid,
            "mode": oct(stat.st_mode & 0o777),
            "architectures": cfg.get("architectures"),
            "model_type": cfg.get("model_type"),
            "max_position_embeddings": cfg.get("max_position_embeddings"),
            "torch_dtype": cfg.get("torch_dtype"),
            "quantization_config": (cfg.get("quantization_config") or {}).get("quant_method"),
        }

    def s_image(self) -> dict[str, Any]:
        if self.profile["vllm"].get("pull", True):
            print(f"       pulling {self.image} (may take a long time on first run)...", flush=True)
            self.client.images.pull(self.image)
        try:
            img = self.client.images.get(self.image)
        except ImageNotFound as e:
            raise StepFailed(f"image {self.image} not available locally") from e
        cfg = img.attrs.get("Config") or {}
        return {
            "id": img.id,
            "repo_digests": img.attrs.get("RepoDigests"),
            "architecture": img.attrs.get("Architecture"),
            "os": img.attrs.get("Os"),
            "created": img.attrs.get("Created"),
            "size_gb": round(img.attrs.get("Size", 0) / 2**30, 2),
            "entrypoint": cfg.get("Entrypoint"),
            "cmd": cfg.get("Cmd"),
            "user": cfg.get("User"),
            "workdir": cfg.get("WorkingDir"),
        }

    def gpu_kwargs(self) -> dict[str, Any]:
        if not self.profile["vllm"].get("gpu"):
            return {}
        return {"device_requests": [DeviceRequest(count=-1, capabilities=[["gpu"]])]}

    def run_probe(self, script: str, timeout: int) -> dict[str, Any]:
        remove_if_exists(self.client, PROBE_NAME)
        c = self.client.containers.run(
            self.image,
            command=["bash", "-c", script],
            name=PROBE_NAME,
            detach=True,
            labels={LABEL_KEY: "probe"},
            volumes={self.model_root: {"bind": self.profile["vllm"]["model_mount"], "mode": "ro"}},
            **self.gpu_kwargs(),
        )
        try:
            res = c.wait(timeout=timeout)
            out = c.logs().decode(errors="replace")
        finally:
            c.remove(force=True)
        return {"exit_code": res.get("StatusCode"), "output": out[-8000:]}

    def s_mount_probe(self) -> dict[str, Any]:
        mount = self.profile["vllm"]["model_mount"]
        script = (
            f"echo '== id'; id; "
            f"echo '== ls'; ls -ln {mount}/{self.model_dir} | head -n 20; "
            f"test -r {mount}/{self.model_dir}/config.json && echo CONFIG_READABLE=yes || echo CONFIG_READABLE=no"
        )
        r = self.run_probe(script, 120)
        if "CONFIG_READABLE=yes" not in r["output"]:
            raise StepFailed("model directory not readable inside container: " + r["output"][-500:])
        return r

    def s_gpu_probe(self) -> dict[str, Any]:
        script = (
            "echo '== nvidia-smi'; nvidia-smi || echo NVIDIA_SMI_FAILED; "
            "echo '== nvidia-smi query'; "
            "nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu --format=csv || true; "
            "echo '== torch'; python3 -c \"import torch,json;"
            "a=torch.cuda.is_available();"
            "print('TORCH_JSON='+json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'available':a,"
            "'device':torch.cuda.get_device_name(0) if a else None,"
            "'capability':list(torch.cuda.get_device_capability(0)) if a else None,"
            "'mem_get_info_gb':[round(x/2**30,2) for x in torch.cuda.mem_get_info()] if a else None}))\"; "
            "echo '== vllm'; python3 -c 'import vllm;print(\"VLLM_VERSION=\"+vllm.__version__)' || true"
        )
        r = self.run_probe(script, self.profile["gpu_probe"]["timeout_s"])
        torch_info = None
        for line in r["output"].splitlines():
            if line.startswith("TORCH_JSON="):
                torch_info = json.loads(line[len("TORCH_JSON="):])
            if line.startswith("VLLM_VERSION="):
                r["vllm_version"] = line.split("=", 1)[1]
        r["torch"] = torch_info
        if not torch_info or not torch_info.get("available"):
            raise StepFailed("torch.cuda not available inside container (GPU not passed through)")
        return r

    def s_gateway_ready(self) -> dict[str, Any]:
        deadline = time.monotonic() + 300
        last = None
        while time.monotonic() < deadline:
            try:
                r = self.http.get(f"{self.litellm_url}/health/readiness")
                last = f"{r.status_code} {r.text[:300]}"
                if r.status_code == 200:
                    body = r.json()
                    if str(body.get("db", "")).lower() == "connected":
                        return {"readiness": body}
            except httpx.HTTPError as e:
                last = repr(e)
            time.sleep(3)
        raise StepFailed(f"LiteLLM not ready with db connected: {last}")

    def vllm_command(self, gpu_mem: str) -> list[str]:
        vcfg = self.profile["vllm"]
        return [
            *vcfg["command_prefix"],
            f"{vcfg['model_mount']}/{self.model_dir}",
            "--host", "0.0.0.0",
            "--port", str(vcfg["port"]),
            "--served-model-name", self.served,
            "--gpu-memory-utilization", gpu_mem,
            "--max-model-len", self.max_len,
            *self.extra,
        ]

    def create_vllm(self, name: str, gpu_mem: str) -> Any:
        vcfg = self.profile["vllm"]
        remove_if_exists(self.client, name)
        kwargs: dict[str, Any] = {
            "name": name,
            "detach": True,
            "network": NETWORK,
            "labels": {LABEL_KEY: "vllm", "dgxsp.served_model_name": self.served},
            "environment": vcfg.get("env", {}),
            "volumes": {self.model_root: {"bind": vcfg["model_mount"], "mode": "ro"}},
            "shm_size": vcfg.get("shm_size", "16g"),
            "ulimits": [Ulimit(name="nofile", soft=vcfg.get("nofile", 65536), hard=vcfg.get("nofile", 65536))],
            **self.gpu_kwargs(),
        }
        if self.ipc_host:
            kwargs["ipc_mode"] = "host"
            kwargs.pop("shm_size")
        return self.client.containers.run(self.image, command=self.vllm_command(gpu_mem), **kwargs)

    def s_vllm_start(self) -> dict[str, Any]:
        c = self.create_vllm(VLLM_NAME, self.gpu_mem)
        c.reload()
        return {
            "container_id": c.id[:12],
            "command": self.vllm_command(self.gpu_mem),
            "status": c.status,
            "network": list((c.attrs.get("NetworkSettings") or {}).get("Networks", {}).keys()),
        }

    def s_vllm_health(self) -> dict[str, Any]:
        c = self.client.containers.get(VLLM_NAME)
        t0 = time.monotonic()
        deadline = t0 + self.health_timeout
        timeline: list[dict[str, Any]] = []
        last_phase = None
        while time.monotonic() < deadline:
            c.reload()
            if c.status in ("exited", "dead"):
                state = c.attrs["State"]
                raise StepFailed(json.dumps({
                    "reason": "container exited during startup",
                    "exit_code": state.get("ExitCode"),
                    "oom_killed": state.get("OOMKilled"),
                    "log_tail": tail_logs(c, 60),
                }, ensure_ascii=False))
            phase = "starting"
            try:
                r = self.http.get(f"{self.vllm_url}/health", timeout=5)
                phase = "ready" if r.status_code == 200 else f"http_{r.status_code}"
            except httpx.HTTPError:
                phase = "loading"
            if phase != last_phase:
                timeline.append({"t": round(time.monotonic() - t0, 1), "phase": phase})
                print(f"       {round(time.monotonic() - t0)}s: {phase}", flush=True)
                last_phase = phase
            if phase == "ready":
                break
            time.sleep(3)
        else:
            raise StepFailed(json.dumps({"reason": "health timeout", "timeout_s": self.health_timeout,
                                         "log_tail": tail_logs(c, 60)}, ensure_ascii=False))
        load_s = round(time.monotonic() - t0, 1)
        r = self.http.get(f"{self.vllm_url}/v1/models")
        r.raise_for_status()
        ids = [m.get("id") for m in r.json().get("data", [])]
        if self.served not in ids:
            raise StepFailed(f"/v1/models does not list {self.served}: {ids}")
        return {"load_seconds": load_s, "timeline": timeline, "v1_models": r.json()}

    def s_litellm_register(self) -> dict[str, Any]:
        body = {
            "model_name": self.served,
            "litellm_params": {"model": f"hosted_vllm/{self.served}", "api_base": f"{self.vllm_url}/v1"},
            "model_info": {"dgxsp_instance_id": "smoke", "dgxsp_managed": True},
        }
        r = self.http.post(f"{self.litellm_url}/model/new", headers=self.admin_headers(), json=body)
        if r.status_code >= 300:
            raise StepFailed(f"/model/new {r.status_code}: {r.text[:500]}")
        new_resp = r.json()
        info = self.http.get(f"{self.litellm_url}/model/info", headers=self.admin_headers())
        info.raise_for_status()
        matches = [m for m in info.json().get("data", [])
                   if (m.get("model_info") or {}).get("dgxsp_instance_id") == "smoke"]
        if not matches:
            raise StepFailed("registered model not found in /model/info")
        self.litellm_model_id = matches[-1]["model_info"].get("id")
        return {
            "model_new_response_keys": sorted(new_resp.keys()) if isinstance(new_resp, dict) else type(new_resp).__name__,
            "model_info_entry_keys": sorted(matches[-1].keys()),
            "model_info_fields": sorted((matches[-1].get("model_info") or {}).keys()),
            "litellm_model_id": self.litellm_model_id,
            "matches": len(matches),
        }

    def s_virtual_key(self) -> dict[str, Any]:
        body = {"key_alias": f"dgxsp-smoke-{int(time.time())}",
                "metadata": {"created_by": "dgxsp", "purpose": "smoke"}}
        r = self.http.post(f"{self.litellm_url}/key/generate", headers=self.admin_headers(), json=body)
        if r.status_code >= 300:
            raise StepFailed(f"/key/generate {r.status_code}: {r.text[:500]}")
        resp = r.json()
        self.virtual_key = resp.get("key")
        if not self.virtual_key:
            raise StepFailed("no key in /key/generate response")
        return {"response_keys": sorted(resp.keys()), "key_prefix": self.virtual_key[:5]}

    def s_chat_via_litellm(self) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.virtual_key}"}
        body = {"model": self.served, "messages": [{"role": "user", "content": "Say hello in five words."}],
                "max_tokens": 32}
        deadline = time.monotonic() + 60
        last = None
        while time.monotonic() < deadline:
            t0 = time.monotonic()
            r = self.http.post(f"{self.litellm_url}/v1/chat/completions", headers=headers, json=body, timeout=120)
            latency = round((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                j = r.json()
                return {"latency_ms": latency,
                        "reply_preview": (j["choices"][0]["message"].get("content") or "")[:200],
                        "usage": j.get("usage"), "model": j.get("model")}
            last = f"{r.status_code}: {r.text[:500]}"
            time.sleep(3)
        raise StepFailed(f"chat via LiteLLM failed: {last}")

    def s_logs(self) -> dict[str, Any]:
        c = self.client.containers.get(VLLM_NAME)
        tail = tail_logs(c, 30)
        streamed: list[str] = []

        def reader() -> None:
            for chunk in c.logs(stream=True, follow=True, since=int(time.time())):
                streamed.append(chunk.decode(errors="replace").rstrip())

        threading.Thread(target=reader, daemon=True).start()
        time.sleep(1)
        for _ in range(3):
            self.http.get(f"{self.vllm_url}/v1/models")
            self.http.post(f"{self.litellm_url}/v1/chat/completions",
                           headers={"Authorization": f"Bearer {self.virtual_key}"},
                           json={"model": self.served, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8},
                           timeout=120)
        time.sleep(4)
        if not tail:
            raise StepFailed("no logs from vLLM container")
        return {"tail_lines": len(tail), "tail_sample": tail[-10:], "streamed_lines": len(streamed),
                "streamed_sample": streamed[-5:]}

    def s_key_revoke(self) -> dict[str, Any]:
        r = self.http.post(f"{self.litellm_url}/key/delete", headers=self.admin_headers(),
                           json={"keys": [self.virtual_key]})
        if r.status_code >= 300:
            raise StepFailed(f"/key/delete {r.status_code}: {r.text[:500]}")
        time.sleep(2)
        chk = self.http.post(f"{self.litellm_url}/v1/chat/completions",
                             headers={"Authorization": f"Bearer {self.virtual_key}"},
                             json={"model": self.served, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4})
        self.virtual_key = None
        if chk.status_code == 200:
            raise StepFailed("revoked key still accepted")
        return {"delete_status": r.status_code, "revoked_key_status": chk.status_code}

    def s_litellm_unregister(self) -> dict[str, Any]:
        r = self.http.post(f"{self.litellm_url}/model/delete", headers=self.admin_headers(),
                           json={"id": self.litellm_model_id})
        if r.status_code >= 300:
            raise StepFailed(f"/model/delete {r.status_code}: {r.text[:500]}")
        info = self.http.get(f"{self.litellm_url}/model/info", headers=self.admin_headers()).json()
        still = [m for m in info.get("data", []) if (m.get("model_info") or {}).get("id") == self.litellm_model_id]
        self.litellm_model_id = None if not still else self.litellm_model_id
        if still:
            raise StepFailed("model still present in /model/info after delete")
        return {"delete_status": r.status_code}

    def s_vllm_stop_remove(self) -> dict[str, Any]:
        c = self.client.containers.get(VLLM_NAME)
        t0 = time.monotonic()
        c.stop(timeout=30)
        stop_s = round(time.monotonic() - t0, 1)
        c.reload()
        state = c.attrs["State"]
        c.remove()
        left = self.client.containers.list(all=True, filters={"label": f"{LABEL_KEY}=vllm"})
        if left:
            raise StepFailed(f"containers left: {[x.name for x in left]}")
        return {"stop_seconds": stop_s, "exit_code_after_stop": state.get("ExitCode"),
                "oom_killed": state.get("OOMKilled")}

    def s_error_probe(self) -> dict[str, Any]:
        c = self.create_vllm(ERRPROBE_NAME, "0.01")
        t0 = time.monotonic()
        try:
            res = c.wait(timeout=600)
            state = (self.client.api.inspect_container(c.id) or {}).get("State", {})
            full = tail_logs(c, 2000)
            return {
                "expected": "startup failure with tiny gpu_memory_utilization",
                "exited": True,
                "seconds_to_exit": round(time.monotonic() - t0, 1),
                "exit_code": res.get("StatusCode"),
                "oom_killed": state.get("OOMKilled"),
                "log_lines": len(full),
                "error_lines": [ln for ln in full if ERROR_HINT.search(ln)][-40:],
                "log_tail": full[-40:],
            }
        except Exception as e:
            return {"exited": False, "note": f"did not exit within timeout: {e}", "log_tail": tail_logs(c, 40)}
        finally:
            remove_if_exists(self.client, ERRPROBE_NAME)

    def cleanup(self) -> None:
        if self.virtual_key:
            try:
                self.http.post(f"{self.litellm_url}/key/delete", headers=self.admin_headers(),
                               json={"keys": [self.virtual_key]})
            except Exception:
                pass
        if self.litellm_model_id:
            try:
                self.http.post(f"{self.litellm_url}/model/delete", headers=self.admin_headers(),
                               json={"id": self.litellm_model_id})
            except Exception:
                pass
        if not self.args.keep_vllm:
            for name in (VLLM_NAME, PROBE_NAME, ERRPROBE_NAME):
                remove_if_exists(self.client, name)

    def run(self) -> int:
        try:
            self.step("01_docker_info", self.s_docker_info)
            self.step("02_model_dir", self.s_model_dir)
            self.step("03_image", self.s_image)
            self.step("04_mount_probe", self.s_mount_probe)
            if self.profile["gpu_probe"]["enabled"]:
                self.step("05_gpu_probe", self.s_gpu_probe)
            self.step("06_gateway_ready", self.s_gateway_ready)
            self.step("07_vllm_start", self.s_vllm_start)
            self.step("08_vllm_health", self.s_vllm_health)
            self.step("09_litellm_register", self.s_litellm_register)
            self.step("10_virtual_key", self.s_virtual_key)
            self.step("11_chat_via_litellm", self.s_chat_via_litellm)
            self.step("12_logs", self.s_logs)
            self.step("13_key_revoke", self.s_key_revoke)
            self.step("14_litellm_unregister", self.s_litellm_unregister)
            if not self.args.keep_vllm:
                self.step("15_vllm_stop_remove", self.s_vllm_stop_remove)
            if self.env.get("SMOKE_ERROR_PROBE", "1") == "1" and not self.failed:
                self.step("16_error_probe", self.s_error_probe, required=False)
        finally:
            self.cleanup()
            self.results["finished_at"] = now_iso()
            self.results["overall"] = "FAIL" if self.failed else "PASS"
            stamp = self.env.get("SMOKE_STAMP") or datetime.now().strftime("%Y%m%d-%H%M%S")
            out = Path(self.args.results_dir) / f"smoke-{self.args.profile}-{stamp}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(self.results, indent=2, ensure_ascii=False, default=str))
            print(f"\nOVERALL: {self.results['overall']}\nresults: {out}", flush=True)
        return 1 if self.failed else 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tail_logs(c: Any, n: int) -> list[str]:
    try:
        return c.logs(tail=n).decode(errors="replace").splitlines()
    except (APIError, NotFound):
        return []


def remove_if_exists(client: docker.DockerClient, name: str) -> None:
    try:
        client.containers.get(name).remove(force=True)
    except NotFound:
        pass


def main() -> int:
    p = argparse.ArgumentParser(description="DGX Spark smoke test")
    p.add_argument("--profile", default=os.environ.get("SMOKE_PROFILE", "spark"))
    p.add_argument("--profile-dir", default=str(Path(__file__).parent / "profiles"))
    p.add_argument("--results-dir", default="/results")
    p.add_argument("--keep-vllm", action="store_true")
    return Smoke(p.parse_args()).run()


if __name__ == "__main__":
    sys.exit(main())
