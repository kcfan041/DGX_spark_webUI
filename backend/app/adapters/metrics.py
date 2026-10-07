import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel

log = logging.getLogger(__name__)


class MemoryStats(BaseModel):
    total_bytes: int
    available_bytes: int
    free_bytes: int
    cached_bytes: int
    swap_total_bytes: int
    swap_free_bytes: int

    @property
    def used_bytes(self) -> int:
        return self.total_bytes - self.available_bytes


class DiskStats(BaseModel):
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int


class GpuProcess(BaseModel):
    pid: int
    name: str
    used_bytes: int | None
    container_id: str | None = None


class GpuStats(BaseModel):
    name: str | None = None
    driver: str | None = None
    utilization_pct: float | None = None
    temperature_c: float | None = None
    power_w: float | None = None
    processes: list[GpuProcess] = []

    @property
    def process_bytes(self) -> int:
        return sum(p.used_bytes or 0 for p in self.processes)


CGROUP_ID_RE = re.compile(r"([0-9a-f]{64})")


def container_of_pid(pid: int, proc_root: Path = Path("/proc")) -> str | None:
    """Return the full docker container id owning a host pid (needs pid: host), or None."""
    try:
        text = (proc_root / str(pid) / "cgroup").read_text(encoding="utf-8")
    except OSError:
        return None
    m = CGROUP_ID_RE.search(text)
    return m.group(1) if m else None


def read_meminfo(path: Path = Path("/proc/meminfo")) -> MemoryStats | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    vals: dict[str, int] = {}
    for line in raw.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            vals[key.strip()] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    if "MemTotal" not in vals:
        return None
    return MemoryStats(
        total_bytes=vals["MemTotal"],
        available_bytes=vals.get("MemAvailable", vals.get("MemFree", 0)),
        free_bytes=vals.get("MemFree", 0),
        cached_bytes=vals.get("Cached", 0) + vals.get("Buffers", 0),
        swap_total_bytes=vals.get("SwapTotal", 0),
        swap_free_bytes=vals.get("SwapFree", 0),
    )


def read_disk(path: Path) -> DiskStats | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return DiskStats(path=str(path), total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free)


def _nvsmi(args: list[str]) -> list[list[str]] | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        cmd = ["nvidia-smi", *args, "--format=csv,noheader,nounits"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout
    except (subprocess.SubprocessError, OSError) as e:
        log.debug("nvidia-smi failed: %s", e)
        return None
    return [[c.strip() for c in line.split(",")] for line in out.strip().splitlines() if line.strip()]


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def parse_gpu(gpu_rows: list[list[str]], app_rows: list[list[str]], proc_root: Path = Path("/proc")) -> GpuStats:
    first = (gpu_rows[0] + ["", "", "", "", ""])[:5]
    name, driver, util, temp, power = first
    procs: list[GpuProcess] = []
    for r in app_rows:
        if len(r) < 3 or not r[0].isdigit():
            continue
        mib = _num(r[2])
        pid = int(r[0])
        procs.append(
            GpuProcess(
                pid=pid,
                name=r[1],
                used_bytes=int(mib * 2**20) if mib is not None else None,
                container_id=container_of_pid(pid, proc_root),
            )
        )
    return GpuStats(
        name=name or None,
        driver=driver or None,
        utilization_pct=_num(util),
        temperature_c=_num(temp),
        power_w=_num(power),
        processes=procs,
    )


def read_gpu() -> GpuStats | None:
    rows = _nvsmi(["--query-gpu=name,driver_version,utilization.gpu,temperature.gpu,power.draw"])
    if not rows:
        return None
    return parse_gpu(rows, _nvsmi(["--query-compute-apps=pid,process_name,used_memory"]) or [])


class MetricsProvider:
    def __init__(self, gpu_source: str, meminfo_path: Path, disk_path: Path, gpu_ttl: float = 2.0) -> None:
        self.gpu_source = gpu_source
        self.meminfo_path = meminfo_path
        self.disk_path = disk_path
        self.gpu_ttl = gpu_ttl
        self._gpu_cache: tuple[float, GpuStats | None] | None = None

    def memory(self) -> MemoryStats | None:
        return read_meminfo(self.meminfo_path)

    def disk(self) -> DiskStats | None:
        return read_disk(self.disk_path)

    def gpu(self) -> GpuStats | None:
        if self.gpu_source != "nvidia_smi":
            return None
        now = time.monotonic()
        if self._gpu_cache and now - self._gpu_cache[0] < self.gpu_ttl:
            return self._gpu_cache[1]
        stats = read_gpu()
        self._gpu_cache = (now, stats)
        return stats
