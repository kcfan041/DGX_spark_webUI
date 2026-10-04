**DGX Spark LLM Control Platform**

**架構規劃與元件說明**

目標：以 Docker + vLLM 為推論層、LiteLLM 為統一 API
Gateway，補上一個初學者友善的 Web 控制台。

| **一句話定位：**這不是重新開發 vLLM 或 LiteLLM，而是做一層 DGX Spark 專用的管理控制面，將模型下載、vLLM 參數、容器生命週期、API Gateway、日誌與監控整合成網頁操作。 |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 1. 專案目標

- 讓不熟悉 Linux、Docker、vLLM
  指令的使用者，也能透過網頁啟動、停止與設定本地 LLM。

- 以 OpenAI-compatible API 對外提供模型服務，讓院內系統、OpenCode
  或其他應用只需要知道單一 API 入口。

- 盡量沿用成熟開源元件，將自製範圍集中在
  UI、管理後端、參數抽象與各元件之間的 glue code。

- 第一版優先追求「可用、好懂、可維護」，不以完整雲端平台或大規模多租戶為目標。

# 2. 整體架構

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>使用者 / 院內系統 / OpenCode<br />
│<br />
▼<br />
┌────────────────┐<br />
│ LiteLLM │ ← 統一 API、API Key、Routing<br />
└───────┬────────┘<br />
│<br />
OpenAI-compatible API<br />
│<br />
┌────────┼─────────┐<br />
▼ ▼ ▼<br />
vLLM #1 vLLM #2 vLLM #3<br />
Qwen Llama 其他模型<br />
│ │ │<br />
└────────┴─────────┘<br />
│<br />
DGX Spark<br />
<br />
┌──────────────────────────────────────┐<br />
│ 自製 Web Control Plane │<br />
│ 模型 / vLLM Instance / Docker / Log │<br />
│ GPU-RAM / LiteLLM 註冊 / 設定 │<br />
└──────────────────────────────────────┘<br />
│<br />
└── 控制與管理上述元件</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**重要：**LiteLLM 是「對外資料流」的入口；自製 Web
控制台是「管理控制流」的入口。兩者概念上是平行角色，不需要把所有請求先經過管理
UI。

# 3. 會用到的主要元件

| **元件**                              | **用途**                                                                           | **定位**   |
|---------------------------------------|------------------------------------------------------------------------------------|------------|
| **DGX OS**                            | DGX Spark 的作業系統與 NVIDIA 軟體環境。                                           | 主機層     |
| **Docker / NVIDIA Container Runtime** | 隔離 vLLM、LiteLLM 與其他服務，降低相依套件衝突。                                  | 容器層     |
| **spark-vllm-docker**                 | 針對 DGX Spark / ARM64 / Blackwell 的 vLLM Docker 建置與啟動參考。                 | 部署輔助   |
| **vLLM**                              | 實際載入模型、使用 GPU 做推論，並提供 OpenAI-compatible API。                      | 推論層     |
| **LiteLLM**                           | 統一 API Gateway，集中模型名稱、API Key、Routing、Fallback、使用紀錄等。           | Gateway 層 |
| **自製 Backend**                      | 管理 Docker、模型、vLLM 參數、狀態、日誌與 LiteLLM 設定。                          | 控制層     |
| **自製 Web UI**                       | 把複雜設定轉成表單、按鈕、預設值與錯誤提示。                                       | 介面層     |
| **Hugging Face / 本地模型目錄**       | 模型來源與儲存位置。                                                               | 資料層     |
| **OpenCode（開發用）**                | 協助撰寫、修改、測試與除錯此平台。不是正式服務必要元件。                           | 開發工具   |
| **9Router（可選）**                   | 可作為個人開發時的模型路由工具；若正式環境已使用 LiteLLM，通常不必重複放在服務端。 | 可選工具   |

# 4. 自製 Web 控制台的功能範圍

## 4.1 Dashboard

- DGX Spark GPU / Unified Memory / 磁碟使用量。

- 目前運行中的 vLLM instances。

- 各模型 Ready / Starting / Error / Stopped 狀態。

- LiteLLM Gateway 與各 vLLM endpoint 健康狀態。

## 4.2 Models

- 查看本地已下載模型。

- 從 Hugging Face 下載模型，管理 Token 與下載進度。

- 顯示模型大小、路徑、量化格式與基本 metadata。

- 刪除模型前檢查是否仍被 instance 使用。

## 4.3 vLLM Instances

- 建立、啟動、停止、重啟與刪除 instance。

- 為每個 instance 指定模型、port 與資源配置。

- 顯示實際產生的啟動設定與 container 狀態。

- 啟動後自動 health check；失敗時顯示可理解的錯誤。

## 4.4 vLLM 參數表單

- 模型路徑 / model ID。

- max-model-len（context length）。

- gpu-memory-utilization。

- quantization / dtype。

- tensor parallel 等硬體相關參數。

- 進階參數收在 Advanced 區域，避免初學者第一眼面對所有 CLI flags。

## 4.5 LiteLLM 管理

- 成功啟動 vLLM 後，自動註冊成可用模型。

- 統一 model alias，讓外部系統不需要知道內部 port。

- API Key、基本權限與 routing 設定。

- instance 移除或改 port 時同步更新 Gateway。

## 4.6 Logs / Monitoring

- 查看 vLLM / LiteLLM / Backend container logs。

- 顯示 GPU / RAM / disk 等基本資源。

- 保留錯誤事件，方便追查 OOM、模型載入失敗與 API 問題。

# 5. 典型操作流程

1.  使用者在 Web UI 選擇或下載一個模型。

2.  建立 vLLM Instance，選擇初學者預設或調整進階參數。

3.  Backend 驗證設定，產生對應 Docker / vLLM 啟動配置。

4.  Backend 啟動 container 並持續檢查 health endpoint。

5.  成功後自動將該 endpoint 註冊到 LiteLLM。

6.  使用者取得統一的 LiteLLM Base URL 與 API Key。

7.  外部系統以 model alias 呼叫，不需要知道 vLLM 實際 port。

8.  若模型出錯，管理 UI 顯示狀態、資源與
    log；使用者可停止、修改設定後重啟。

# 6. 建議 Repository 結構

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>dgx-spark-llm-platform/<br />
├─ frontend/ # Web UI<br />
├─ backend/ # 管理 API / Docker orchestration<br />
├─ configs/<br />
│ ├─ litellm.yaml<br />
│ ├─ models.yaml<br />
│ └─ defaults.yaml<br />
├─ docker/<br />
│ ├─ compose.yaml<br />
│ └─ templates/ # vLLM container template<br />
├─ scripts/<br />
│ ├─ health-check.sh<br />
│ └─ bootstrap.sh<br />
├─ docs/<br />
│ └─ architecture.md<br />
└─ README.md</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**原則：**自己的 repo 應以「整合與控制」為主，而不是把
vLLM、LiteLLM、spark-vllm-docker 三個專案整包複製進來。優先以 Docker
image、設定檔、API、CLI 或可維護的外部依賴方式引用。

# 7. MVP（第一版）建議邊界

- 單台 DGX Spark。

- 先支援一到數個 vLLM containers，不做複雜排程。

- 可選本地模型並設定少數最重要的 vLLM 參數。

- Start / Stop / Restart / Logs / Health Check。

- 成功啟動後可由 LiteLLM 統一對外。

- 提供基本 API Key。

- 顯示 GPU / Unified Memory / Disk 基本狀態。

- 保留 Advanced settings，但不追求把每一個 vLLM CLI flag 都做成 UI。

**第一版暫時不需要：**
Kubernetes、多節點排程、完整多租戶計費、HA、自動水平擴縮、複雜
quota、完整 Grafana 平台。這些可以等實際需求出現再加。

# 8. 主要風險與注意事項

| **風險**                         | **處理方向**                                                                                                             |
|----------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| **DGX Spark 相容性**             | Spark 是 ARM64 + Blackwell / Unified Memory 平台；不要假設所有 x86 CUDA/vLLM image 都能直接使用。應固定並驗證可用版本。  |
| **參數不是全部都能即時修改**     | 許多 vLLM 參數需要重啟 instance 才生效，因此 UI 要清楚區分「可即時改」與「需重啟」。                                     |
| **不同模型有例外**               | 不同模型可能需要不同 dtype、quantization、trust-remote-code、context 或 tokenizer 設定，無法完全用一套固定表單安全涵蓋。 |
| **OOM / 資源競爭**               | 多個 instance 同時存在時，模型權重、KV cache 與 runtime 都會消耗記憶體。UI 應做基本預估、警告與失敗回復。                |
| **Docker 權限**                  | Backend 若能控制 Docker，等同具有很高的主機權限。正式對外時必須限制登入與管理 API。                                      |
| **Gateway 與 Instance 狀態同步** | vLLM 啟動失敗、port 變更或 container 被手動刪除時，LiteLLM 設定不可繼續指向失效 endpoint。                               |
| **上游版本變化**                 | vLLM / LiteLLM 的參數與 API 會演進。控制台應用「能力偵測 + 版本鎖定」而非把所有行為寫死。                                |

# 9. 開發方式與 AI 協作定位

- OpenCode 可以直接在 DGX Spark 上協助建立 repo、Docker
  配置、Backend、Frontend、測試與文件。

- OpenCode / 9Router
  是「開發與施工工具」，不應成為平台正式運作不可替代的必要依賴。

- 開發時優先讓 AI 先做可運作版本，再針對實際架構補理解與驗收；不需要先把
  Linux、Docker、vLLM 全部學完才開始。

- 人需要掌握最少的驗收知識：服務在哪裡、API
  怎麼走、模型如何啟停、設定存在哪裡、怎麼看 log、OOM 或 endpoint
  掛掉時如何判斷。

# 10. 最終定位

**本專案可以定義為：「DGX Spark 專用的 LLM Control Plane / Web
Console」**

底層沿用 Docker + vLLM + LiteLLM
等成熟元件，自製部分專注於初學者友善的操作介面、模型與 instance
生命週期管理、參數抽象、狀態同步、日誌與基本資源監控。這樣可以在避免重造輪子的前提下，形成一套適合
DGX Spark 實際使用的完整管理體驗。
