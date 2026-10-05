from pathlib import Path

import pytest

from app.adapters.metrics import MemoryStats
from app.adapters.model_sources import LocalDirSource, ModelMeta
from app.db.models import Instance
from app.domain.instance import InstanceStatus
from app.domain.params import InstanceParams, build_command, slugify
from app.profiles import load_profile
from app.services.error_classifier import ErrorClassifier
from app.services.planner import PlanInput, Planner, PlanningError
from app.services.presets import PresetResolver
from tests.conftest import QWEN_CONFIG, REPO_ROOT, make_model

GB = 2**30
PROFILE = load_profile(REPO_ROOT / "configs", "spark")
PRESETS = PresetResolver.from_file(REPO_ROOT / "configs" / "presets.yaml", PROFILE)
MEM = MemoryStats(
    total_bytes=120 * GB,
    available_bytes=110 * GB,
    free_bytes=60 * GB,
    cached_bytes=50 * GB,
    swap_total_bytes=0,
    swap_free_bytes=0,
)


@pytest.fixture
def model(tmp_path: Path) -> ModelMeta:
    make_model(tmp_path, "Qwen2.5-0.5B-Instruct", QWEN_CONFIG)
    return LocalDirSource("local", tmp_path, "/data/models").scan()[0]


def codes(plan: object) -> set[str]:
    return {w.code for w in plan.warnings}  # type: ignore[attr-defined]


def test_kv_estimate(model: ModelMeta) -> None:
    assert model.kv_bytes_per_token == 2 * 24 * 2 * 64 * 2


def test_presets(model: ModelMeta) -> None:
    by_id = {p.id: p for p in PRESETS.resolve_all(model)}
    assert set(by_id) == {"balanced", "low_memory", "long_context", "high_throughput", "custom"}
    assert by_id["balanced"].recommended
    assert by_id["balanced"].params.max_model_len == 32768
    assert by_id["balanced"].params.gpu_memory_utilization == 0.7
    assert by_id["low_memory"].params.max_model_len == 8192
    assert by_id["low_memory"].params.gpu_memory_utilization == 0.4
    assert by_id["long_context"].params.max_model_len == 32768
    assert by_id["custom"].params == by_id["balanced"].params
    assert any(e.key == "presets.explain.model_limit" for e in by_id["balanced"].explanations)


def test_presets_unknown_context(model: ModelMeta) -> None:
    m = model.model_copy(update={"max_context": None})
    by_id = {p.id: p for p in PRESETS.resolve_all(m)}
    assert by_id["balanced"].params.max_model_len == 8192
    assert by_id["long_context"].params.max_model_len == 32768


def test_build_command(model: ModelMeta) -> None:
    p = InstanceParams(
        max_model_len=4096,
        gpu_memory_utilization=0.3,
        dtype="bfloat16",
        quantization="fp8",
        trust_remote_code=True,
        extra_args="--enforce-eager --max-num-seqs 8",
    )
    cmd = build_command(PROFILE, model, "smoke-qwen", p)
    assert cmd == [
        "vllm",
        "serve",
        "/models",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--served-model-name",
        "smoke-qwen",
        "--gpu-memory-utilization",
        "0.3",
        "--max-model-len",
        "4096",
        "--dtype",
        "bfloat16",
        "--quantization",
        "fp8",
        "--trust-remote-code",
        "--enforce-eager",
        "--max-num-seqs",
        "8",
    ]


def test_slugify() -> None:
    assert slugify("Qwen2.5-7B Instruct") == "qwen2.5-7b-instruct"
    assert slugify("///") == "model"


def test_plan_defaults(model: ModelMeta) -> None:
    plan = Planner(PROFILE, PRESETS).plan(PlanInput(model_id=model.id), model, [], MEM)
    assert not plan.blocking
    assert plan.served_model_name == "qwen2.5-0.5b-instruct"
    assert plan.display_name == "Qwen2.5-0.5B-Instruct (Balanced)"
    assert plan.estimate.budget_bytes == int(0.7 * 120 * GB)
    assert plan.estimate.kv_cache_bytes == model.kv_bytes_per_token * 32768  # type: ignore[operator]
    assert "PAGE_CACHE_HIGH" in codes(plan)


def test_plan_blocking(model: ModelMeta) -> None:
    other = Instance(
        id="x",
        display_name="x",
        served_model_name="taken",
        model_id="m",
        params={"gpu_memory_utilization": 0.5, "host_port": 18000},
        status=InstanceStatus.READY,
    )
    plan = Planner(PROFILE, PRESETS).plan(
        PlanInput(
            model_id=model.id,
            served_model_name="taken",
            params={"max_model_len": 65536, "host_port": 18000, "extra_args": "--port 9"},
        ),
        model,
        [other],
        MEM,
    )
    assert plan.blocking
    assert {
        "NAME_DUPLICATE",
        "CONTEXT_EXCEEDS_MODEL",
        "HOST_PORT_CONFLICT",
        "EXTRA_ARGS_FORBIDDEN",
        "TOTAL_UTIL_HIGH",
    } <= codes(plan)


def test_plan_exclude_self(model: ModelMeta) -> None:
    me = Instance(id="me", display_name="x", served_model_name="mine", model_id="m", params={})
    plan = Planner(PROFILE, PRESETS).plan(
        PlanInput(model_id=model.id, served_model_name="mine"), model, [me], MEM, exclude_id="me"
    )
    assert "NAME_DUPLICATE" not in codes(plan)


def test_plan_errors(model: ModelMeta) -> None:
    planner = Planner(PROFILE, PRESETS)
    with pytest.raises(PlanningError) as e:
        planner.plan(PlanInput(model_id="nope"), None, [], MEM)
    assert e.value.code == "MODEL_NOT_FOUND"
    with pytest.raises(PlanningError) as e:
        planner.plan(PlanInput(model_id=model.id, preset="zzz"), model, [], MEM)
    assert e.value.code == "PRESET_NOT_FOUND"


def test_tailor_suggestions() -> None:
    from app.domain.errors import ErrorCode
    from app.services.error_classifier import make_error, tailor_suggestions

    err = make_error(ErrorCode.OOM)
    big = tailor_suggestions(err, {"max_model_len": 32768}, 32768)
    assert big.suggestions[0].patch == {"max_model_len": 8192}
    assert big.suggestions[0].params == {"value": 8192}

    small_model = tailor_suggestions(err, {"max_model_len": 4096}, 4096)
    assert small_model.suggestions[0].patch == {"max_model_len": 2048}

    tiny = tailor_suggestions(err, {"max_model_len": 256}, 4096)
    assert all(s.patch is None or "max_model_len" not in s.patch for s in tiny.suggestions)
    assert [s.action for s in tiny.suggestions] == ["apply_preset", "navigate"]


def test_classifier_spark_sample() -> None:
    c = ErrorClassifier.from_file(REPO_ROOT / "configs" / "error-patterns.yaml")
    spark_tail = ["RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {}"]
    assert c.classify(exit_code=1, oom_killed=False, logs=spark_tail).code == "CRASHED"
    logs = [
        "ValueError: No available memory for the cache blocks. Try increasing `gpu_memory_utilization`",
        *spark_tail,
    ]
    err = c.classify(exit_code=1, oom_killed=False, logs=logs)
    assert err.code == "OOM"
    assert "No available memory" in err.evidence[0]
    assert c.classify(exit_code=137, oom_killed=True, logs=[]).code == "OOM"
    assert c.annotate("torch.OutOfMemoryError: CUDA out of memory") == "OOM"
    assert c.annotate("INFO all good") is None
