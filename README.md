# DGX Spark LLM Control Platform

DGX Spark 專用、初學者友善的 LLM Control Plane / Web Console。
以 Docker + vLLM 為推論層、LiteLLM 為統一 API Gateway，自製 Backend + Web UI 負責整合與管理。

## 文件

- [架構規劃](docs/architecture.md)
- [UI/UX 規格](docs/ui-spec.md)
- [DGX Spark 實機驗證（smoke test）](docs/spark-validation.md)

## 目錄

```
backend/       FastAPI + Docker SDK（管理 API、orchestration）
frontend/      React + TypeScript + Mantine（Web Console）
configs/       RuntimeProfile（spark / dev）等設定
deploy/        docker compose（web、backend、litellm、postgres）
mock-vllm/     假的 vLLM，供無 GPU 環境開發測試
smoke/         Spark smoke test
scripts/       preflight、模型下載、.env 產生
docs/          架構、UI 規格、實機驗證
```

## 部署（DGX Spark）

```bash
git pull
scripts/init-env.sh spark          # 產生 deploy/.env（含隨機密碼），並印出登入用的管理者 Token
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
```

- Web Console：`http://<spark-ip>:8088`（用管理者 Token 登入）
- 對外 API（LiteLLM）：`http://<spark-ip>:4000/v1`
- 停止：`docker compose --env-file deploy/.env -f deploy/compose.yaml down`（加 `-v` 會刪除資料）

## 本機開發（無 GPU）

```bash
# Backend
cd backend && uv sync && uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app

# Frontend（dev server 會把 /api 代理到 127.0.0.1:8080）
cd frontend && npm install && npm run dev
npm run typecheck && npm run lint && npm test && npm run build

# 整套（dev profile，使用 mock-vllm）
scripts/init-env.sh dev
docker compose --env-file deploy/.env -f deploy/compose.yaml -f deploy/compose.dev.yaml up -d --build
```

## 狀態

- [x] 規劃與 UI 規格
- [x] P0a：smoke 工具
- [x] Spark smoke test（2026-10-05，16/16 PASS）
- [x] P0b：Backend / Frontend 骨架、compose、CI
- [x] P1：模型服務生命週期（Backend）：建立 / 啟動 / 停止 / 重啟 / 取消 / 刪除、健康檢查、LiteLLM 自動註冊、錯誤分類、對帳、開機自動啟動
- [x] P1 Spark 實機驗證（2026-10-05，`P1 CHECK PASS`）
- [ ] P2：Frontend 主流程（Wizard、詳細頁、Logs）

## mock-vllm 失敗模擬（dev profile）

| `max_model_len` | 行為 |
|---|---|
| `1111` | 模擬記憶體不足（vLLM `No available memory for the cache blocks`）→ `OOM` |
| `2222` | 模擬 vLLM 啟動失敗（只有 `Engine core initialization failed`）→ `CRASHED` |
| 其他 | 約 8 秒後就緒 |
