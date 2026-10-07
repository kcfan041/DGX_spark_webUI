import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const zh = JSON.parse(readFileSync("H:/git/DGX_spark/frontend/src/i18n/locales/zh-TW.json", "utf-8"));
const BASE = "http://127.0.0.1:8088";
const OUT = process.env.OUT ?? "shots";
const log = (...a) => console.log(...a);
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1400, height: 1000 } })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
const H = { Authorization: "Bearer sk-dev-master" };

// upstream mock model on LiteLLM (simulates a cloud provider's model)
const up = await (await fetch("http://127.0.0.1:4000/model/new", {
  method: "POST",
  headers: { ...H, "Content-Type": "application/json" },
  body: JSON.stringify({ model_name: "upstream-echo", litellm_params: { model: "openai/echo", api_key: "x", mock_response: "cloud says hi" }, model_info: {} }),
})).json();

let ok = true;
try {
  await page.goto(`${BASE}/dashboard`);
  await page.getByLabel(zh.login.tokenLabel ?? "管理者 Token").fill("dev-admin-token");
  await page.getByRole("button", { name: zh.login.submit ?? "登入", exact: true }).click();
  await page.getByRole("link", { name: zh.nav.cloud }).waitFor({ timeout: 20000 });
  log("1 nav has cloud + usage:", await page.getByRole("link", { name: zh.nav.usage }).isVisible());

  // ---- cloud provider
  await page.getByRole("link", { name: zh.nav.cloud }).click();
  await page.getByText(zh.cloud.provider.empty).waitFor();
  await page.getByTestId("add-provider").click();
  const dlg = page.getByRole("dialog");
  await dlg.getByText(zh.cloud.types.openai_compatible).click();
  await dlg.getByTestId("provider-name").fill("Self LiteLLM");
  await dlg.getByTestId("provider-base").fill("http://127.0.0.1:4000/v1");
  await dlg.getByTestId("provider-key").fill("sk-dev-master");
  await dlg.getByLabel(zh.cloud.provider.testModel).fill("upstream-echo");
  await dlg.getByTestId("provider-test").click();
  const res = dlg.getByTestId("provider-test-result");
  await res.waitFor({ timeout: 60000 });
  log("2 test result:", (await res.innerText()).replace(/\s+/g, " "));
  await page.screenshot({ path: `${OUT}/cl-01-provider.png`, fullPage: true });
  await dlg.getByTestId("provider-save").click();

  // add-model modal opens automatically
  await page.getByText(zh.cloud.model.addTitle).waitFor();
  const md = page.getByRole("dialog");
  await md.getByTestId("model-id").fill("upstream-echo");
  await md.getByTestId("model-name").fill("cloud-echo");
  await md.getByTestId("model-save").click();
  await page.getByTestId("cloud-model-cloud-echo").waitFor();
  const masked = await page.getByTestId("provider-row-Self LiteLLM").innerText();
  log("3 provider row:", masked.replace(/\s+/g, " "), "| no full key:", !masked.includes("sk-dev-master"));
  ok &&= !masked.includes("sk-dev-master");

  // ---- local service must exist for fallback: create via API quickly
  const api = (p, init = {}) =>
    fetch(`http://127.0.0.1:8080/api/v1${p}`, {
      ...init,
      headers: { Authorization: "Bearer dev-admin-token", "Content-Type": "application/json", ...(init.headers ?? {}) },
    }).then((r) => r.json());
  const models = await api("/models");
  const inst = await api("/instances", { method: "POST", body: JSON.stringify({ model_id: models[0].id, preset: "low_memory", served_model_name: "local-q", start: true }) });
  for (let i = 0; i < 60; i++) {
    const s = await api(`/instances/${inst.id}`);
    if (s.status === "READY" && s.gateway_state === "registered") break;
    await new Promise((r) => setTimeout(r, 2000));
  }
  await page.reload();
  await page.getByTestId("fallback-source").click();
  await page.getByRole("option", { name: "local-q" }).click();
  await page.getByTestId("fallback-targets").click();
  await page.getByRole("option", { name: /cloud-echo/ }).click();
  await page.keyboard.press("Escape");
  await page.getByTestId("fallback-add").click();
  await page.getByTestId("fallback-local-q").waitFor();
  log("4 fallback row:", (await page.getByTestId("fallback-local-q").innerText()).replace(/\s+/g, " "));

  await api(`/instances/${inst.id}/stop`, { method: "POST" });
  await new Promise((r) => setTimeout(r, 3000));
  await page.reload();
  const fb = page.getByTestId("fallback-local-q");
  await fb.getByText(/cloud-echo/).first().waitFor();
  const fbText = (await fb.innerText()).replace(/\s+/g, " ");
  log("5 stopped -> alias badge:", fbText);
  ok &&= fbText.toLowerCase().includes(zh.cloud.fallback.active.replace("{{target}}", "cloud-echo").toLowerCase());
  const aliasListed = (await page.getByTestId("cloud-model-local-q").count()) > 0;
  log("5b alias not listed as cloud model:", !aliasListed);
  ok &&= !aliasListed;
  await page.screenshot({ path: `${OUT}/cl-02-cloud-page.png`, fullPage: true });

  // ---- gateway: create key with limits, edit, rotate
  await page.getByRole("link", { name: zh.nav.gateway }).click();
  await page.getByTestId("create-key").click();
  const kd = page.getByRole("dialog");
  await kd.getByPlaceholder(zh.gateway.keys.namePlaceholder).fill("ui-key");
  await kd.getByTestId("limits-toggle").click();
  await kd.getByTestId("limit-rpm").fill("30");
  await kd.getByTestId("limit-budget").fill("10");
  await page.screenshot({ path: `${OUT}/cl-03-key-limits.png`, fullPage: true });
  await kd.getByRole("button", { name: zh.gateway.keys.create }).click();
  const newKey = (await page.getByTestId("new-key").innerText()).trim();
  await page.getByTestId("saved-confirm").click();
  await page.getByTestId("close-created").click();
  const row = page.getByTestId("key-row-active").filter({ hasText: "ui-key" });
  await row.waitFor();
  log("6 key row:", (await row.innerText()).replace(/\s+/g, " "));

  // call via stopped local-q -> cloud fallback, generating usage
  const c = await fetch("http://127.0.0.1:4000/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${newKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "local-q", messages: [{ role: "user", content: "hi" }] }),
  });
  const cj = await c.json();
  log("7 chat local-q while stopped:", c.status, cj.choices?.[0]?.message?.content);
  ok &&= c.status === 200;

  await page.getByTestId("key-menu-ui-key").click();
  await page.getByTestId("key-edit").click();
  const ed = page.getByRole("dialog");
  await ed.getByTestId("limit-rpm").fill("60");
  await ed.getByTestId("save-limits").click();
  await row.getByText("60 次/分").waitFor();
  log("8 edited rpm -> 60");

  await page.getByTestId("key-menu-ui-key").click();
  await page.getByTestId("key-rotate").click();
  await page.getByRole("dialog").getByRole("button", { name: zh.gateway.keys.rotate }).click();
  await page.getByText(zh.gateway.keys.rotatedTitle).waitFor();
  const rotatedKey = (await page.getByTestId("new-key").innerText()).trim();
  log("9 rotated, different key:", rotatedKey !== newKey);
  await page.getByTestId("saved-confirm").click();
  await page.getByTestId("close-created").click();
  await page.screenshot({ path: `${OUT}/cl-04-keys.png`, fullPage: true });

  // ---- service detail: local price
  await page.goto(`${BASE}/services/${inst.id}`);
  await page.getByTestId("price-toggle").click();
  await page.getByTestId("price-in").fill("0.5");
  await page.getByTestId("price-save").click();
  await page.getByText(zh.price.saved).waitFor();
  log("10 local price saved");

  // ---- usage page (wait for spend-log flush)
  await page.getByRole("link", { name: zh.nav.usage }).click();
  let found = false;
  for (let i = 0; i < 15 && !found; i++) {
    await page.waitForTimeout(6000);
    await page.reload();
    await page.getByTestId("usage-totals").waitFor();
    found = (await page.getByText("local-q").count()) > 0;
  }
  log("11 usage shows local-q:", found, "| totals:", (await page.getByTestId("usage-totals").innerText()).replace(/\s+/g, " "));
  ok &&= found;
  await page.getByTestId("usage-group").getByText(zh.usage.byKey).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/cl-05-usage.png`, fullPage: true });

  // ---- settings: change admin token then re-login
  await page.getByRole("link", { name: zh.nav.settings }).click();
  await page.getByTestId("token-current").fill("dev-admin-token");
  await page.getByTestId("token-new").fill("new-dev-token-123");
  await page.getByTestId("token-confirm").fill("new-dev-token-123");
  await page.screenshot({ path: `${OUT}/cl-06-token.png`, fullPage: true });
  await page.getByTestId("token-save").click();
  await page.getByTestId("token-relogin").click();
  await page.getByTestId("token-relogin").waitFor({ state: "detached" });
  await page.getByLabel(zh.login.tokenLabel ?? "管理者 Token").waitFor();
  await page.getByLabel(zh.login.tokenLabel ?? "管理者 Token").fill("dev-admin-token");
  await page.getByRole("button", { name: zh.login.submit ?? "登入", exact: true }).click();
  await page.waitForTimeout(1500);
  const oldRejected = page.url().includes("/login");
  await page.getByLabel(zh.login.tokenLabel ?? "管理者 Token").fill("new-dev-token-123");
  await page.getByRole("button", { name: zh.login.submit ?? "登入", exact: true }).click();
  await page.waitForURL(/dashboard|settings/, { timeout: 15000 });
  log("12 old token rejected:", oldRejected, "| new token works:", !page.url().includes("/login"));
  ok &&= oldRejected;

  // cleanup via API with new token
  const api2 = (p, init = {}) =>
    fetch(`http://127.0.0.1:8080/api/v1${p}`, { ...init, headers: { Authorization: "Bearer new-dev-token-123", "Content-Type": "application/json" } });
  await api2(`/instances/${inst.id}`, { method: "DELETE" });
  const provs = await (await api2("/cloud/providers")).json();
  for (const p of provs) await api2(`/cloud/providers/${p.id}`, { method: "DELETE" });
} catch (e) {
  ok = false;
  log("ERROR", e);
  await page.screenshot({ path: `${OUT}/cl-error.png`, fullPage: true });
} finally {
  await fetch("http://127.0.0.1:4000/model/delete", { method: "POST", headers: { ...H, "Content-Type": "application/json" }, body: JSON.stringify({ id: up.model_id }) });
  log("page errors:", errors);
  log(ok && errors.length === 0 ? "RESULT PASS" : "RESULT FAIL");
  await browser.close();
}
