import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.domain.errors import ErrorCode, InstanceError, Suggestion

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
                    return make_error(p.code, evidence=hits[-5:], params={"exit_code": exit_code})
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
