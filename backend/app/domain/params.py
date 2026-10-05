import re
import shlex
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.adapters.model_sources import ModelMeta
from app.profiles import RuntimeProfile

SERVED_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
DTYPES = ["auto", "bfloat16", "float16"]
QUANTIZATIONS = ["auto", "fp8", "awq", "gptq", "compressed-tensors", "modelopt", "modelopt_fp4", "bitsandbytes"]
MIN_CONTEXT = 256
FORBIDDEN_EXTRA = {
    "--host",
    "--port",
    "--served-model-name",
    "--model",
    "--gpu-memory-utilization",
    "--max-model-len",
    "--dtype",
    "--quantization",
    "--trust-remote-code",
}


class InstanceParams(BaseModel):
    max_model_len: int
    gpu_memory_utilization: float
    dtype: str = "auto"
    quantization: str = "auto"
    trust_remote_code: bool = False
    host_port: int | None = None
    extra_args: str = ""


class ParamField(BaseModel):
    name: str
    level: Literal["basic", "advanced"]
    type: Literal["integer", "number", "string", "boolean", "select"]
    widget: str
    default: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    marks: list[int] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    unit: str | None = None
    restart_required: bool = True
    label_key: str
    help_key: str


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-._")
    return (s or "model")[:63]


def context_marks(max_ctx: int | None) -> list[int]:
    base = [4096, 8192, 16384, 32768, 65536, 131072]
    marks = [m for m in base if max_ctx is None or m <= max_ctx]
    if max_ctx and max_ctx not in marks:
        marks.append(max_ctx)
    return marks


def param_schema(profile: RuntimeProfile, model: ModelMeta | None, defaults: InstanceParams | None) -> list[ParamField]:
    mem = profile.memory
    max_ctx = model.max_context if model else None
    d = defaults
    return [
        ParamField(
            name="max_model_len",
            level="basic",
            type="integer",
            widget="slider",
            default=d.max_model_len if d else None,
            min=MIN_CONTEXT,
            max=max_ctx,
            marks=context_marks(max_ctx),
            unit="tokens",
            label_key="params.max_model_len.label",
            help_key="params.max_model_len.help",
        ),
        ParamField(
            name="gpu_memory_utilization",
            level="basic",
            type="number",
            widget="slider",
            default=d.gpu_memory_utilization if d else mem.default,
            min=mem.min,
            max=mem.max,
            step=0.05,
            unit="ratio",
            label_key="params.gpu_memory_utilization.label",
            help_key="params.gpu_memory_utilization.help",
        ),
        ParamField(
            name="quantization",
            level="basic",
            type="select",
            widget="select",
            default=d.quantization if d else "auto",
            options=QUANTIZATIONS,
            label_key="params.quantization.label",
            help_key="params.quantization.help",
        ),
        ParamField(
            name="dtype",
            level="advanced",
            type="select",
            widget="select",
            default=d.dtype if d else "auto",
            options=DTYPES,
            label_key="params.dtype.label",
            help_key="params.dtype.help",
        ),
        ParamField(
            name="trust_remote_code",
            level="advanced",
            type="boolean",
            widget="switch",
            default=bool(model and model.needs_remote_code) if d is None else d.trust_remote_code,
            label_key="params.trust_remote_code.label",
            help_key="params.trust_remote_code.help",
        ),
        ParamField(
            name="host_port",
            level="advanced",
            type="integer",
            widget="number",
            default=None,
            min=1024,
            max=65535,
            label_key="params.host_port.label",
            help_key="params.host_port.help",
        ),
        ParamField(
            name="extra_args",
            level="advanced",
            type="string",
            widget="text",
            default="",
            label_key="params.extra_args.label",
            help_key="params.extra_args.help",
        ),
    ]


def split_extra_args(extra: str) -> list[str]:
    return shlex.split(extra) if extra.strip() else []


def build_command(
    profile: RuntimeProfile, model: ModelMeta, served_model_name: str, params: InstanceParams
) -> list[str]:
    v = profile.vllm
    model_path = f"{v.model_mount}/{model.mount_rel_path}".rstrip("/")
    cmd = [
        *v.command_prefix,
        model_path,
        "--host",
        "0.0.0.0",
        "--port",
        str(v.port),
        "--served-model-name",
        served_model_name,
        "--gpu-memory-utilization",
        f"{params.gpu_memory_utilization:g}",
        "--max-model-len",
        str(params.max_model_len),
    ]
    if params.dtype != "auto":
        cmd += ["--dtype", params.dtype]
    if params.quantization not in ("auto", "", None):
        cmd += ["--quantization", params.quantization]
    if params.trust_remote_code:
        cmd.append("--trust-remote-code")
    cmd += split_extra_args(params.extra_args)
    return cmd
