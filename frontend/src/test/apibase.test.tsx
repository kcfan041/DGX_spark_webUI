import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ApiBaseInfo } from "@/api/types";
import { ApiBaseCard } from "@/components/settings/ApiBaseCard";
import zhTW from "@/i18n/locales/zh-TW.json";
import { livenessUrl } from "@/lib/gatewayProbe";
import { mockFetch, renderRoute } from "./utils";

const AUTO: ApiBaseInfo = {
  effective: "http://192.168.50.240:4000/v1",
  source: "auto",
  mode: null,
  manual: null,
  deploy: null,
  auto: "http://192.168.50.240:4000/v1",
  warnings: [],
};

describe("ApiBaseCard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows auto value and switches to manual", async () => {
    let state: ApiBaseInfo = AUTO;
    const calls = mockFetch({
      "GET /settings/api-base": () => state,
      "PUT /settings/api-base": (_u, init) => {
        const b = JSON.parse(String(init?.body)) as { mode: string; value?: string };
        state = { ...AUTO, effective: b.value ?? AUTO.auto, source: "manual", mode: "manual", manual: b.value ?? null };
        return state;
      },
    });
    renderRoute(<ApiBaseCard />, "/settings", "/settings");

    expect(await screen.findByTestId("api-base-effective")).toHaveTextContent(AUTO.effective);
    expect(screen.getByTestId("api-base-source")).toHaveTextContent(zhTW.apiBase.source.auto);

    fireEvent.click(screen.getByLabelText(zhTW.apiBase.manualLabel));
    const input = await screen.findByTestId("api-base-input");
    fireEvent.change(input, { target: { value: "https://llm.hospital.lan/v1" } });
    fireEvent.click(screen.getByTestId("api-base-save"));

    await waitFor(() => expect(screen.getByTestId("api-base-effective")).toHaveTextContent("https://llm.hospital.lan/v1"));
    expect(screen.getByTestId("api-base-source")).toHaveTextContent(zhTW.apiBase.source.manual);
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ mode: "manual", value: "https://llm.hospital.lan/v1" });
  });

  it("shows localhost warning", async () => {
    mockFetch({
      "GET /settings/api-base": () => ({ ...AUTO, effective: "http://localhost:4000/v1", auto: "http://localhost:4000/v1", warnings: ["API_BASE_LOCALHOST"] }),
    });
    renderRoute(<ApiBaseCard />, "/settings", "/settings");
    expect(await screen.findByText(zhTW.apiBase.warnings.API_BASE_LOCALHOST)).toBeInTheDocument();
  });

  it("probes the gateway liveliness endpoint", () => {
    expect(livenessUrl("http://192.168.50.240:4000/v1")).toBe("http://192.168.50.240:4000/health/liveliness");
    expect(livenessUrl("https://llm.lan/v1")).toBe("https://llm.lan/health/liveliness");
  });
});
