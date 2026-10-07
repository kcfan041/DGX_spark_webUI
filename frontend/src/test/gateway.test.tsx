import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import zhTW from "@/i18n/locales/zh-TW.json";
import { GatewayPage } from "@/pages/GatewayPage";
import { mockFetch, renderRoute } from "./utils";

const FULL_KEY = "sk-ABCDEFGHIJKLMNOPQRSTUV";

describe("GatewayPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("creates a key, shows it once, requires acknowledgement, then lists it masked", async () => {
    let keys: unknown[] = [];
    const calls = mockFetch({
      "GET /gateway/status": () => ({ reachable: true, db_connected: true }),
      "GET /gateway/connection-info": () => ({ api_base: "http://spark:4000/v1", source: "auto", warnings: [], models: ["qwen-small"] }),
      "GET /gateway/models": () => [
        { model_name: "qwen-small", gateway_model_id: "m1", instance_id: "i1", instance_name: "Qwen", instance_status: "READY", sync: "ok" },
      ],
      "GET /gateway/keys": () => keys,
      "POST /gateway/keys": () => {
        const row = { id: "h1", name: "院內系統A", masked: "sk-...STUV", status: "active", created_at: "2026-10-05T06:35:09Z", last_active: null, system: false, expires_at: null, spend: 0, budget_reset_at: null, limits: { max_budget: null, budget_duration: null, rpm_limit: null, tpm_limit: null, models: [] } };
        keys = [row];
        return { ...row, key: FULL_KEY };
      },
    });
    renderRoute(<GatewayPage />, "/gateway", "/gateway");

    await screen.findByText(zhTW.gateway.keys.empty);
    expect(screen.getAllByText("qwen-small").length).toBeGreaterThan(0);
    const createBtn = await screen.findByTestId("create-key");
    await waitFor(() => expect(createBtn).toBeEnabled());
    fireEvent.click(createBtn);

    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByPlaceholderText(zhTW.gateway.keys.namePlaceholder), { target: { value: "院內系統A" } });
    fireEvent.click(within(dialog).getByRole("button", { name: zhTW.gateway.keys.create }));

    expect(await screen.findByTestId("new-key")).toHaveTextContent(FULL_KEY);
    expect(screen.getByText(zhTW.gateway.keys.onlyOnce)).toBeInTheDocument();
    const closeBtn = screen.getByTestId("close-created");
    expect(closeBtn).toBeDisabled();
    fireEvent.click(screen.getByTestId("saved-confirm"));
    expect(closeBtn).toBeEnabled();
    fireEvent.click(closeBtn);

    await waitFor(() => expect(screen.queryByTestId("new-key")).not.toBeInTheDocument());
    await screen.findByText("sk-...STUV");
    expect(screen.queryByText(FULL_KEY)).not.toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST" && c.url.endsWith("/gateway/keys"))?.body).toEqual({
      name: "院內系統A",
      expires_in: null,
      max_budget: null,
      budget_duration: null,
      rpm_limit: null,
      tpm_limit: null,
      models: [],
    });
  });

  it("disables key creation when gateway is down", async () => {
    mockFetch({
      "GET /gateway/status": () => ({ reachable: false, db_connected: false }),
      "GET /gateway/connection-info": () => ({ api_base: "http://spark:4000/v1", source: "auto", warnings: [], models: [] }),
      "GET /gateway/models": () => [],
      "GET /gateway/keys": () => [],
    });
    renderRoute(<GatewayPage />, "/gateway", "/gateway");
    await screen.findByText(zhTW.errors.GATEWAY_UNREACHABLE.description);
    expect(screen.getByTestId("create-key")).toBeDisabled();
  });
});
