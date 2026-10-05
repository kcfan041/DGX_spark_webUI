# DGX Spark LLM Control Platform — Web Console UI/UX 規格

版本：v0.1（MVP）
狀態：已確認，作為 P5 前端與 Backend API 的共同依據
技術：React + TypeScript + Mantine，i18n 架構（第一版完成繁體中文）

---

## 0. 設計原則

1. **初學者優先，進階可展開**：預設畫面只回答「現在怎樣」與「下一步做什麼」，技術細節放在「進階設定」或「診斷」。
2. **不把 vLLM CLI 一比一搬成表單**：參數經過 Preset、預設值、說明與防呆後才呈現。
3. **唯一的主要流程**：
   `Models → 選模型 → 選 Preset → 設定 → 建立並啟動 → 載入中 → API 就緒`
   其他功能（只儲存、進階設定、診斷）不可干擾這條流程。
4. **初學者不需要理解**：Docker container、Docker network、LiteLLM model id、vLLM CLI、container internal port。這些只出現在「進階設定」或「診斷」。
5. **狀態以後端為準**：前端不做樂觀更新，所有操作是非同步的，靠輪詢或 SSE 更新。
6. **誠實呈現估算**：記憶體預估一律標示「僅供參考」，不宣稱能精準判斷 OOM。
7. **文案不 hardcode**：UI 文字、狀態名稱、錯誤訊息、說明文字全部經由 i18n key。

---

## 1. 用語與 i18n

### 1.1 用語對照

UI 顯示左欄用語；文件、程式碼、API 內部使用右欄。

| UI 顯示 | 內部概念 |
|---|---|
| 模型服務 | instance（vLLM container） |
| API 呼叫名稱 | `served_model_name` / LiteLLM model alias |
| 記憶體使用比例 | `gpu_memory_utilization` |
| 最長對話長度 | `max_model_len` |
| 對外 API 位址 | LiteLLM base URL |
| 已發布到 Gateway | 已在 LiteLLM 註冊 |
| API Key | LiteLLM virtual key |
| 用途 / 預設組合 | preset |

- 「模型服務（Instance）」僅在首次說明處（例如空狀態說明、Wizard 標題提示）出現一次，其餘一律顯示「模型服務」。
- **LiteLLM master key 不在 UI 中以「API Key」名義出現**，它是平台管理憑證，只存在於部署設定。

### 1.2 i18n 規範

- 函式庫：`react-i18next`；語系檔 `frontend/src/locales/{zh-TW,en}/*.json`，依 namespace 拆分：
  `common`, `nav`, `dashboard`, `models`, `instances`, `wizard`, `params`, `presets`, `status`, `errors`, `gateway`, `logs`, `settings`
- 第一版：`zh-TW` 完整；`en` 可缺，缺漏時 fallback 到 `zh-TW`，並在開發模式顯示缺 key 警告。
- Backend **只回傳代碼與參數**（狀態碼、錯誤碼、help_key、preset label_key），不回傳顯示文字。
  - 例外：log 原文、模型名稱等使用者資料原樣顯示。
- 數字、大小、時間用 `Intl` 格式化（GB、相對時間「3 秒前」、持續時間「2 分 13 秒」）。
- Key 命名：`<namespace>.<區塊>.<項目>`，例如 `errors.OOM.title`、`errors.OOM.description`、`params.max_model_len.help`。

---

## 2. Information Architecture

```
/login                      管理者 Token 登入
/dashboard                  系統總覽（預設首頁）
/models                     模型
  └─ 模型詳細（右側 Drawer）
/services                   模型服務清單
  ├─ /services/new          建立模型服務（Wizard；?model=<id> 時跳過 Step 1）
  └─ /services/:id          模型服務詳細（主要操作中心）
       ├─ 概覽
       ├─ 設定
       ├─ Logs
       ├─ 事件
       └─ 診斷（進階）
/gateway                    Gateway：連線資訊、API Key、已發布模型
/logs                       全域 Log
/settings                   一般 / 存取 / 模型來源 / 執行環境 / 關於
```

> 前端路由使用 `/services`（貼近 UI 用語）；Backend API 仍使用 `/instances`。

### 2.1 Sidebar

| 順序 | 顯示 | 路由 |
|---|---|---|
| 1 | 總覽 | `/dashboard` |
| 2 | 模型 | `/models` |
| 3 | 模型服務 | `/services` |
| 4 | Gateway | `/gateway` |
| 5 | Logs | `/logs` |
| 6 | 設定 | `/settings` |

### 2.2 全域元素

- **頂部列**：平台名稱、系統狀態燈（正常 / 注意 / 異常，點擊前往總覽）、登出。
- **Toast 通知**：狀態變化時提示，例如「Qwen 7B 聊天 已就緒」「Llama 8B 啟動失敗：可用記憶體不足」。
- **「顯示技術細節」開關**（設定 → 一般，預設關閉，存於 localStorage）：開啟後各頁的診斷區塊直接展開。

---

## 3. 各頁 Wireframe

### 3.1 總覽 Dashboard

```
┌ Sidebar ┬──────────────────────────────────────────────────────────────┐
│ 總覽     │ ● 系統運作正常                               最後更新 3 秒前   │
│ 模型     │ ┌───────────┐┌───────────┐┌───────────┐┌───────────┐         │
│ 模型服務 │ │ DGX Spark ││ 記憶體     ││ 磁碟       ││ Gateway   │         │
│ Gateway │ │ ● 正常     ││ ███████░  ││ ████░░░░  ││ ● 正常     │         │
│ Logs    │ │ GPU 42%   ││ 78/128 GB ││ 1.2/4 TB  ││ 3 個模型   │         │
│ 設定     │ │           ││ GPU與系統共用││ 模型目錄   ││ 已發布     │         │
│         │ └───────────┘└───────────┘└───────────┘└───────────┘         │
│         │  ● 就緒 2     ◐ 載入中 1     ✕ 錯誤 1     ○ 已停止 3            │
│         │ ┌ 運行中的模型服務 ──────────────────────────────────────────┐ │
│         │ │ 名稱           狀態           API 呼叫名稱   記憶體   操作     │ │
│         │ │ Qwen 7B 聊天   ● 就緒          qwen-7b      30%    [查看]    │ │
│         │ │ Llama 8B       ◐ 載入中 2:13   llama-8b     40%    [查看]    │ │
│         │ │ Mistral 測試   ✕ 記憶體不足    mistral       —     [處理]    │ │
│         │ └──────────────────────────────────────────────────────────┘ │
│         │ ┌ 如何連線 ─────────────────────────────────────────────────┐ │
│         │ │ 對外 API 位址  http://spark.local:4000/v1   [複製]          │ │
│         │ │ 需要 API Key？前往 Gateway 建立 →          [查看使用範例]    │ │
│         │ └──────────────────────────────────────────────────────────┘ │
└─────────┴──────────────────────────────────────────────────────────────┘
```

規則：
- 第一行固定為一句話健康摘要：`正常` / `有 N 個模型服務需要處理` / `Gateway 無法連線` / `執行環境異常`。
- 後端拿不到的指標（由 `capabilities` 決定）**整張卡片隱藏**，不顯示 0 或假數字。
- 記憶體卡片標註「GPU 與系統共用」（Spark unified memory）。
- 空狀態：「還沒有運行中的模型服務」＋ [前往選擇模型]。
- 不顯示 container、image、內部 URL 等技術資訊。
- 記憶體卡片：以 `/proc/meminfo` 為準，顯示「已使用 / 總量」，副標「其中可回收快取 X GB」（`nvidia-smi` 在 GB10 不提供總量）。
- 開機自動啟動進行中時，在健康摘要下方顯示：「正在依序啟動 2 個自動啟動的模型服務（1/2）」。
- 偵測到外部服務時顯示提示卡（見 9.2）。

### 3.2 模型 Models

```
│ 模型                                     [搜尋_____] 來源:[全部▾] [▦][☰] │
│ ┌──────────────────────────────────────────────────────────────────┐ │
│ │ 名稱                  大小   架構     量化   dtype  最長Context  使用狀態 │ │
│ │ Qwen2.5-7B-Instruct  15 GB  Qwen2    —     bf16   32K        ● 使用中(1)│ │
│ │                                       [建立模型服務]  [詳細]          │ │
│ │ Llama-3.1-8B-FP8      9 GB  Llama    FP8   auto   128K       未使用    │ │
│ │                                       [建立模型服務]  [詳細]          │ │
│ │ SomeModel-X           4 GB  未知 ⚠   —     —      未知        未使用    │ │
│ │  ⚠ 可能需要「信任遠端程式碼」          [建立模型服務]  [詳細]          │ │
│ └──────────────────────────────────────────────────────────────────┘ │
```

- 支援表格 / 卡片兩種檢視。
- 主要操作：**[建立模型服務]** → `/services/new?model=<id>`（跳過 Wizard Step 1）。
- 「使用中(n)」可點擊，列出使用此模型的模型服務。
- 無法解析的 metadata 顯示「未知」，不阻擋使用。
- 詳細 Drawer：
  - 基本資訊（名稱、大小、架構、量化、dtype、最長 Context）
  - 建議設定：各 Preset 套用在此模型後的值
  - ▸ 技術資訊（收起）：來源類型、實體路徑、`config.json` 摘要
- 空狀態：說明如何把模型放入模型目錄（顯示目前設定的 `MODEL_ROOT`）＋ [重新掃描]。
  - 預留：未來在此加入 [下載模型]（Hugging Face repo ID）。

### 3.3 模型服務清單

```
│ 模型服務                                           [+ 建立模型服務]   │
│ [全部 7] [就緒 2] [載入中 1] [錯誤 1] [已停止 3]                       │
│ 名稱           模型                  狀態          Gateway    操作        │
│ Qwen 7B 聊天   Qwen2.5-7B-Instruct   ● 就緒         ✓ 已發布   [停止][⋯]  │
│ Llama 8B       Llama-3.1-8B-FP8      ◐ 載入中 2:13  — 等待中   [停止][⋯]  │
│ Mistral 測試   Mistral-7B            ✕ 記憶體不足   — 未發布   [處理][⋯]  │
│ 大模型備用     Llama-3.1-70B-FP8     ○ 已停止       — 未發布   [啟動][⋯]  │
```

- 每列主要按鈕依狀態變化（見第 6 節操作矩陣）。
- `⋯`：重新啟動、編輯設定、查看 Log、刪除。
- 空狀態：「模型服務（Instance）是一個正在運作、可被呼叫的模型。」＋ [從模型建立]。

### 3.4 模型服務詳細頁（主要操作中心）

**頁首（所有分頁共用）**
```
│ ← 模型服務 / Qwen 7B 聊天                     ● 就緒   已運行 3h 12m   │
│                      [停止] [重新啟動] [編輯設定] [⋯ 刪除]              │
│ [概覽] [設定] [Logs] [事件] [診斷]                                     │
```

**概覽（就緒）**
```
│ ┌ 如何使用 ──────────────────────────────────────────────────────┐ │
│ │ API 位址     http://spark.local:4000/v1     [複製]                │ │
│ │ 模型名稱     qwen-7b                        [複製]                │ │
│ │ API Key      使用 Gateway 建立的 Key  [前往建立]                    │ │
│ │ 範例：[curl] [Python] [OpenCode]                       [複製範例]  │ │
│ │ [▶ 送出測試訊息]  「你好」→「你好！有什麼可以幫忙…」  0.8 秒 ✓          │ │
│ └────────────────────────────────────────────────────────────────┘ │
│ ┌ Gateway 發布 ──────────────┐ ┌ 資源 ─────────────────────────────┐ │
│ │ ✓ 已發布到 Gateway           │ │ 記憶體配額  30% ≈ 38 GB（估算）      │ │
│ │ 外部系統可用 qwen-7b 呼叫     │ │ （無法取得的項目自動隱藏）           │ │
│ └────────────────────────────┘ └──────────────────────────────────┘ │
│ ┌ 目前設定 ───────────────────────────────────── [編輯設定] ──────┐  │
│ │ 用途：均衡 · 最長對話長度 32K · 記憶體 30% · 量化 自動              │  │
│ └────────────────────────────────────────────────────────────────┘  │
```

**送出測試訊息**
- 路徑必須為 **Web UI → Backend → LiteLLM → vLLM → Model**，Backend 不得直接呼叫 vLLM。
- Backend 使用平台內部專用的 virtual key（見第 7.3 節）呼叫 LiteLLM `/v1/chat/completions`。
- 顯示：送出內容、回應前段文字、耗時、成功 / 失敗。
- 失敗時依錯誤碼顯示（例如 `GATEWAY_UNREACHABLE`、`GATEWAY_MODEL_NOT_FOUND`、`TEST_TIMEOUT`）。
- 僅在狀態「就緒且已發布」時可用。

**概覽（載入中）**
```
│ ◐ 正在載入模型…                                已等待 2 分 13 秒        │
│ ✓ 準備設定 → ✓ 建立服務 → ◐ 載入模型 → ○ 發布到 Gateway → ○ 就緒        │
│ 大模型第一次載入可能需要數分鐘，這是正常的。                               │
│ 最新訊息：Loading safetensors checkpoint shards: 60% …   [查看完整 Log] │
│                                                          [取消啟動]    │
```
- 「已等待」由 `phase_started_at`（本次啟動起點）計算，前端每秒更新。
- 「最新訊息」為最後一行 log（原文，不翻譯）。
- 超過預期時間（profile 設定的門檻）改為黃色提示：「比預期久，建議查看 Log」。
- 預留：日後依同模型歷史載入時間顯示「通常約需 X 分鐘」。

**概覽（錯誤）**
```
│ ✕ 模型啟動失敗：可用記憶體不足                                         │
│   此模型加上目前設定所需的記憶體，超過了可用量。                           │
│   建議：                                                             │
│   [降低最長對話長度至 8K 並重試] [改用「省記憶體」] [查看其他運行中的服務]   │
│   ▸ 相關 Log 片段（3 行）                              [查看原始 Log]   │
│   錯誤代碼 OOM · 發生於 14:02:31                                      │
```
- 標題與說明來自 `errors.<code>.*`，不直接顯示 raw log。
- 建議按鈕依 `suggestions[]` 產生；按下後開啟「編輯設定」並預填建議值，使用者確認後才重試。
- 原始 log 只以「相關片段（收起）」與「查看原始 Log」提供。

**設定分頁 / 編輯設定**
- 使用與 Wizard Step 3 相同的表單元件（含 Preset 選擇與進階設定）。
- 模型服務運行中時，頂部顯示：「⚠ 變更需要重新啟動才會生效，重新啟動期間外部呼叫會暫時中斷。」
- 按鈕：主要 [儲存並重新啟動]、次要 [只儲存]（下次啟動時生效）。
- 修改「API 呼叫名稱」時額外警告：「使用舊名稱的外部系統將無法呼叫」。

**Logs 分頁**：共用全域 Log 元件，來源固定為此模型服務。

**事件分頁**：時間軸，例如「14:00 建立」「14:01 開始啟動」「14:02 載入失敗：OOM」「14:05 重新啟動」「14:07 就緒」「14:07 已發布到 Gateway」。

**診斷分頁（進階）**
- container 名稱 / ID、image 與 digest、network、內部 URL
- LiteLLM model id、發布時間
- 實際 `vllm serve` 完整指令（可複製）
- 最後一次 exit code、OOMKilled
- 原始狀態 JSON（可複製）

### 3.5 Gateway

```
│ Gateway（對外 API 入口）                                  ● 正常        │
│ ┌ 連線資訊 ─────────────────────────────────────────────────────────┐ │
│ │ API 位址  http://spark.local:4000/v1   [複製]                       │ │
│ │ 可用模型名稱  qwen-7b [複製]  llama-8b [複製]                         │ │
│ │ [使用範例]                                                          │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ ┌ API Key ─────────────────────────────────────── [+ 建立 API Key] ──┐ │
│ │ 名稱            Key             建立時間           狀態     操作       │ │
│ │ OpenCode-Alice  sk-…a1b2        2026-10-04 10:12  ● 有效   [撤銷]     │ │
│ │ 院內系統A        sk-…9f3e        2026-10-01 09:00  ○ 已撤銷  —         │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ ┌ 已發布模型 ──────────────────────────────────────── [重新同步] ────┐ │
│ │ API 呼叫名稱   對應模型服務     服務狀態   同步狀態                     │ │
│ │ qwen-7b       Qwen 7B 聊天    ● 就緒    ✓ 一致                       │ │
│ │ old-model     （已不存在）      —        ⚠ 殘留，將自動清除  [立即清除]  │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ ▸ 進階：LiteLLM 版本、資料庫狀態                                          │
```

**API Key（LiteLLM Virtual Key）**
- **建立**：Modal 輸入名稱（必填）→ 建立成功後顯示：
  ```
  ✓ API Key 已建立
  sk-xxxxxxxxxxxxxxxxxxxxxxxx        [複製]
  ⚠ 這是唯一一次顯示完整 Key，關閉後將無法再查看，請立即複製保存。
  [複製 API 位址] [複製 Key] [複製連線範例]          [我已保存，關閉]
  ```
  - 關閉前必須點「我已保存」（避免誤關）。
  - 完整 key 不寫入 Backend 資料庫、不寫入 log、不存於前端 state 以外的地方。
- **清單**：名稱、遮罩後 key（前後幾碼）、建立時間、狀態（有效 / 已撤銷）。
- **撤銷**：確認對話框「撤銷後使用此 Key 的系統將立即無法呼叫，且無法復原。」
- 第一版不提供：quota、budget、team、模型存取限制、到期時間。
- **Master key 不顯示**於任何頁面。
- 平台內部用於「送出測試訊息」的 key 不出現在此清單（或以「系統」標籤唯讀顯示，不可撤銷）。

**複製**：API 位址、API Key（僅建立當下）、模型名稱，各自有複製按鈕；「使用範例」會把三者組合成 curl / Python / OpenCode 設定片段（key 以 `<YOUR_API_KEY>` 佔位）。

### 3.6 Logs

```
│ Logs  來源:[Qwen 7B 聊天 ▾]  [● 即時][⏸ 暫停]  [搜尋____] [☐ 只看錯誤] [下載] │
│ 14:02:10 INFO  Loading model weights...                                │
│ 14:02:31 ERROR torch.OutOfMemoryError: CUDA out of memory ...           │
│          └ 💡 這表示可用記憶體不足  [查看解法]                             │
```
- 來源：各模型服務、Gateway、平台 Backend。
- 即時模式使用 SSE；暫停時保留畫面、背景緩衝。
- 後端比對到已知錯誤樣式時，在該行附加 `annotation`（錯誤碼），前端顯示對應 i18n 說明。
- Log 原文不翻譯。

### 3.7 設定 Settings

| 區塊 | 第一版內容 |
|---|---|
| 一般 | 介面語言（繁中；英文未完成時標示「部分翻譯」）、顯示技術細節開關、主題（亮 / 暗） |
| 存取 | 目前登入狀態、登出；說明管理者 Token 於部署設定更換（唯讀） |
| 模型來源 | 來源清單（類型、路徑、模型數、最後掃描時間）、[重新掃描]；第一版唯讀，由設定檔決定 |
| 執行環境 | Profile（spark / dev）、vLLM image 與 digest、CPU 架構、Docker 狀態、GPU 狀態（唯讀） |
| 關於 | 平台版本、vLLM 版本、LiteLLM 版本 |

### 3.8 登入

- 單一欄位「管理者 Token」＋ [登入]。
- Token 存於 sessionStorage（關閉瀏覽器即失效），所有 API 帶 `Authorization: Bearer`。
- 401 時導回登入頁並保留原本路徑。
- Security layer 以介面抽象（`AuthProvider`），日後可替換為帳號 / SSO / RBAC。

---

## 4. 建立模型服務 Wizard

### 4.1 流程

```
Step 1 選模型 ─► Step 2 選用途 ─► Step 3 基本設定 ─► Step 4 確認
 （從模型頁進入                     （進階設定收起）       │
   時跳過此步）                                           ├─ 主要：[▶ 建立並啟動模型服務] ─► 詳細頁（載入中）
                                                         └─ 次要：只儲存設定 ─────────► 詳細頁（已停止）
```

- 頂部 Stepper 可點擊回到已完成的步驟；離開 Wizard 時若有未儲存內容需確認。
- 標題：「建立模型服務」，副標第一次出現時說明「模型服務（Instance）就是一個正在運作、可透過 API 呼叫的模型」。

### 4.2 Step 1：選模型

- 與模型頁相同的清單元件（單選模式），含搜尋。
- 選定後顯示摘要卡（名稱、大小、最長 Context、量化）。

### 4.3 Step 2：選用途（Preset）

```
┌ 均衡 ✓推薦 ─────────┐┌ 省記憶體 ────────────┐┌ 長文件 ──────────────┐
│ 一般聊天、問答         ││ 想同時跑多個模型        ││ 需要讀長文件或大量程式碼 │
│ 最長對話 32K          ││ 最長對話 8K            ││ 最長對話 128K          │
│ 記憶體 70%            ││ 記憶體 40%             ││ 記憶體 85%  ⚠ 較吃資源  │
│ [為什麼是這些值？]      ││                       ││                       │
└──────────────────────┘└───────────────────────┘└───────────────────────┘
┌ 高吞吐 ──────────────┐┌ 自訂 ─────────────────┐
│ 多人同時使用           ││ 自己調整所有基本設定      │
└──────────────────────┘└───────────────────────┘
```

- 卡片上的值由後端 `GET /presets?model_id=` 依 **RuntimeProfile + 模型 metadata** 計算，不寫死在前端。
- 「為什麼是這些值？」顯示後端回傳的 `explanations[]`（i18n key + 參數），例如「模型最多支援 32K，因此取 32K」。
- 預設選中標記為 `recommended` 的 Preset（均衡）。
- 第一版「高吞吐」與「均衡」差異有限（吞吐相關參數尚未開放），卡片說明需如實呈現，不誇大。

### 4.4 Step 3：基本設定

| 欄位 | 元件 | 預設 / 防呆 |
|---|---|---|
| 服務名稱 | TextInput | 自動帶「模型簡稱 + 用途」，僅供顯示 |
| API 呼叫名稱 | TextInput | 自動產生 slug；即時檢查格式與是否重複；說明「外部系統用這個名稱呼叫」 |
| 最長對話長度 | Slider + 刻度（4K / 8K / 32K / 模型上限）+ 數字輸入 | 超過模型上限 → 阻擋；模型上限未知 → 警告 |
| 記憶體使用比例 | Slider（%）＋ 約略 GB | 範圍由 profile 決定；與其他運行中服務加總超過門檻 → 警告 |
| 量化方式 | Select | 預設「自動（偵測到：FP8）」；說明「大多數情況不需要更改」 |

- 任一值偏離 Preset 時，標籤顯示「均衡（已修改）」＋ [還原用途預設值]。
- 每個欄位旁有 `?` tooltip，文字來自 `params.<name>.help`。
- 下方：**▸ 進階設定（預設收起）**，內容見第 5 節。

### 4.5 Step 4：確認

```
│ 預估記憶體（僅供參考，實際用量以啟動結果為準）                              │
│ 模型權重 ██████ 15 GB │ 對話快取 ████ ~10 GB │ 其他 ██ ~3 GB   ≈ 28 GB   │
│ 此服務配額 70% ≈ 89 GB      目前系統可用 ≈ 95 GB                           │
│                                                                        │
│ ⚠ 警告                                                                 │
│  · 另一個模型服務已使用 30%，合計 100%，可能導致啟動失敗                       │
│                                                                        │
│ 最終設定                                                                 │
│  模型 Qwen2.5-7B · API 呼叫名稱 qwen-7b · 最長對話 32K · 記憶體 70% · 量化 自動│
│ ▸ 顯示實際啟動參數（進階）                                                  │
│                                                                        │
│                [上一步]                    [▶ 建立並啟動模型服務]           │
│                                              只儲存設定，稍後再啟動          │
```

- **主要 CTA**：`建立並啟動模型服務`（Mantine filled button）。
- **次要操作**：`只儲存設定，稍後再啟動`（subtle / link 樣式，位於主要按鈕下方，視覺明顯較弱）。
- 警告分級：
  - `info`（灰）：提示，不影響操作。
  - `warning`（黃）：可繼續，按鈕維持可用。
  - `blocking`（紅）：兩個按鈕皆停用。只用於**確定不可行**的情況：模型權重大於總記憶體、API 呼叫名稱重複、port 衝突、必填缺漏。
- 記憶體預估永遠標示「僅供參考」，估算規則待 Spark 實機校正。
- 建立並啟動後導向詳細頁（載入中狀態）；只儲存後導向詳細頁（已停止狀態），並提示「設定已儲存，可隨時啟動」。

---

## 5. 參數分類（Beginner / Advanced）

| 層級 | 參數 | 呈現 |
|---|---|---|
| 用途（Preset） | balanced / low_memory / long_context / high_throughput / custom | Step 2 卡片 |
| 基本 | 服務名稱、API 呼叫名稱、最長對話長度、記憶體使用比例、量化方式 | Step 3 直接顯示 |
| 基本（服務行為） | 開機自動啟動（Switch，預設關閉） | Step 3 底部、設定分頁 |
| 進階（收起） | dtype、信任遠端程式碼（開啟時顯示安全警告）、對外直連 port（除錯用，預設空）、額外啟動參數（附「不保證相容」警告）、自動啟動順序（數字） | 展開才顯示 |
| 未來擴充（進階） | max_num_seqs、kv_cache_dtype、prefix caching、chunked prefill、tool / reasoning parser、speculative decoding | 由 schema 新增，前端不改程式 |
| 僅診斷 | container、network、內部 port、LiteLLM model id、image digest、完整 CLI | 唯讀 |

### 5.1 參數 Schema（由 Backend 提供）

前端依 `GET /param-schema?model_id=` 動態產生表單，每個欄位：

```json
{
  "name": "max_model_len",
  "level": "basic",
  "type": "integer",
  "widget": "slider",
  "default": 32768,
  "min": 1024,
  "max": 32768,
  "marks": [4096, 8192, 32768],
  "unit": "tokens",
  "restart_required": true,
  "label_key": "params.max_model_len.label",
  "help_key": "params.max_model_len.help",
  "warnings": []
}
```

### 5.2 Preset 結構（`configs/presets.yaml`）

```yaml
balanced:
  label_key: presets.balanced.label
  description_key: presets.balanced.description
  recommended: true
  rules:
    gpu_memory_utilization: { from: profile.memory.default }
    max_model_len:          { min: [model.max_context, 32768] }
    dtype:                  { value: auto }
    quantization:           { from: model.detected_quantization, fallback: auto }
low_memory:
  label_key: presets.low_memory.label
  rules:
    gpu_memory_utilization: { from: profile.memory.low }
    max_model_len:          { min: [model.max_context, 8192] }
long_context:
  label_key: presets.long_context.label
  rules:
    gpu_memory_utilization: { from: profile.memory.high }
    max_model_len:          { from: model.max_context, cap: 131072 }
high_throughput:
  label_key: presets.high_throughput.label
  rules:
    gpu_memory_utilization: { from: profile.memory.high }
    max_model_len:          { min: [model.max_context, 16384] }
custom:
  label_key: presets.custom.label
  inherits: balanced
```

- 計算：`PresetResolver(profile, model_meta, preset) → { params, explanations[] }`。
- 第一版規則僅支援 `value` / `from` / `min` / `cap` / `fallback`；結構預留更複雜的規則。
- 實際數值待更多 Spark 實測校正（0.5B 模型 `gpu_memory_utilization=0.3` 已驗證可用；見 `docs/spark-validation.md`）。

---

## 6. 狀態與錯誤呈現

### 6.1 模型服務狀態

| 狀態碼 | 顯示 | 顏色 / 圖示 | 主要按鈕 | 其他操作 |
|---|---|---|---|---|
| `CREATED` / `STOPPED` | 已停止 | 灰 ○ | 啟動 | 編輯、刪除 |
| `STARTING` | 啟動中 | 藍 ◐ + 計時 | 取消啟動 | 查看 Log |
| `LOADING` | 載入中 | 藍 ◐ + 計時 + 步驟條 | 取消啟動 | 查看 Log |
| `READY` + gateway `registered` | 就緒 | 綠 ● | 停止 | 重新啟動、編輯、測試、Log |
| `READY` + gateway `pending` / `failed` | 就緒（尚未發布） | 黃 ◑ | 重試發布 | 停止、Log |
| `STOPPING` | 停止中 | 灰 ◐ | — | — |
| `ERROR` | 錯誤：{簡短原因} | 紅 ✕ | 處理 | 重新啟動、編輯、刪除、Log |

- 操作是非同步的：按下後該按鈕顯示 loading，互斥按鈕停用，直到後端狀態改變。
- 確認對話框：
  - 停止 / 重新啟動已發布的服務：「外部系統將暫時無法呼叫 `qwen-7b`」。
  - 刪除：需確認；運行中的服務不可刪除（須先停止）。
- 載入步驟條（`phase`）：`preparing → creating → loading → registering → ready`。

### 6.2 錯誤碼與呈現

Backend 回傳結構化錯誤，前端依 `code` 查 i18n：

```json
{
  "code": "OOM",
  "severity": "error",
  "params": { "requested_gb": 89 },
  "evidence": ["14:02:31 torch.OutOfMemoryError: CUDA out of memory..."],
  "suggestions": [
    { "action": "edit", "label_key": "errors.OOM.suggest.reduce_context", "patch": { "max_model_len": 8192 } },
    { "action": "apply_preset", "label_key": "errors.OOM.suggest.low_memory", "preset": "low_memory" },
    { "action": "navigate", "label_key": "errors.OOM.suggest.view_running", "target": "services?status=ready" }
  ],
  "occurred_at": "2026-10-04T14:02:31Z"
}
```

| 錯誤碼 | 使用者看到的標題 | 建議動作 |
|---|---|---|
| `OOM` | 模型啟動失敗：可用記憶體不足 | 降低最長對話長度、改用省記憶體、查看其他運行中的服務 |
| `MEMORY_PRECHECK` | 預估記憶體可能不足（啟動前警告） | 同上 |
| `MODEL_NOT_FOUND` | 找不到模型檔案 | 重新掃描模型、檢查模型目錄 |
| `MODEL_UNSUPPORTED` | 此模型架構目前不支援 | 查看 Log、改用其他模型 |
| `REMOTE_CODE_REQUIRED` | 此模型需要「信任遠端程式碼」 | 開啟進階選項（附安全說明） |
| `HEALTH_TIMEOUT` | 啟動逾時 | 查看 Log、重試 |
| `CRASHED` | 模型服務意外停止 | 查看 Log、重新啟動 |
| `PORT_CONFLICT` | 對外直連 port 已被占用 | 更換或清空此欄位 |
| `IMAGE_UNAVAILABLE` | 執行環境映像檔不存在 | 請管理員檢查（附診斷） |
| `GPU_UNAVAILABLE` | 無法使用 GPU | 檢查主機（總覽亮紅燈） |
| `DOCKER_UNAVAILABLE` | 無法連線容器執行環境 | 檢查主機 |
| `CONTAINER_MISSING` | 模型服務已被外部移除 | 重新啟動 |
| `GATEWAY_UNREACHABLE` | 無法連線到 Gateway | 查看 Gateway 頁 |
| `GATEWAY_REGISTER_FAILED` | 無法發布到 Gateway | 重試發布 |
| `GATEWAY_MODEL_NOT_FOUND` | Gateway 找不到此模型（測試時） | 重新同步 |
| `TEST_TIMEOUT` | 測試訊息逾時 | 稍後重試、查看 Log |
| `UNKNOWN` | 啟動失敗（原因未知） | 查看原始 Log |

- 每個錯誤碼在 i18n 需有：`title`、`description`、`suggest.*`。
- 錯誤偵測規則放在 `configs/error-patterns.yaml`（exit code、OOMKilled、log regex → code），實機遇到新樣式時只需新增規則。
- 原始 log 永遠可以透過「查看原始 Log」取得，但不作為主要訊息。

---

## 7. Backend API 需求

前綴 `/api/v1`。除 `/auth/login` 外皆需 `Authorization: Bearer <admin token>`。

### 7.1 API 清單

| API | 用途 |
|---|---|
| `POST /auth/login`、`GET /auth/me` | 登入、驗證 token |
| `GET /system/summary` | 總覽：健康摘要、資源、各狀態數量、`capabilities` |
| `GET /system/info` | 設定、診斷：profile、image digest、版本 |
| `GET /models`、`GET /models/{model_id}` | 模型清單與詳細（含使用中的模型服務） |
| `GET /model-sources`、`POST /model-sources/rescan` | 模型來源 |
| `GET /presets?model_id=` | Wizard Step 2：各 Preset 解析後的值與說明 |
| `GET /param-schema?model_id=` | Step 3、編輯設定：欄位定義 |
| `POST /instances/preview` | Step 4、編輯設定：最終參數、記憶體估算、分級警告、指令預覽（不建立） |
| `POST /instances` | 建立；body 含 `start: true \| false` |
| `GET /instances` | 清單 |
| `GET /instances/{id}` | 詳細：`status`、`phase`、`phase_started_at`、`last_error`、`gateway`、`endpoint`、`diagnostics` |
| `PATCH /instances/{id}` | 編輯；回傳 `restart_required`；可帶 `restart: true` |
| `POST /instances/{id}/start` · `/stop` · `/restart` · `/cancel` | 生命週期，回 202 |
| `POST /instances/{id}/gateway/retry` | 重試發布 |
| `DELETE /instances/{id}` | 刪除（需已停止） |
| `GET /instances/{id}/metrics` | 資源（僅回傳可取得的項目） |
| `GET /instances/{id}/events` | 事件時間軸 |
| `POST /instances/{id}/test` | 送出測試訊息（經由 LiteLLM） |
| `GET /logs/sources` | Log 來源清單 |
| `GET /logs/{source}?tail=&level=` | 取得 Log（含 `annotation`） |
| `GET /logs/{source}/stream` | SSE 即時 Log |
| `GET /gateway/status` | Gateway 健康、版本、資料庫狀態 |
| `GET /gateway/connection-info` | 對外 base URL、可用模型名稱、範例模板 |
| `GET /gateway/models` | 已發布模型與同步狀態 |
| `POST /gateway/resync` | 手動對帳 |
| `POST /gateway/models/{name}/cleanup` | 清除殘留 |
| `GET /gateway/keys` | API Key 清單（遮罩） |
| `POST /gateway/keys` | 建立 API Key；**回應中完整 key 只出現這一次** |
| `POST /gateway/keys/{key_id}/revoke` | 撤銷 API Key |
| `GET /system/external` | 偵測到的外部（非平台管理）服務：名稱、image、port、估計記憶體 |
| `GET /system/autostart` | 開機自動啟動進度：佇列、目前項目、結果 |
| `POST /system/autostart/cancel` | 取消剩餘的自動啟動 |

Instance 設定欄位新增：`autostart: bool`（預設 false）、`autostart_order: int`（預設 100，小的先啟動）。

### 7.2 API Key（LiteLLM Virtual Key）實作要點

- Backend 以 master key 呼叫 LiteLLM key 管理 API（generate / list / delete 或 block）；master key 僅存在 Backend 環境變數，永不回傳前端。
- 建立時以 metadata 標記 `created_by: dgxsp`、`display_name`，清單只列平台建立的 key。
- Backend 不持久化完整 key；清單只回傳 LiteLLM 提供的遮罩 / 識別資訊與建立時間、狀態。
- 第一版不設定 budget、rate limit、team、模型限制（全部可用模型皆可呼叫）。
- 撤銷為不可逆操作。

### 7.3 送出測試訊息實作要點

- Backend 啟動時確保存在一把**平台內部 virtual key**（metadata `purpose: system-test`），用於 `/instances/{id}/test`。
- 呼叫路徑：Backend → `LiteLLM /v1/chat/completions`（`model = served_model_name`）→ vLLM。
- 不使用 master key 發送測試請求，以確保測試條件與外部使用者一致。
- 固定小型請求（例如 `max_tokens: 32`）、設定逾時，回傳 `{ ok, latency_ms, reply_preview, error? }`。

### 7.4 更新機制

- 第一版：清單、詳細頁每 2–3 秒輪詢（TanStack Query）；Log 使用 SSE。
- 預留：全域事件 SSE（`/events/stream`），用於即時 Toast 與減少輪詢。

---

## 8. 前端技術約定

- React + TypeScript + Vite + Mantine
- 路由：React Router
- 資料：TanStack Query（輪詢、快取、mutation）
- 表單：Mantine Form 或 react-hook-form + zod；欄位由 param-schema 動態產生
- i18n：react-i18next
- Log 串流：EventSource
- API client：由 Backend OpenAPI 產生型別（`openapi-typescript`），避免前後端欄位不一致

---

## 9. 開機自動啟動與外部服務

### 9.1 開機自動啟動（Autostart）

使用者情境：Spark 停電 / 重開機後，院內系統依賴的模型應自動恢復，不需要有人登入 UI。

**行為**
- 平台本身（Backend、Web UI、LiteLLM、Postgres）：compose `restart: unless-stopped`，開機即起。
- vLLM container **不使用** Docker restart policy（避免同時啟動搶記憶體、避免狀態與平台不同步）。
- Backend 啟動後執行 **Autostart Manager**：
  1. 先對帳：把 DB 中「上次是 RUNNING 但 container 已不存在」的服務標為 `STOPPED`（事件：「主機重新啟動」）。
  2. 取出 `autostart = true` 的服務，依 `autostart_order`、再依建立時間排序。
  3. **一次只啟動一個**：等它 `READY`（或 `ERROR` / 逾時）才啟動下一個。
  4. 每個啟動前做記憶體預檢；預檢為 `blocking` 時跳過並記錄事件，不中斷後續項目。
  5. 某個失敗不影響其他；失敗的服務照一般 `ERROR` 呈現。
- 手動「停止」不會改變 `autostart` 設定（下次開機仍會自動啟動）。
- 使用者可在總覽按「取消剩餘的自動啟動」。

**UI**
- Step 3（基本設定）底部：
  ```
  ☐ Spark 開機時自動啟動此模型服務
     重新開機後會依序自動啟動，不需要人工操作。
  ```
- 清單與詳細頁：已勾選者在名稱旁顯示小圖示「⟳ 自動啟動」。
- 詳細頁設定分頁可切換；進階設定可調整「啟動順序」。
- 總覽：自動啟動進行中顯示進度條與目前項目；完成後若有失敗，健康摘要顯示「開機自動啟動：1 個失敗」。
- 事件時間軸：「主機重新啟動」「自動啟動排隊中」「自動啟動：已就緒 / 失敗（原因）」。
- Step 4 警告：所有 `autostart` 服務的記憶體使用比例加總超過門檻時，顯示 `warning`「開機時可能無法全部啟動」。

**i18n keys**：`instances.autostart.label`、`instances.autostart.help`、`dashboard.autostart.progress`、`dashboard.autostart.failed`、`events.host_restarted`、`events.autostart_*`。

### 9.2 外部服務（非平台管理）

定義：不帶 `dgxsp.*` label 的 container 或主機 process，但使用 GPU 或佔用平台需要的 port。
來源：Docker container 清單（image 名含 `vllm` 等規則）、`nvidia-smi --query-compute-apps` 的 process 與記憶體、平台需要的 port（Gateway、Web）占用檢查。

**原則**：平台**不會停止、修改或刪除**外部服務；只偵測、顯示、納入記憶體計算。

**UI**
- 總覽提示卡（黃色）：
  ```
  ⚠ 偵測到 1 個非本平台管理的模型服務，約使用 36 GB 記憶體。
     它不會出現在「模型服務」中，也無法從這裡停止。     [查看詳細]
  ```
  [查看詳細] 開啟 Drawer：名稱、image、port、記憶體、啟動時間，以及「如需停止，請由原本啟動它的方式處理」的說明。
- Step 4 記憶體預估：外部服務用量列為一個區塊「其他程式 ≈ 36 GB」，並據此給警告。
- Port 衝突：Gateway port 被外部占用時，總覽健康摘要顯示「Gateway port 4000 被其他程式占用」（錯誤碼 `GATEWAY_PORT_IN_USE`）。

**錯誤碼新增**：`GATEWAY_PORT_IN_USE`、`AUTOSTART_SKIPPED_MEMORY`。

---

## 10. MVP 範圍外（預留，不實作）

- 下載模型（Hugging Face repo ID）
- 多使用者、RBAC、SSO
- API Key 的 quota / budget / team / 到期時間
- 英文翻譯完整化
- 依歷史資料預估載入時間
- 全域事件推播
- 進階 vLLM 參數（吞吐、parser、speculative decoding 等）
