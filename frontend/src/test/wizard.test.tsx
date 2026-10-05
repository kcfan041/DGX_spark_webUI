import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { Instance, ModelMeta, ParamField, Plan, ResolvedPreset } from "@/api/types";
import zhTW from "@/i18n/locales/zh-TW.json";
import { CreateServicePage } from "@/pages/CreateServicePage";
import { mockFetch, renderRoute } from "./utils";

const MODEL: ModelMeta = {
  id: "local:Qwen2.5-0.5B-Instruct",
  source: "local",
  locator: "Qwen2.5-0.5B-Instruct",
  name: "Qwen2.5-0.5B-Instruct",
  size_bytes: 999588520,
  architecture: "Qwen2ForCausalLM",
  model_type: "qwen2",
  quantization: null,
  dtype: "bfloat16",
  max_context: 32768,
  needs_remote_code: false,
  host_path: "/data/models/Qwen2.5-0.5B-Instruct",
  in_use_by: [],
};

const params = (ctx: number, mem: number) => ({
  max_model_len: ctx,
  gpu_memory_utilization: mem,
  dtype: "auto",
  quantization: "auto",
  trust_remote_code: false,
  host_port: null,
  extra_args: "",
});

const PRESETS: ResolvedPreset[] = [
  { id: "balanced", label_key: "", description_key: null, recommended: true, params: params(32768, 0.7), explanations: [] },
  { id: "low_memory", label_key: "", description_key: null, recommended: false, params: params(8192, 0.4), explanations: [] },
];

const SCHEMA: ParamField[] = [
  { name: "max_model_len", level: "basic", type: "integer", widget: "slider", default: 32768, min: 256, max: 32768, step: null, marks: [4096, 8192, 32768], options: [], unit: "tokens", restart_required: true, label_key: "", help_key: "" },
  { name: "gpu_memory_utilization", level: "basic", type: "number", widget: "slider", default: 0.7, min: 0.1, max: 0.95, step: 0.05, marks: [], options: [], unit: "ratio", restart_required: true, label_key: "", help_key: "" },
  { name: "quantization", level: "basic", type: "select", widget: "select", default: "auto", min: null, max: null, step: null, marks: [], options: ["auto", "fp8"], unit: null, restart_required: true, label_key: "", help_key: "" },
  { name: "dtype", level: "advanced", type: "select", widget: "select", default: "auto", min: null, max: null, step: null, marks: [], options: ["auto", "bfloat16"], unit: null, restart_required: true, label_key: "", help_key: "" },
];

function plan(body: { params: { gpu_memory_utilization: number; max_model_len: number } }, blocking = false): Plan {
  return {
    model_id: MODEL.id,
    preset: "low_memory",
    display_name: "x",
    served_model_name: "qwen2.5-0.5b-instruct",
    params: params(body.params.max_model_len, body.params.gpu_memory_utilization),
    autostart: false,
    autostart_order: 100,
    estimate: {
      weights_bytes: 999588520,
      kv_cache_bytes: 50331648,
      overhead_bytes: 2147483648,
      total_bytes: 3197403816,
      budget_bytes: 39198293606,
      system_total_bytes: 130660978688,
      system_available_bytes: 126162673664,
      system_free_bytes: 53314772992,
      other_services_ratio: 0,
    },
    warnings: blocking ? [{ code: "NAME_DUPLICATE", level: "blocking", params: { name: "qwen2.5-0.5b-instruct" } }] : [{ code: "PAGE_CACHE_HIGH", level: "info", params: {} }],
    command: ["vllm", "serve", "/models"],
    blocking,
  };
}

describe("CreateServicePage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("walks model → preset → settings → confirm and creates + starts", async () => {
    const calls = mockFetch({
      "GET /models": () => [MODEL],
      "GET /presets": () => PRESETS,
      "GET /param-schema": () => SCHEMA,
      "GET /system/summary": () => ({ memory: { total_bytes: 130660978688 } }),
      "POST /instances/preview": (_u, init) => plan(JSON.parse(String(init?.body))),
      "POST /instances": () => ({ id: "abc123" }) as Partial<Instance>,
    });
    renderRoute(<CreateServicePage />, `/services/new?model=${encodeURIComponent(MODEL.id)}`, "/services/new");

    await screen.findByTestId("preset-low_memory");
    expect(screen.getByText(zhTW.wizard.selectPreset)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("preset-low_memory"));
    fireEvent.click(screen.getByRole("button", { name: zhTW.common.next }));

    await screen.findByText(zhTW.params.max_model_len.label);
    expect(screen.getByDisplayValue("qwen2.5-0.5b-instruct")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: zhTW.params.max_model_len.label })).toHaveValue("8192");
    fireEvent.click(screen.getByRole("button", { name: zhTW.common.next }));

    await screen.findByText(zhTW.estimate.title);
    expect(screen.getByText(/目前有大量系統快取/)).toBeInTheDocument();
    const create = await screen.findByTestId("create-and-start");
    await waitFor(() => expect(create).toBeEnabled());
    fireEvent.click(create);

    await screen.findByTestId("navigated");
    const post = calls.find((c) => c.method === "POST" && c.url === "/api/v1/instances");
    expect(post?.body).toMatchObject({
      model_id: MODEL.id,
      preset: "low_memory",
      start: true,
      served_model_name: "qwen2.5-0.5b-instruct",
      params: { max_model_len: 8192, gpu_memory_utilization: 0.4 },
    });
  });

  it("disables create when the plan is blocking", async () => {
    mockFetch({
      "GET /models": () => [MODEL],
      "GET /presets": () => PRESETS,
      "GET /param-schema": () => SCHEMA,
      "GET /system/summary": () => ({}),
      "POST /instances/preview": (_u, init) => plan(JSON.parse(String(init?.body)), true),
    });
    renderRoute(<CreateServicePage />, `/services/new?model=${encodeURIComponent(MODEL.id)}`, "/services/new");
    await screen.findByTestId("preset-balanced");
    fireEvent.click(screen.getByRole("button", { name: zhTW.common.next }));
    await screen.findByText(zhTW.params.max_model_len.label);
    fireEvent.click(screen.getByRole("button", { name: zhTW.common.next }));
    await screen.findByText(/已被其他模型服務使用/);
    expect(screen.getByTestId("create-and-start")).toBeDisabled();
  });
});
