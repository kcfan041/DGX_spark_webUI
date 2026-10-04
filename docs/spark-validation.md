# DGX Spark 實機驗證

目的：在寫大量 Backend 前，用最小測試確認 Spark 特有的假設。
工具：`scripts/spark-preflight.sh`、`smoke/run-smoke.sh`（內部執行 `smoke/spark_smoke.py`）。

## 1. 執行方式

```bash
git clone https://github.com/kcfan041/DGX_spark_webUI.git
cd DGX_spark_webUI

# 模型目錄（依實際磁碟配置調整）
sudo mkdir -p /data/models && sudo chown "$(id -un)": /data/models

# 下載測試模型（約 1 GB，下載成一般目錄，不是 HF cache 格式）
MODEL_ROOT=/data/models scripts/download-model.sh Qwen/Qwen2.5-0.5B-Instruct

# 產生 smoke/.env（隨機產生 LiteLLM master key / salt / DB 密碼）
./smoke/run-smoke.sh --init
#   檢查 smoke/.env 的 MODEL_ROOT、SMOKE_MODEL_DIR

# 執行
./smoke/run-smoke.sh
```

結果輸出在 `smoke/results/`（已 gitignore）：

| 檔案 | 內容 |
|---|---|
| `preflight-*.json` | 主機檢查、`nvidia-smi` 原文、`/proc/meminfo` 原文 |
| `smoke-spark-*.json` | 每個步驟 PASS/FAIL、耗時、收集到的資料 |
| `litellm-*.log` | LiteLLM log 尾段 |

請把 `preflight-*.json` 與 `smoke-spark-*.json` 回傳（不含任何 secret）。

清除：`./smoke/run-smoke.sh --down`

## 2. 測試架構（與正式架構相同的路徑）

```
smoke-runner (Docker SDK, 掛 docker.sock)
   │ 建立/停止/移除
   ▼
dgxsp-smoke-vllm ──(network: dgxsp-smoke, bridge)── dgxsp-smoke-litellm ── dgxsp-smoke-db (Postgres)
   ▲ /models (MODEL_ROOT, ro)                         ▲ /model/new, /key/generate, /v1/chat/completions
```

- vLLM 用 **bridge network**（不是 spark-vllm-docker 預設的 host network），LiteLLM 以 container 名稱連線。
- 不經過 `launch-cluster.sh`；直接 `vllm serve`，GPU 用 Docker SDK `device_requests`（等同 `--gpus all`）。
- 模型從 `MODEL_ROOT` 本機目錄以唯讀掛載，`HF_HUB_OFFLINE=1`。
- 對話測試使用 **virtual key**，不使用 master key。

## 3. 步驟與要確認的假設

| 步驟 | 驗證內容 | 失敗代表 |
|---|---|---|
| 01_docker_info | Docker 版本、架構、runtimes、cgroup | — |
| 02_model_dir | 模型 config.json、大小、檔案擁有者 UID | 模型路徑或下載問題 |
| 03_image | pull `eugr/spark-vllm`、記錄 digest、entrypoint、user | image 不可用 / 非 arm64 |
| 04_mount_probe | container 內能讀 `/models` | UID/權限問題 |
| 05_gpu_probe | container 內 `nvidia-smi`、`torch.cuda`、`mem_get_info`、vLLM 版本 | **Docker SDK GPU 掛載方式錯誤** |
| 06_gateway_ready | LiteLLM `/health/readiness` 且 db connected | LiteLLM arm64 / Postgres 問題 |
| 07_vllm_start | Docker SDK 建立 vLLM container（bridge、shm、ulimit） | 參數不相容 |
| 08_vllm_health | `/health` 200、`/v1/models` 含 served name；記錄載入時間軸 | 模型載入失敗、逾時 |
| 09_litellm_register | `/model/new` 註冊、`/model/info` 查回、自訂 `model_info` 欄位保留 | DB 模式動態註冊不可行 |
| 10_virtual_key | `/key/generate` | virtual key 不可用 |
| 11_chat_via_litellm | virtual key → LiteLLM → vLLM 完整對話 | bridge 網路 / routing 問題 |
| 12_logs | 讀 log tail 與即時 stream | log 讀取方式 |
| 13_key_revoke | `/key/delete` 後該 key 被拒絕 | 撤銷行為 |
| 14_litellm_unregister | `/model/delete` 後確實消失 | 移除行為 |
| 15_vllm_stop_remove | stop 耗時、exit code、無殘留 container | lifecycle 問題 |
| 16_error_probe（非必要） | 用極小 `gpu_memory_utilization` 故意啟動失敗，記錄 exit code / OOMKilled / log | 作為錯誤分類規則樣本 |

## 4. 失敗時的調整開關（`smoke/.env`）

| 情況 | 調整 |
|---|---|
| NCCL / shm / IPC 相關錯誤 | `SMOKE_IPC_HOST=1`（改用 `--ipc=host`，與 launch-cluster 預設相同） |
| 載入逾時 | `SMOKE_HEALTH_TIMEOUT=1800` |
| 需要額外 vLLM 參數 | `SMOKE_VLLM_EXTRA_ARGS=--enforce-eager` 等 |
| 想換 image / 鎖版本 | `SMOKE_VLLM_IMAGE=eugr/spark-vllm@sha256:...` |
| 想保留 gateway 手動檢查 | `SMOKE_KEEP_GATEWAY=1`，LiteLLM UI 在 `http://127.0.0.1:4000/ui` |

## 5. 已在本機（x86, 無 GPU）確認的事項

| 項目 | 結果 |
|---|---|
| LiteLLM `main-stable` 提供 linux/arm64 image | ✅ manifest 含 arm64 |
| `eugr/spark-vllm:latest` | 僅 arm64；entrypoint `/opt/nvidia/nvidia_entrypoint.sh`，無 Cmd、以 root 執行、WORKDIR `/workspace/vllm` → **必須明確指定 command** |
| LiteLLM + Postgres（`STORE_MODEL_IN_DB`）readiness | ✅ `{"status":"healthy","db":"connected"}` |
| `/model/new` → `/model/info` 自訂 `model_info` 欄位保留 | ✅（`dgxsp_instance_id` 可用於對帳） |
| `/model/new` 回應欄位 | `model_id, model_name, litellm_params, model_info, created_at, ...` |
| `/key/generate` → `/key/delete` → 舊 key 回 401 | ✅ |
| `/model/delete` 後 `/model/info` 不再出現 | ✅ |

## 6. 結果紀錄（Spark 實測後填寫）

| 項目 | 結果 | 對 Backend 設計的決定 |
|---|---|---|
| vLLM image digest | | profile 鎖定 |
| vLLM 版本 | | |
| GPU 掛載寫法（device_requests） | | |
| 是否需要 `--ipc=host` | | |
| bridge network 可用 | | |
| `torch.cuda.mem_get_info` 數值 | | 資源監控資料來源 |
| `nvidia-smi` 記憶體欄位是否有值 | | 資源監控資料來源 |
| 0.5B 模型載入時間 | | 健康檢查逾時預設 |
| 模型目錄 UID / 權限 | | MODEL_ROOT 規範 |
| 啟動失敗樣本（exit code / log） | | `error-patterns.yaml` |
| stop 耗時 | | stop timeout 預設 |
