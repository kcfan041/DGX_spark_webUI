import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.domain.errors import ErrorCode, InstanceError, Suggestion
from app.domain.params import MIN_CONTEXT

ERRORISH = re.compile(r"(error|exception|traceback|failed|out of memory)", re.IGNORECASE)


@dataclass
class Pattern:
    code: ErrorCode
    oom_killed: bool | None = None
    exit_codes: list[int] = field(default_factory=list)
    log: list[re.Pattern[str]] = field(default_factory=list)


SUGGESTIONS: dict[ErrorCode, list[Suggestion]] = {
    ErrorCode.OOM: [
        Suggestion(action="edit", label_key="errors.OOM.suggest.reduce_context", patch={"max_model_len": 8192}),
        Suggestion(action="apply_preset", label_key="errors.OOM.suggest.low_memory", preset="low_memory"),
        Suggestion(action="navigate", label_key="errors.OOM.suggest.view_running", target="/services?status=ready"),
    ],
    ErrorCode.GPU_MEMORY_IN_USE: [
        Suggestion(
            action="navigate", label_key="errors.GPU_MEMORY_IN_USE.suggest.stop_others", target="/services?status=ready"
        ),
        Suggestion(
            action="edit",
            label_key="errors.GPU_MEMORY_IN_USE.suggest.lower_ratio",
            patch={"gpu_memory_utilization": None},
        ),
    ],
    ErrorCode.REMOTE_CODE_REQUIRED: [
        Suggestion(
            action="edit", label_key="errors.REMOTE_CODE_REQUIRED.suggest.enable", patch={"trust_remote_code": True}
        ),
    ],
    ErrorCode.MODEL_NOT_FOUND: [
        Suggestion(action="navigate", label_key="errors.MODEL_NOT_FOUND.suggest.rescan", target="/models"),
    ],
    ErrorCode.HEALTH_TIMEOUT: [Suggestion(action="logs", label_key="errors.common.view_logs")],
    ErrorCode.CRASHED: [Suggestion(action="restart", label_key="errors.common.restart")],
    ErrorCode.CONTAINER_MISSING: [Suggestion(action="restart", label_key="errors.common.restart")],
    ErrorCode.PORT_CONFLICT: [
        Suggestion(action="edit", label_key="errors.PORT_CONFLICT.suggest.clear_port", patch={"host_port": None}),
    ],
    ErrorCode.UNKNOWN: [Suggestion(action="logs", label_key="errors.common.view_logs")],
}


MIN_RATIO = 0.05


def _ratio_target(err: InstanceError, current: float) -> float | None:
    try:
        free = float(err.params["free_gib"])
        total = float(err.params["total_gib"])
    except (KeyError, TypeError, ValueError):
        return None
    if total <= 0:
        return None
    target = math.floor((free / total - 0.02) * 100) / 100
    if target < MIN_RATIO or target >= current:
        return None
    return round(target, 2)


def tailor_suggestions(err: InstanceError, current: dict[str, Any], model_max_context: int | None) -> InstanceError:
    """Make generic suggestions concrete for this instance; drop ones that would not change anything."""
    out: list[Suggestion] = []
    for s in err.suggestions:
        patch = dict(s.patch or {})
        if "gpu_memory_utilization" in patch:
            target = _ratio_target(err, float(current.get("gpu_memory_utilization") or 0))
            if target is None:
                continue
            patch["gpu_memory_utilization"] = target
            s = s.model_copy(update={"patch": patch, "params": {**s.params, "value": round(target * 100)}})
        if "max_model_len" in patch:
            cur = int(current.get("max_model_len") or 0)
            limits = [int(patch["max_model_len"]), cur // 2 if cur else int(patch["max_model_len"])]
            if model_max_context:
                limits.append(model_max_context)
            target = max(MIN_CONTEXT, min(limits))
            target -= target % 256
            if not cur or target >= cur:
                continue
            patch["max_model_len"] = target
            s = s.model_copy(update={"patch": patch, "params": {**s.params, "value": target}})
        out.append(s)
    return err.model_copy(update={"suggestions": out})


def make_error(
    code: ErrorCode, *, evidence: list[str] | None = None, params: dict[str, Any] | None = None, severity: str = "error"
) -> InstanceError:
    return InstanceError(
        code=code,
        severity=severity,
        params=params or {},
        evidence=evidence or [],
        suggestions=SUGGESTIONS.get(code, []),
        occurred_at=datetime.now(UTC),
    )


class ErrorClassifier:
    def __init__(self, patterns: list[Pattern]) -> None:
        self.patterns = patterns

    @classmethod
    def from_file(cls, path: Path) -> "ErrorClassifier":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else []
        patterns = []
        for item in raw or []:
            m = item.get("match") or {}
            patterns.append(
                Pattern(
                    code=ErrorCode(item["code"]),
                    oom_killed=m.get("oom_killed"),
                    exit_codes=list(m.get("exit_code") or []),
                    log=[re.compile(p, re.IGNORECASE) for p in m.get("log") or []],
                )
            )
        return cls(patterns)

    def classify(
        self, *, exit_code: int | None, oom_killed: bool, logs: list[str], default: ErrorCode = ErrorCode.CRASHED
    ) -> InstanceError:
        for p in self.patterns:
            if p.oom_killed is not None and p.oom_killed == oom_killed and oom_killed:
                return make_error(p.code, evidence=self._tail_errors(logs), params={"exit_code": exit_code})
            if p.exit_codes and exit_code in p.exit_codes:
                return make_error(p.code, evidence=self._tail_errors(logs), params={"exit_code": exit_code})
            if p.log:
                hits = [ln for ln in logs if any(rx.search(ln) for rx in p.log)]
                if hits:
                    params: dict[str, Any] = {"exit_code": exit_code}
                    for ln in hits:
                        for rx in p.log:
                            m = rx.search(ln)
                            if m:
                                params.update({k: v for k, v in m.groupdict().items() if v is not None})
                    return make_error(p.code, evidence=hits[-5:], params=params)
        return make_error(default, evidence=self._tail_errors(logs), params={"exit_code": exit_code})

    def annotate(self, line: str) -> str | None:
        for p in self.patterns:
            if p.log and any(rx.search(line) for rx in p.log):
                return p.code.value
        return None

    @staticmethod
    def _tail_errors(logs: list[str], n: int = 5) -> list[str]:
        hits = [ln for ln in logs if ERRORISH.search(ln)]
        return (hits or logs)[-n:]
