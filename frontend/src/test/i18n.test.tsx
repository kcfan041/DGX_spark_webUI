import { screen } from "@testing-library/react";
import i18n from "@/i18n";
import en from "@/i18n/locales/en.json";
import zhTW from "@/i18n/locales/zh-TW.json";
import { UsagePage } from "@/pages/UsagePage";
import { mockFetch, renderRoute } from "./utils";

type Tree = { [k: string]: string | Tree };

function flatten(o: Tree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(o)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}

const vars = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();

describe("locales", () => {
  const zh = flatten(zhTW as Tree);
  const e = flatten(en as Tree);

  it("en has exactly the same keys as zh-TW", () => {
    expect(Object.keys(e).filter((k) => !(k in zh))).toEqual([]);
    expect(Object.keys(zh).filter((k) => !(k in e))).toEqual([]);
  });

  it("placeholders match", () => {
    const bad = Object.keys(zh).filter((k) => k in e && vars(zh[k]!).join() !== vars(e[k]!).join());
    expect(bad).toEqual([]);
  });

  it("en contains no CJK text", () => {
    const bad = Object.entries(e).filter(([, v]) => /[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]/.test(v));
    expect(bad).toEqual([]);
  });
});

describe("English UI", () => {
  afterEach(async () => {
    vi.unstubAllGlobals();
    await i18n.changeLanguage("zh-TW");
  });

  it("renders a page in English", async () => {
    await i18n.changeLanguage("en");
    const m = { requests: 1, successful: 1, failed: 0, prompt_tokens: 1, completion_tokens: 1, total_tokens: 2, spend: 0 };
    mockFetch({
      "GET /usage/summary": () => ({ start: "2026-10-07", end: "2026-10-07", totals: m, days: [], by_model: [], by_key: [] }),
      "GET /usage/logs": () => ({ items: [], page: 1, total_pages: 0, total: 0, capped: false }),
    });
    renderRoute(<UsagePage />, "/usage", "/usage");
    expect(await screen.findByText(en.usage.title)).toBeInTheDocument();
    expect(screen.getByText(en.usage.range["7d"])).toBeInTheDocument();
    expect(screen.queryByText(zhTW.usage.title)).not.toBeInTheDocument();
  });
});
