import { execSync } from "node:child_process";
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:8088";
const OUT = process.env.OUT ?? ".";
const TOKEN = process.env.TOKEN ?? "dev-admin-token";
const log = (...a) => console.log(...a);
const hdr = { Authorization: `Bearer ${TOKEN}` };
const backendLog = (since) => execSync(`docker logs --since ${since} dgxsp-backend-1 2>&1`).toString();
const poll = async (n) => {
  for (let i = 0; i < n; i++) await fetch(`${BASE}/api/v1/system/summary`, { headers: hdr });
};

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1400, height: 1100 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));

try {
  await page.goto(`${BASE}/settings`);
  await page.getByLabel("管理者 Token").fill(TOKEN);
  await page.getByRole("button", { name: "登入" }).click();
  await page.getByTestId("advanced-card").waitFor();
  log("1 advanced card visible");

  // verbose: off by default -> polling not logged
  await new Promise((r) => setTimeout(r, 2000));
  await poll(3);
  await new Promise((r) => setTimeout(r, 1500));
  const quiet = (backendLog("4s").match(/GET \/api\/v1\/system\/summary/g) || []).length;
  log("2 verbose off, summary lines in log:", quiet);

  await page.getByTestId("verbose-switch").check({ force: true }).catch(() => {}); await page.getByTestId("verbose-switch").dispatchEvent("click");
  await page.getByText("已開啟完整記錄").waitFor();
  await new Promise((r) => setTimeout(r, 500));
  await poll(3);
  await new Promise((r) => setTimeout(r, 1500));
  const loud = (backendLog("3s").match(/GET \/api\/v1\/system\/summary/g) || []).length;
  log("3 verbose on (no restart), summary lines in log:", loud);

  await page.getByTestId("verbose-switch").check({ force: true }).catch(() => {}); await page.getByTestId("verbose-switch").dispatchEvent("click");
  await page.getByText("已關閉完整記錄").waitFor();
  await new Promise((r) => setTimeout(r, 2500));
  await poll(3);
  await new Promise((r) => setTimeout(r, 1500));
  const quiet2 = (backendLog("3s").match(/GET \/api\/v1\/system\/summary/g) || []).length;
  log("4 verbose off again, summary lines:", quiet2);

  // timeout
  await page.getByTestId("timeout-input").fill("45");
  await page.getByTestId("timeout-save").click();
  await page.getByText("已儲存").first().waitFor();
  const info = await (await fetch(`${BASE}/api/v1/system/info`, { headers: hdr })).json();
  log("5 timeout saved -> system/info health_s:", info.timeouts.health_s, "slow_warning_s:", info.timeouts.slow_warning_s);
  await page.reload();
  await page.getByTestId("timeout-input").waitFor();
  log("  after reload input =", await page.getByTestId("timeout-input").inputValue());

  // endpoint: bad mirror then real
  await page.getByTestId("endpoint-input").fill("https://no-such-mirror.invalid");
  await page.getByTestId("endpoint-test").click();
  await page.getByTestId("endpoint-test-result").waitFor({ timeout: 30000 });
  log("6 bad mirror test:", await page.getByTestId("endpoint-test-result").innerText());
  await page.getByTestId("endpoint-save").click();
  await page.getByText("已儲存").first().waitFor();
  const pv = await fetch(`${BASE}/api/v1/downloads/preview`, {
    method: "POST",
    headers: { ...hdr, "Content-Type": "application/json" },
    body: JSON.stringify({ repo_id: "hf-internal-testing/tiny-random-LlamaForCausalLM" }),
  });
  log("7 download preview with bad mirror:", pv.status, (await pv.json()).detail?.code);

  await page.getByTestId("endpoint-input").fill("");
  await page.getByTestId("endpoint-test").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="endpoint-test-result"]')?.textContent?.includes("huggingface.co"));
  log("8 default test:", await page.getByTestId("endpoint-test-result").innerText());
  await page.getByRole("button", { name: "改回預設" }).first().waitFor();
  const resets = page.getByRole("button", { name: "改回預設" });
  while ((await resets.count()) > 0) {
    await resets.first().click();
    await new Promise((r) => setTimeout(r, 700));
  }
  const pv2 = await fetch(`${BASE}/api/v1/downloads/preview`, {
    method: "POST",
    headers: { ...hdr, "Content-Type": "application/json" },
    body: JSON.stringify({ repo_id: "hf-internal-testing/tiny-random-LlamaForCausalLM" }),
  });
  log("9 after reset all -> preview status:", pv2.status);
  const adv = await (await fetch(`${BASE}/api/v1/settings/advanced`, { headers: hdr })).json();
  log("  sources:", adv.verbose_access_log.source, adv.hf_endpoint.source, adv.health_timeout_min.source);
  await page.screenshot({ path: `${OUT}/adv-01.png`, fullPage: true });

  log("page errors:", errors.length ? errors : "none");
  const ok = quiet === 0 && loud >= 3 && quiet2 === 0 && info.timeouts.health_s === 2700 && pv.status >= 500 && pv2.status === 200;
  log(ok ? "ADVANCED E2E PASS" : "ADVANCED E2E FAIL (see numbers above)");
  if (!ok) process.exitCode = 1;
} catch (e) {
  await page.screenshot({ path: `${OUT}/adv-fail.png`, fullPage: true });
  log("page errors:", errors);
  log("ADVANCED E2E FAIL:", e.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
