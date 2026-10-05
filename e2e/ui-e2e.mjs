import { chromium } from "playwright";

// Browser E2E for the main flow. Requires the dev stack (mock-vllm) running:
//   docker compose --env-file deploy/.env -f deploy/compose.yaml -f deploy/compose.dev.yaml up -d --build
//   cd e2e && npm install && npx playwright install chromium && TOKEN=<admin token> npm run ui
const BASE = process.env.BASE ?? "http://127.0.0.1:8088";
const TOKEN = process.env.TOKEN ?? "dev-admin-token";
const OUT = process.env.OUT ?? ".";
const log = (...a) => console.log(...a);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(String(e)));

try {
  // login
  await page.goto(`${BASE}/models`);
  await page.getByLabel("管理者 Token").fill(TOKEN);
  await page.getByRole("button", { name: "登入" }).click();
  await page.getByRole("heading", { name: "模型" }).waitFor();
  log("1 login -> models page");
  await page.screenshot({ path: `${OUT}/01-models.png`, fullPage: true });

  // models -> wizard
  await page.getByRole("link", { name: "建立模型服務" }).first().click();
  await page.getByText("這個模型主要用來做什麼？").waitFor();
  log("2 wizard opened at preset step (model preselected)");
  await page.getByTestId("preset-low_memory").click();
  await page.screenshot({ path: `${OUT}/02-presets.png`, fullPage: true });
  await page.getByRole("button", { name: "下一步" }).click();

  await page.getByText("最長對話長度").first().waitFor();
  const name = page.getByLabel("API 呼叫名稱");
  await name.fill("ui-e2e");
  log("3 settings step, served name =", await name.inputValue());
  await page.screenshot({ path: `${OUT}/03-settings.png`, fullPage: true });
  await page.getByRole("button", { name: "下一步" }).click();

  await page.getByText("預估記憶體").waitFor();
  const create = page.getByTestId("create-and-start");
  await create.waitFor();
  await page.waitForFunction(() => !document.querySelector('[data-testid="create-and-start"]')?.hasAttribute("disabled"));
  await page.screenshot({ path: `${OUT}/04-confirm.png`, fullPage: true });
  log("4 confirm step, create enabled");
  await create.click();

  // detail: loading
  await page.waitForURL(/\/services\/[0-9a-f]+$/);
  const id = page.url().split("/").pop();
  log("5 navigated to detail", id);
  await page.getByTestId("loading-progress").waitFor({ timeout: 15000 });
  await page.waitForTimeout(3000);
  const waited = await page.getByText(/已等待/).first().textContent();
  log("6 loading card visible:", waited);
  await page.screenshot({ path: `${OUT}/05-loading.png`, fullPage: true });

  // ready
  await page.getByText("外部系統可用「ui-e2e」呼叫").waitFor({ timeout: 60000 });
  log("7 READY + registered");
  await page.getByTestId("send-test").click();
  await page.getByText(/回應成功/).waitFor({ timeout: 30000 });
  log("8 test message:", (await page.getByText(/\[mock\]/).first().textContent())?.slice(0, 80));
  await page.screenshot({ path: `${OUT}/06-ready.png`, fullPage: true });

  // logs tab
  await page.getByRole("tab", { name: "Logs" }).click();
  await page.getByText(/Application startup complete/).waitFor({ timeout: 15000 });
  log("9 logs tab streaming");
  await page.screenshot({ path: `${OUT}/07-logs.png` });

  // events tab
  await page.getByRole("tab", { name: "事件" }).click();
  await page.getByText("已發布到 Gateway").first().waitFor();
  log("10 events timeline ok");

  // settings tab: induce OOM via mock trigger (max_model_len 1111)
  await page.getByRole("tab", { name: "設定" }).click();
  await page.getByText("變更需要重新啟動才會生效").waitFor();
  const ctx = page.getByRole("textbox", { name: "最長對話長度" });
  await ctx.fill("1111");
  await ctx.blur();
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: "儲存並重新啟動" }).click();
  log("11 saved with restart (mock OOM trigger)");

  // error card
  await page.getByTestId("error-card").waitFor({ timeout: 60000 });
  const title = await page.getByText("模型啟動失敗：可用記憶體不足").first().textContent();
  log("12 error card:", title);
  await page.screenshot({ path: `${OUT}/08-error.png`, fullPage: true });

  // apply suggestion -> settings prefilled with 8192 -> save & start
  const sugg = page.getByRole("button", { name: /降低最長對話長度至 .+ 並重試/ });
  log("12b suggestion label:", await sugg.textContent());
  await sugg.click();
  await page.getByText("最長對話長度").first().waitFor();
  const v = await page.getByRole("textbox", { name: "最長對話長度" }).inputValue();
  log("13 suggestion prefilled max_model_len =", v);
  await page.waitForTimeout(800);
  await page.getByRole("button", { name: "儲存並重試啟動" }).click();
  await page.getByText("外部系統可用「ui-e2e」呼叫").waitFor({ timeout: 60000 });
  log("14 restarted after fix -> READY");

  // services list + stop with confirm
  await page.goto(`${BASE}/services`);
  await page.getByRole("link", { name: /ui-e2e|fake-model/ }).first().waitFor();
  await page.screenshot({ path: `${OUT}/09-services.png`, fullPage: true });
  await page.getByRole("button", { name: "停止" }).first().click();
  await page.getByText(/外部系統將暫時無法呼叫/).waitFor();
  await page.getByRole("button", { name: "確認" }).click();
  await page.getByText("已停止").first().waitFor({ timeout: 30000 });
  log("15 stopped from list with confirm dialog");

  // dashboard
  await page.goto(`${BASE}/dashboard`);
  await page.getByText("記憶體").first().waitFor();
  await page.screenshot({ path: `${OUT}/10-dashboard.png`, fullPage: true });
  log("16 dashboard ok");

  // delete
  await page.goto(`${BASE}/services/${id}`);
  await page.getByRole("button", { name: "more" }).click();
  await page.getByRole("menuitem", { name: "刪除" }).click();
  await page.getByRole("button", { name: "確認" }).click();
  await page.waitForURL(`${BASE}/services`);
  log("17 deleted");

  log("console errors:", consoleErrors.length ? consoleErrors : "none");
  log("UI E2E PASS");
} catch (e) {
  await page.screenshot({ path: `${OUT}/fail.png`, fullPage: true });
  log("console errors:", consoleErrors);
  log("UI E2E FAIL:", e.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
