import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8088";
const OUT = process.env.OUT ?? "shots";
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
await ctx.addInitScript(() => localStorage.setItem("dgxsp.lang", "en"));
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
const cjk = /[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]/;
const leftovers = {};

await page.goto(`${BASE}/dashboard`);
await page.getByLabel("Admin token").fill("dev-admin-token");
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.getByRole("link", { name: "Cloud Models" }).waitFor({ timeout: 20000 });

for (const p of ["dashboard", "models", "services", "services/new", "gateway", "cloud", "usage", "logs", "settings"]) {
  await page.goto(`${BASE}/${p}`);
  await page.waitForTimeout(2500);
  const text = await page.locator("body").innerText();
  const lines = text.split("\n").filter((l) => cjk.test(l) && !l.includes("繁體中文"));
  if (lines.length) leftovers[p] = lines.slice(0, 5);
  await page.screenshot({ path: `${OUT}/en-${p.replace("/", "-")}.png`, fullPage: true });
}
console.log("CJK leftovers:", JSON.stringify(leftovers, null, 1));
console.log("page errors:", errors);
await browser.close();
