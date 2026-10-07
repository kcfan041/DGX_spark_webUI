import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8088";
const OUT = process.env.OUT ?? ".";
const log = (...a) => console.log(...a);
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1400, height: 1000 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));

try {
  await page.goto(`${BASE}/dashboard`);
  await page.getByLabel("管理者 Token").fill("dev-admin-token");
  await page.getByRole("button", { name: "登入" }).click();
  await page.getByTestId("external-alert").waitFor({ timeout: 20000 });
  log("1 external alert:", (await page.getByTestId("external-alert").innerText()).replace(/\s+/g, " "));
  log("  gpu card hidden on dev:", (await page.getByTestId("gpu-card").count()) === 0);
  await page.getByRole("button", { name: "查看詳細" }).click();
  await page.getByTestId("external-item").first().waitFor();
  log("2 drawer:", (await page.getByTestId("external-item").first().innerText()).replace(/\s+/g, " ").slice(0, 200));
  await page.screenshot({ path: `${OUT}/ex-01-external.png`, fullPage: true });
  await page.keyboard.press("Escape");

  await page.goto(`${BASE}/models`);
  await page.getByTestId("model-name").first().click();
  await page.getByTestId("model-details").waitFor();
  log("3 model details:", (await page.getByTestId("model-details").innerText()).replace(/\s+/g, " ").slice(0, 220));
  await page.getByText("技術資訊").click();
  await page.getByText("config.json").first().waitFor();
  await page.screenshot({ path: `${OUT}/ex-02-model.png`, fullPage: true });
  await page.keyboard.press("Escape");

  await page.goto(`${BASE}/logs`);
  await page.getByTestId("log-source").click();
  await page.getByRole("option", { name: "Gateway（LiteLLM）" }).click();
  await page.getByText(/LiteLLM|Uvicorn|health/).first().waitFor({ timeout: 20000 });
  log("4 gateway logs streaming");
  await page.getByTestId("log-source").click();
  await page.getByRole("option", { name: "平台後端" }).click();
  await page.getByText(/GET \/api\/v1|uvicorn|started profile/i).first().waitFor({ timeout: 20000 });
  log("5 backend logs streaming");
  await page.screenshot({ path: `${OUT}/ex-03-logs.png`, fullPage: true });

  log("page errors:", errors.length ? errors : "none");
  log("EXTRAS E2E PASS");
} catch (e) {
  await page.screenshot({ path: `${OUT}/ex-fail.png`, fullPage: true });
  log("page errors:", errors);
  log("EXTRAS E2E FAIL:", e.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
