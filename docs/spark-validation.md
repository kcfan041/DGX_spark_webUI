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

## 6. 結果紀錄

### 第 1 次：2026-10-05，`OVERALL: PASS`（16/16）

主機：DGX Spark `spark-9526`，Ubuntu 24.04.5，kernel 7.0.0-1019-nvidia，Docker 29.6.2，Compose 5.2.0，
NVIDIA driver 580.178.04 / CUDA 13.0，Container Toolkit 1.20.1，20 CPU，MemTotal 121.7 GB，Swap 16 GB，cgroup v2。

| 項目 | 結果 | 對 Backend 設計的決定 |
|---|---|---|
| vLLM image | `eugr/spark-vllm@sha256:311616bd5f4f18a72ed1d309161fa504a7e6e1752d916d25395aadbf5a92b6ef`（arm64，10.5 GB，pull 195 s） | spark profile 鎖定此 digest；升版走「改 digest → 重跑 smoke」 |
| vLLM 版本 | `0.30.1rc1.dev631+g0872ddf4b`，torch 2.13.0+cu130，capability 12.1 | 記錄於 系統資訊 |
| Image 設定 | entrypoint `/opt/nvidia/nvidia_entrypoint.sh`、無 Cmd、root、WORKDIR `/workspace/vllm` | Backend 一律明確指定 `vllm serve ...` 作為 command |
| GPU 掛載 | Docker **未登錄 nvidia runtime**（只有 runc），但 `device_requests=[DeviceRequest(count=-1, capabilities=[["gpu"]])]` 可用 | DockerRuntime adapter 採 device_requests，不依賴 `runtime=nvidia` |
| `--ipc=host` / `--privileged` | 皆**不需要**；`shm_size=16g` + `ulimit nofile=1048576` 即可 | 預設非特權模式；`ipc_host` 保留為 profile 選項 |
| bridge network | ✅ vLLM 不開主機 port，LiteLLM 以 `http://<container>:8000/v1` 連線 | 平台內部網路 + container 名稱定址 |
| 模型掛載 / 權限 | `/data/models` 1000:1000 755；container 內 root 唯讀讀取 OK | `MODEL_ROOT=/data/models`，ro 掛載 |
| 載入時間（0.5B） | 123 s（含 CUDA graph / compile） | 健康檢查逾時預設 900 s；UI「已等待」計時有必要 |
| 健康判斷 | `/health` 200 後 `/v1/models` 立即列出 served name | READY = `/health` 200 且 `/v1/models` 含名稱 |
| LiteLLM 註冊 | `/model/new` 回 `model_id`；`/model/info` 保留自訂欄位 `dgxsp_instance_id`、`dgxsp_managed` | 以 `model_info.dgxsp_*` 做對帳 |
| 對話路徑 | virtual key → LiteLLM → vLLM：186 ms，回應正常 | 「送出測試訊息」採同一路徑 |
| Virtual key | `/key/generate` → `/key/delete` 後舊 key 回 401 | Gateway API Key 功能可行 |
| Log | tail 與 follow stream 皆可；vLLM 每個 HTTP 請求都會寫 access log | Log 頁需「只看錯誤 / 過濾」；預設過濾 `/health`、`/v1/models` 輪詢雜訊 |
| Stop | 0.9 s，exit code 0 | stop timeout 30 s 足夠 |
| 刻意失敗（`gpu_memory_utilization=0.01`） | 81.5 s 後 exit 1，`OOMKilled=false`；尾段只看到 `RuntimeError: Engine core initialization failed. See root cause above.` | 錯誤分類**不能只看最後幾行**，需掃描完整 log 找 root cause（已改 smoke 收集更多 log） |

### 記憶體觀察（需要後續校正，**不是結論**）

| 來源 | 數值 |
|---|---|
| `nvidia-smi` Memory-Usage | `Not Supported`（GB10 unified memory），只有每個 process 的用量 |
| `/proc/meminfo`（preflight） | MemTotal 121.7 GB，MemFree 76.8 GB，MemAvailable 118.3 GB，Cached 40.6 GB |
| `torch.cuda.mem_get_info()`（GPU probe，pull 完 10 GB image 後） | free **50.2 GB** / total 121.7 GB |

- `mem_get_info` 的 free 明顯小於 MemAvailable，推測接近 MemFree（**不含可回收的 page cache**）。
  剛 pull 完 10 GB image、讀完模型檔，page cache 變大，CUDA 視角的可用記憶體就變小。
- 影響：vLLM 依 `gpu_memory_utilization × total` 配置；若 page cache 佔用大，可能出現「系統看起來很空卻啟動失敗」。
- 第一版處理：
  - 資源監控以 `/proc/meminfo` 為主（顯示 已用 / 可用 / 快取），per-process 用量取 `nvidia-smi --query-compute-apps`。
  - Step 4 預估同時顯示「系統可用（含快取）」與「立即可用（MemFree）」，差距大時給 info 提示。
  - 是否需要在啟動前 drop cache（需 root）**不在第一版做**，待更多實測。
- 待校正：多 instance 同時存在時 `gpu_memory_utilization` 的實際語意、大模型實際峰值。

### 待補測（P1 之後再做）

- [ ] 7B–8B 模型載入時間與記憶體峰值
- [ ] 兩個 instance 同時運行
- [ ] 真正的記憶體不足（OOM）樣本與 `OOMKilled` 行為
- [ ] 量化模型（FP8 / NVFP4 / AWQ）
- [ ] Spark 重開機後平台自動復原（autostart）
