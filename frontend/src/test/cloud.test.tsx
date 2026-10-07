import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import zhTW from "@/i18n/locales/zh-TW.json";
import { CloudPage } from "@/pages/CloudPage";
import { mockFetch, renderRoute } from "./utils";

const SPECS = [
  { type: "openai", needs_api_base: false, api_key_required: true, test_model: "gpt-4o-mini", catalog_provider: "openai", key_url: null },
  { type: "anthropic", needs_api_base: false, api_key_required: true, test_model: "claude-haiku-4-5", catalog_provider: "anthropic", key_url: null },
  { type: "gemini", needs_api_base: false, api_key_required: true, test_model: "gemini-2.5-flash", catalog_provider: "gemini", key_url: null },
  { type: "openai_compatible", needs_api_base: true, api_key_required: false, test_model: null, catalog_provider: null, key_url: null },
];

describe("CloudPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("adds a provider after a connection test, never echoes the key, then opens add-model", async () => {
    let providers: unknown[] = [];
    const calls = mockFetch({
      "GET /gateway/status": () => ({ reachable: true, db_connected: true }),
      "GET /cloud/provider-types": () => SPECS,
      "GET /cloud/providers": () => providers,
      "GET /cloud/models": () => [],
      "GET /cloud/routing": () => ({ fallbacks: [], num_retries: 2, models: [] }),
      "GET /cloud/catalog/openai": () => [{ id: "gpt-4o-mini", input_per_mtok: 0.15, output_per_mtok: 0.6, max_input_tokens: 128000 }],
      "POST /cloud/test": () => ({ ok: true, model: "gpt-4o-mini", error: null }),
      "POST /cloud/providers": () => {
        const p = { id: "dgxsp-x", type: "openai", name: "OpenAI", api_base: null, masked_key: "sk****cd", models: 0 };
        providers = [p];
        return p;
      },
    });
    renderRoute(<CloudPage />, "/cloud", "/cloud");
    await screen.findByText(zhTW.cloud.provider.empty);
    fireEvent.click(screen.getByTestId("add-provider"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByTestId("provider-name"), { target: { value: "OpenAI" } });
    fireEvent.change(within(dialog).getByTestId("provider-key"), { target: { value: "sk-secret-abcd" } });
    fireEvent.click(within(dialog).getByTestId("provider-test"));
    expect(await within(dialog).findByTestId("provider-test-result")).toHaveTextContent("gpt-4o-mini");
    fireEvent.click(within(dialog).getByTestId("provider-save"));

    await screen.findByText(zhTW.cloud.model.addTitle);
    await screen.findByTestId("provider-row-OpenAI");
    expect(screen.queryByText("sk-secret-abcd")).not.toBeInTheDocument();
    expect(screen.getByText("sk****cd")).toBeInTheDocument();
    const create = calls.find((c) => c.method === "POST" && c.url.endsWith("/cloud/providers"));
    expect(create?.body).toEqual({ type: "openai", name: "OpenAI", api_key: "sk-secret-abcd", api_base: null });
    expect(calls.find((c) => c.url.endsWith("/cloud/test"))?.body).toMatchObject({ type: "openai", api_key: "sk-secret-abcd" });
  });

  it("requires api base for OpenAI-compatible providers", async () => {
    mockFetch({
      "GET /gateway/status": () => ({ reachable: true, db_connected: true }),
      "GET /cloud/provider-types": () => SPECS,
      "GET /cloud/providers": () => [],
      "GET /cloud/models": () => [],
      "GET /cloud/routing": () => ({ fallbacks: [], num_retries: 2, models: [] }),
    });
    renderRoute(<CloudPage />, "/cloud", "/cloud");
    fireEvent.click(await screen.findByTestId("add-provider"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByText(zhTW.cloud.types.openai_compatible));
    const save = within(dialog).getByTestId("provider-save");
    fireEvent.change(within(dialog).getByTestId("provider-name"), { target: { value: "Groq" } });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByTestId("provider-base"), { target: { value: "https://api.groq.com/openai/v1" } });
    await waitFor(() => expect(save).toBeEnabled());
  });

  it("shows fallback rules and the active alias for a stopped local model", async () => {
    const calls = mockFetch({
      "GET /gateway/status": () => ({ reachable: true, db_connected: true }),
      "GET /cloud/provider-types": () => SPECS,
      "GET /cloud/providers": () => [{ id: "p", type: "openai", name: "OA", api_base: null, masked_key: "sk****cd", models: 1 }],
      "GET /cloud/models": () => [
        {
          id: "m1",
          name: "gpt-4o-mini",
          model: "gpt-4o-mini",
          provider_id: "p",
          provider_name: "OA",
          provider_type: "openai",
          input_per_mtok: 0.15,
          output_per_mtok: 0.6,
          custom_price: false,
        },
      ],
      "GET /cloud/routing": () => ({
        fallbacks: [{ model: "qwen", targets: ["gpt-4o-mini"], active_alias: "gpt-4o-mini" }],
        num_retries: 2,
        models: ["gpt-4o-mini", "qwen"],
      }),
      "PUT /cloud/routing/fallbacks": () => ({ fallbacks: [], num_retries: 2, models: ["gpt-4o-mini", "qwen"] }),
    });
    renderRoute(<CloudPage />, "/cloud", "/cloud");
    const row = await screen.findByTestId("fallback-qwen");
    expect(row).toHaveTextContent("gpt-4o-mini");
    expect(within(row).getByText(zhTW.cloud.fallback.active.replace("{{target}}", "gpt-4o-mini"))).toBeInTheDocument();
    expect(screen.getByTestId("cloud-model-gpt-4o-mini")).toHaveTextContent("$0.15");

    fireEvent.click(within(row).getByText(zhTW.common.delete));
    const confirm = await screen.findByRole("dialog");
    fireEvent.click(within(confirm).getByRole("button", { name: zhTW.common.delete }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ model: "qwen", targets: [] });
  });
});
