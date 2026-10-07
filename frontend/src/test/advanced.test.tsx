import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { AdvancedSettings } from "@/api/types";
import { AdvancedCard } from "@/components/settings/AdvancedCard";
import zhTW from "@/i18n/locales/zh-TW.json";
import { mockFetch, renderRoute } from "./utils";

const BASE: AdvancedSettings = {
  verbose_access_log: { value: false, source: "default", default: false },
  hf_endpoint: { value: null, source: "default", default: null },
  health_timeout_min: { value: 15, source: "default", default: 15 },
  timeout_range: [15, 120],
  deploy: {
    profile: "spark",
    model_root: "/data/models",
    model_owner: "1000:1000",
    hf_cache_dir: null,
    gateway_port: 4000,
    gateway_bind: "0.0.0.0",
    gateway_local_only: false,
    vllm_image: "eugr/spark-vllm@sha256:x",
  },
};

type Body = { health_timeout_min?: number; verbose_access_log?: boolean; hf_endpoint?: string | null };
const body = (c: { body: unknown }) => (c.body ?? {}) as Body;

describe("AdvancedCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("saves timeout, toggles verbose, tests and saves endpoint", async () => {
    let state = structuredClone(BASE);
    const calls = mockFetch({
      "GET /settings/advanced": () => state,
      "PUT /settings/advanced": (_u, init) => {
        const b = JSON.parse(String(init?.body));
        if (b.health_timeout_min) state.health_timeout_min = { value: b.health_timeout_min, source: "web", default: 15 };
        if (typeof b.verbose_access_log === "boolean")
          state.verbose_access_log = { value: b.verbose_access_log, source: "web", default: false };
        if ("hf_endpoint" in b) state.hf_endpoint = { value: b.hf_endpoint, source: "web", default: null };
        state = structuredClone(state);
        return state;
      },
      "POST /settings/advanced/test-hf-endpoint": () => ({ ok: true, ms: 120, url: "https://hf-mirror.com" }),
    });
    renderRoute(<AdvancedCard />, "/settings", "/settings");

    const input = await screen.findByTestId("timeout-input");
    expect(screen.getByTestId("timeout-save")).toBeDisabled();
    fireEvent.change(input, { target: { value: "200" } });
    expect(await screen.findByText(zhTW.advanced.timeoutRange.replace("{{lo}}", "15").replace("{{hi}}", "120"))).toBeInTheDocument();
    expect(screen.getByTestId("timeout-save")).toBeDisabled();
    fireEvent.change(input, { target: { value: "45" } });
    fireEvent.click(screen.getByTestId("timeout-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && body(c).health_timeout_min === 45)).toBe(true));
    expect(await screen.findAllByText(zhTW.advanced.source.web)).toHaveLength(1);

    fireEvent.click(screen.getByTestId("verbose-switch"));
    await waitFor(() => expect(calls.some((c) => body(c).verbose_access_log === true)).toBe(true));

    fireEvent.change(screen.getByTestId("endpoint-input"), { target: { value: "https://hf-mirror.com" } });
    fireEvent.click(screen.getByTestId("endpoint-test"));
    expect(await screen.findByTestId("endpoint-test-result")).toHaveTextContent("hf-mirror.com");
    fireEvent.click(screen.getByTestId("endpoint-save"));
    await waitFor(() => expect(calls.some((c) => body(c).hf_endpoint === "https://hf-mirror.com")).toBe(true));
  });
});
