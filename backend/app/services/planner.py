from typing import Any, Literal

from pydantic import BaseModel, Field

from app.adapters.metrics import MemoryStats
from app.adapters.model_sources import ModelMeta
from app.db.models import Instance
from app.domain.instance import ACTIVE_STATUSES
from app.domain.params import (
    FORBIDDEN_EXTRA,
    MIN_CONTEXT,
    SERVED_NAME_RE,
    InstanceParams,
    build_command,
    slugify,
    split_extra_args,
)
from app.profiles import RuntimeProfile
from app.services.presets import FIT_OVERHEAD_BYTES, PresetResolver

OVERHEAD_BYTES = FIT_OVERHEAD_BYTES

Level = Literal["info", "warning", "blocking"]


class Warning_(BaseModel):
    code: str
    level: Level
    params: dict[str, Any] = Field(default_factory=dict)


class MemoryEstimate(BaseModel):
    weights_bytes: int | None
    kv_cache_bytes: int | None
    overhead_bytes: int
    total_bytes: int | None
    budget_bytes: int | None
    system_total_bytes: int | None
    system_available_bytes: int | None
    system_free_bytes: int | None
    other_services_ratio: float
    note_key: str = "estimate.disclaimer"


class PlanInput(BaseModel):
    model_id: str
    preset: str = "balanced"
    params: dict[str, Any] = Field(default_factory=dict)
    display_name: str | None = None
    served_model_name: str | None = None
    autostart: bool = False
    autostart_order: int = 100


class Plan(BaseModel):
    model_id: str
    preset: str
    display_name: str
    served_model_name: str
    params: InstanceParams
    autostart: bool
    autostart_order: int
    estimate: MemoryEstimate
    warnings: list[Warning_]
    command: list[str]
    blocking: bool


class PlanningError(Exception):
    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.params = params or {}


PRESET_LABELS = {
    "balanced": "Balanced",
    "low_memory": "Low Memory",
    "long_context": "Long Context",
    "high_throughput": "High Throughput",
    "custom": "Custom",
}


class Planner:
    def __init__(self, profile: RuntimeProfile, presets: PresetResolver) -> None:
        self.profile = profile
        self.presets = presets

    def plan(
        self,
        inp: PlanInput,
        model: ModelMeta | None,
        others: list[Instance],
        memory: MemoryStats | None,
        exclude_id: str | None = None,
    ) -> Plan:
        if model is None:
            raise PlanningError("MODEL_NOT_FOUND", {"model_id": inp.model_id})
        if inp.preset not in self.presets.ids():
            raise PlanningError("PRESET_NOT_FOUND", {"preset": inp.preset})

        base = self.presets.resolve(inp.preset, model).params.model_dump()
        merged = {**base, **{k: v for k, v in inp.params.items() if k in InstanceParams.model_fields}}
        try:
            params = InstanceParams(**merged)
        except ValueError as e:
            raise PlanningError("PARAMS_INVALID", {"detail": str(e)}) from e

        served = inp.served_model_name or slugify(model.name.split("/")[-1])
        display = inp.display_name or f"{model.name.split('/')[-1]} ({PRESET_LABELS.get(inp.preset, inp.preset)})"
        others = [o for o in others if o.id != exclude_id]

        warnings = self._validate(model, served, params, others)
        estimate = self._estimate(model, params, others, memory)
        warnings += self._memory_warnings(model, params, estimate, others, inp.autostart)

        return Plan(
            model_id=model.id,
            preset=inp.preset,
            display_name=display,
            served_model_name=served,
            params=params,
            autostart=inp.autostart,
            autostart_order=inp.autostart_order,
            estimate=estimate,
            warnings=warnings,
            command=build_command(self.profile, model, served, params),
            blocking=any(w.level == "blocking" for w in warnings),
        )

    def _validate(
        self, model: ModelMeta, served: str, params: InstanceParams, others: list[Instance]
    ) -> list[Warning_]:
        w: list[Warning_] = []
        mem = self.profile.memory
        if not SERVED_NAME_RE.match(served):
            w.append(Warning_(code="NAME_INVALID", level="blocking", params={"name": served}))
        if any(o.served_model_name == served for o in others):
            w.append(Warning_(code="NAME_DUPLICATE", level="blocking", params={"name": served}))

        if params.max_model_len < MIN_CONTEXT:
            w.append(Warning_(code="CONTEXT_TOO_SMALL", level="blocking", params={"min": MIN_CONTEXT}))
        if model.max_context is None:
            w.append(Warning_(code="CONTEXT_MODEL_UNKNOWN", level="warning"))
        elif params.max_model_len > model.max_context:
            w.append(
                Warning_(
                    code="CONTEXT_EXCEEDS_MODEL",
                    level="blocking",
                    params={"value": params.max_model_len, "max": model.max_context},
                )
            )

        if not mem.min <= params.gpu_memory_utilization <= mem.max:
            w.append(
                Warning_(
                    code="MEM_UTIL_OUT_OF_RANGE",
                    level="blocking",
                    params={"value": params.gpu_memory_utilization, "min": mem.min, "max": mem.max},
                )
            )

        if params.trust_remote_code:
            w.append(Warning_(code="REMOTE_CODE_ENABLED", level="warning"))
        elif model.needs_remote_code:
            w.append(Warning_(code="REMOTE_CODE_LIKELY_REQUIRED", level="warning"))

        try:
            extra = split_extra_args(params.extra_args)
        except ValueError:
            extra = []
            w.append(Warning_(code="EXTRA_ARGS_INVALID", level="blocking"))
        bad = sorted({a.split("=", 1)[0] for a in extra if a.split("=", 1)[0] in FORBIDDEN_EXTRA})
        if bad:
            w.append(Warning_(code="EXTRA_ARGS_FORBIDDEN", level="blocking", params={"args": bad}))
        elif extra:
            w.append(Warning_(code="EXTRA_ARGS_PRESENT", level="info"))

        if params.host_port is not None:
            if not 1024 <= params.host_port <= 65535:
                w.append(Warning_(code="HOST_PORT_INVALID", level="blocking", params={"port": params.host_port}))
            elif any((o.params or {}).get("host_port") == params.host_port for o in others):
                w.append(Warning_(code="HOST_PORT_CONFLICT", level="blocking", params={"port": params.host_port}))
        return w

    def _estimate(
        self, model: ModelMeta, params: InstanceParams, others: list[Instance], memory: MemoryStats | None
    ) -> MemoryEstimate:
        weights = model.size_bytes
        kv = model.kv_bytes_per_token * params.max_model_len if model.kv_bytes_per_token else None
        total = (weights or 0) + (kv or 0) + OVERHEAD_BYTES if weights is not None else None
        sys_total = memory.total_bytes if memory else None
        other_ratio = sum(
            float((o.params or {}).get("gpu_memory_utilization", 0)) for o in others if o.status in ACTIVE_STATUSES
        )
        return MemoryEstimate(
            weights_bytes=weights,
            kv_cache_bytes=kv,
            overhead_bytes=OVERHEAD_BYTES,
            total_bytes=total,
            budget_bytes=int(params.gpu_memory_utilization * sys_total) if sys_total else None,
            system_total_bytes=sys_total,
            system_available_bytes=memory.available_bytes if memory else None,
            system_free_bytes=memory.free_bytes if memory else None,
            other_services_ratio=round(other_ratio, 3),
        )

    def _memory_warnings(
        self, model: ModelMeta, params: InstanceParams, est: MemoryEstimate, others: list[Instance], autostart: bool
    ) -> list[Warning_]:
        w: list[Warning_] = []
        mem = self.profile.memory
        if est.weights_bytes and est.system_total_bytes and est.weights_bytes > est.system_total_bytes:
            w.append(Warning_(code="WEIGHTS_EXCEED_TOTAL", level="blocking"))
        elif est.total_bytes and est.budget_bytes and est.total_bytes > est.budget_bytes:
            w.append(
                Warning_(
                    code="ESTIMATE_EXCEEDS_BUDGET",
                    level="warning",
                    params={"estimate": est.total_bytes, "budget": est.budget_bytes},
                )
            )
        combined = est.other_services_ratio + params.gpu_memory_utilization
        if est.other_services_ratio > 0 and combined > mem.total_warning:
            w.append(
                Warning_(
                    code="TOTAL_UTIL_HIGH",
                    level="warning",
                    params={"others": est.other_services_ratio, "combined": round(combined, 3)},
                )
            )
        if est.budget_bytes and est.system_available_bytes and est.budget_bytes > est.system_available_bytes:
            w.append(
                Warning_(
                    code="AVAILABLE_LOW",
                    level="warning",
                    params={"budget": est.budget_bytes, "available": est.system_available_bytes},
                )
            )
        if (
            est.budget_bytes
            and est.system_free_bytes is not None
            and est.system_available_bytes
            and est.system_free_bytes < est.budget_bytes <= est.system_available_bytes
        ):
            w.append(
                Warning_(
                    code="PAGE_CACHE_HIGH",
                    level="info",
                    params={"free": est.system_free_bytes, "available": est.system_available_bytes},
                )
            )
        if est.budget_bytes:
            w.append(
                Warning_(
                    code="RESERVES_UP_FRONT",
                    level="info",
                    params={"budget": est.budget_bytes, "ratio": params.gpu_memory_utilization},
                )
            )
        if (
            est.total_bytes
            and est.budget_bytes
            and est.budget_bytes > est.total_bytes * 4
            and est.budget_bytes > 20 * 2**30
        ):
            w.append(
                Warning_(
                    code="RESERVE_MUCH_LARGER",
                    level="info",
                    params={"budget": est.budget_bytes, "estimate": est.total_bytes},
                )
            )
        if autostart:
            auto_ratio = params.gpu_memory_utilization + sum(
                float((o.params or {}).get("gpu_memory_utilization", 0)) for o in others if o.autostart
            )
            if auto_ratio > mem.total_warning:
                w.append(
                    Warning_(code="AUTOSTART_TOTAL_HIGH", level="warning", params={"combined": round(auto_ratio, 3)})
                )
        return w
