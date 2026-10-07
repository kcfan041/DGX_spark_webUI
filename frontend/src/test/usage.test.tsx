import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import zhTW from "@/i18n/locales/zh-TW.json";
import { rangeDates, fmtUsd } from "@/lib/usage";
import { UsagePage } from "@/pages/UsagePage";
import { mockFetch, renderRoute } from "./utils";

const m = (requests: number, pt: number, ct: number, spend = 0, failed = 0) => ({
  requests,
  successful: requests - failed,
  failed,
  prompt_tokens: pt,
  completion_tokens: ct,
  total_tokens: pt + ct,
  spend,
});

describe("usage helpers", () => {
  it("computes local date ranges", () => {
    const now = new Date(2026, 9, 7, 1, 0, 0);
    expect(rangeDates("today", now)).toEqual({ start: "2026-10-07", end: "2026-10-07" });
    expect(rangeDates("7d", now)).toEqual({ start: "2026-10-01", end: "2026-10-07" });
    expect(rangeDates("30d", now).start).toBe("2026-09-08");
  });
  it("formats money", () => {
    expect(fmtUsd(0)).toBe("$0");
    expect(fmtUsd(0.00025)).toBe("$0.0003");
    expect(fmtUsd(12.345)).toBe("$12.35");
  });
});

describe("UsagePage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows totals, breakdowns by model and key, and recent requests", async () => {
    const calls = mockFetch({
      "GET /usage/summary": () => ({
        start: "2026-10-01",
        end: "2026-10-07",
        totals: m(12, 1200, 3400, 0.5, 1),
        days: [
          { date: "2026-10-06", metrics: m(2, 100, 200) },
          { date: "2026-10-07", metrics: m(10, 1100, 3200, 0.5, 1) },
        ],
        by_model: [
          { id: "qwen", label: "qwen", kind: "model", metrics: m(10, 1000, 3000) },
          { id: "gpt-4o-mini", label: "gpt-4o-mini", kind: "model", metrics: m(2, 200, 400, 0.5, 1) },
        ],
        by_key: [
          { id: "t1", label: "OpenCode", kind: "key", metrics: m(11, 1100, 3300, 0.5) },
          { id: "litellm_proxy_master_key", label: "", kind: "admin", metrics: m(1, 100, 100) },
        ],
      }),
      "GET /usage/logs": () => ({
        items: [
          {
            request_id: "r1",
            time: "2026-10-07T01:00:00Z",
            model: "qwen",
            key_name: "OpenCode",
            status: "success",
            prompt_tokens: 12,
            completion_tokens: 34,
            spend: 0,
            duration_ms: 1500,
          },
        ],
        page: 1,
        total_pages: 1,
        total: 1,
        capped: false,
      }),
    });
    renderRoute(<UsagePage />, "/usage", "/usage");
    const totals = await screen.findByTestId("usage-totals");
    expect(totals).toHaveTextContent("12");
    expect(totals).toHaveTextContent("1,200");
    expect(totals).toHaveTextContent("3,400");
    expect(totals).toHaveTextContent("$0.50");
    expect(screen.getAllByText("gpt-4o-mini").length).toBeGreaterThan(0);

    fireEvent.click(within(screen.getByTestId("usage-group")).getByText(zhTW.usage.byKey));
    expect(await screen.findByText(zhTW.usage.admin)).toBeInTheDocument();
    expect(screen.getAllByText("OpenCode").length).toBeGreaterThan(1);

    const logs = await screen.findByTestId("usage-logs");
    expect(logs).toHaveTextContent("1.5s");
    const summaryCall = calls.find((c) => c.url.includes("/usage/summary"))!;
    expect(summaryCall.url).toMatch(/tz=-?\d+/);

    fireEvent.click(within(screen.getByTestId("usage-range")).getByText(zhTW.usage.range.today));
    await waitFor(() => {
      const last = calls.filter((c) => c.url.includes("/usage/summary")).pop()!;
      const u = new URL(last.url, "http://x");
      expect(u.searchParams.get("start")).toBe(u.searchParams.get("end"));
    });
  });
});
