// Browser E2E for "download model from Hugging Face" (needs internet; downloads a 6 MB test model).
// Requires an EMPTY model directory and the dev stack running.
import { chromium } from "playwright";

const BASE = process.env.BASE ?? "http://127.0.0.1:8088";
const OUT = process.env.OUT ?? ".";
const REPO = "hf-internal-testing/tiny-random-LlamaForCausalLM";
const log = (...a) => console.log(...a);

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1400, height: 1000 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));

try {
  await page.goto(`${BASE}/models`);
  await page.getByLabel("管理者 Token").fill(process.env.TOKEN ?? "dev-admin-token");
  await page.getByRole("button", { name: "登入" }).click();
  await page.getByText("模型目錄中還沒有模型").waitFor();
  log("1 empty models page with download hint");

  await page.getByTestId("open-download").click();
  await page.getByTestId("download-repo").fill(REPO);
  await page.getByTestId("download-check").click();
  await page.getByTestId("download-preview").waitFor({ timeout: 60000 });
  log("2 preview:", (await page.getByTestId("download-preview").innerText()).replace(/\s+/g, " ").slice(0, 160));
  await page.screenshot({ path: `${OUT}/dl-01-preview.png`, fullPage: true });
  await page.getByTestId("download-start").click();

  await page.getByTestId("downloads-panel").waitFor();
  await page.getByTestId("download-completed").waitFor({ timeout: 120000 });
  log("3 download completed");
  await page.getByText("tiny-random-LlamaForCausalLM").first().waitFor();
  await page.screenshot({ path: `${OUT}/dl-02-done.png`, fullPage: true });
  log("4 model listed:", await page.getByRole("row", { name: /tiny-random-LlamaForCausalLM/ }).innerText());

  // duplicate download is blocked
  await page.getByTestId("open-download").click();
  await page.getByTestId("download-repo").fill(REPO);
  await page.getByTestId("download-check").click();
  await page.getByText(/已經有「tiny-random-LlamaForCausalLM」/).waitFor();
  log("5 duplicate blocked:", await page.getByTestId("download-start").isDisabled());
  await page.keyboard.press("Escape");

  // invalid repo
  await page.getByTestId("open-download").click();
  await page.getByTestId("download-repo").fill("nobody-xyz/does-not-exist-123");
  await page.getByTestId("download-check").click();
  await page.getByText("在 Hugging Face 找不到這個模型").waitFor({ timeout: 60000 });
  log("6 missing repo explained");
  await page.keyboard.press("Escape");

  // gated repo
  await page.getByTestId("open-download").click();
  await page.getByTestId("download-repo").fill("meta-llama/Llama-3.1-8B-Instruct");
  await page.getByTestId("download-check").click();
  await page.getByText(/需要先在 Hugging Face 網站同意授權/).waitFor({ timeout: 60000 });
  log("7 gated repo explained");
  await page.keyboard.press("Escape");

  // create service from downloaded model (mock vllm)
  await page.getByRole("row", { name: /tiny-random/ }).getByRole("link", { name: "建立模型服務" }).click();
  await page.getByTestId("preset-balanced").waitFor();
  const fit = await page.getByTestId("preset-balanced").innerText();
  log("8 wizard preset card:", fit.replace(/\s+/g, " "));

  // delete model
  await page.goto(`${BASE}/models`);
  await page.getByRole("row", { name: /tiny-random/ }).getByRole("button", { name: "more" }).click();
  await page.getByRole("menuitem", { name: "刪除模型檔案" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "刪除" }).click();
  await page.getByText("模型目錄中還沒有模型").waitFor();
  log("9 model deleted from disk");

  log("page errors:", errors.length ? errors : "none");
  log("DOWNLOAD E2E PASS");
} catch (e) {
  await page.screenshot({ path: `${OUT}/dl-fail.png`, fullPage: true });
  log("page errors:", errors);
  log("DOWNLOAD E2E FAIL:", e.message);
  process.exitCode = 1;
} finally {
  await browser.close();
}
