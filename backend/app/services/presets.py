from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.adapters.model_sources import ModelMeta
from app.domain.params import MIN_CONTEXT, InstanceParams
from app.profiles import RuntimeProfile


class Explanation(BaseModel):
    field: str
    key: str
    params: dict[str, Any] = Field(default_factory=dict)


class ResolvedPreset(BaseModel):
    id: str
    label_key: str
    description_key: str | None = None
    recommended: bool = False
    params: InstanceParams
    explanations: list[Explanation]


def _lookup(path: str, profile: RuntimeProfile, model: ModelMeta) -> Any:
    root, _, rest = path.partition(".")
    obj: Any = {"profile": profile, "model": model}.get(root)
    for part in rest.split(".") if rest else []:
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _resolve_rule(
    field: str, rule: dict[str, Any], profile: RuntimeProfile, model: ModelMeta
) -> tuple[Any, Explanation]:
    fallback = rule.get("fallback")
    if "value" in rule:
        return rule["value"], Explanation(field=field, key="presets.explain.fixed", params={"value": rule["value"]})
    if "min" in rule:
        vals = [_lookup(x, profile, model) if isinstance(x, str) else x for x in rule["min"]]
        known = [v for v in vals if v is not None]
        if len(known) < len(vals) and fallback is not None:
            limit = min([*known, fallback]) if known else fallback
            return limit, Explanation(field=field, key="presets.explain.unknown_fallback", params={"value": limit})
        val = min(known) if known else fallback
        src_ctx = vals[0] if vals else None
        key = "presets.explain.model_limit" if val == src_ctx else "presets.explain.preset_limit"
        return val, Explanation(field=field, key=key, params={"value": val, "model_max": src_ctx})
    if "from" in rule:
        val = _lookup(rule["from"], profile, model)
        if val is None:
            return fallback, Explanation(
                field=field, key="presets.explain.unknown_fallback", params={"value": fallback}
            )
        if "cap" in rule and isinstance(val, int | float):
            capped = min(val, rule["cap"])
            key = "presets.explain.capped" if capped != val else "presets.explain.from_source"
            return capped, Explanation(field=field, key=key, params={"value": capped, "source": rule["from"]})
        return val, Explanation(
            field=field, key="presets.explain.from_source", params={"value": val, "source": rule["from"]}
        )
    return fallback, Explanation(field=field, key="presets.explain.fixed", params={"value": fallback})


class PresetResolver:
    def __init__(self, presets: dict[str, dict[str, Any]], profile: RuntimeProfile) -> None:
        self.presets = presets
        self.profile = profile

    @classmethod
    def from_file(cls, path: Path, profile: RuntimeProfile) -> "PresetResolver":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return cls(data or {}, profile)

    def ids(self) -> list[str]:
        return list(self.presets)

    def _rules(self, preset_id: str) -> dict[str, Any]:
        p = self.presets[preset_id]
        base = self._rules(p["inherits"]) if p.get("inherits") else {}
        return {**base, **(p.get("rules") or {})}

    def resolve(self, preset_id: str, model: ModelMeta) -> ResolvedPreset:
        if preset_id not in self.presets:
            raise KeyError(preset_id)
        p = self.presets[preset_id]
        values: dict[str, Any] = {}
        explanations: list[Explanation] = []
        for field, rule in self._rules(preset_id).items():
            val, exp = _resolve_rule(field, rule, self.profile, model)
            values[field] = val
            explanations.append(exp)
        if values.get("max_model_len") is not None:
            values["max_model_len"] = max(int(values["max_model_len"]), MIN_CONTEXT)
        values.setdefault("gpu_memory_utilization", self.profile.memory.default)
        values.setdefault("max_model_len", model.max_context or 4096)
        quant = values.get("quantization")
        values["quantization"] = quant if isinstance(quant, str) and quant else "auto"
        values["trust_remote_code"] = model.needs_remote_code
        return ResolvedPreset(
            id=preset_id,
            label_key=p.get("label_key", f"presets.{preset_id}.label"),
            description_key=p.get("description_key"),
            recommended=bool(p.get("recommended")),
            params=InstanceParams(**values),
            explanations=explanations,
        )

    def resolve_all(self, model: ModelMeta) -> list[ResolvedPreset]:
        return [self.resolve(pid, model) for pid in self.presets]
