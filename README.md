# DGX Spark LLM Control Platform

DGX Spark 專用、初學者友善的 LLM Control Plane / Web Console。
以 Docker + vLLM 為推論層、LiteLLM 為統一 API Gateway，自製 Backend + Web UI 負責整合與管理。

## 文件

- [架構規劃](docs/architecture.md)
- [UI/UX 規格](docs/ui-spec.md)
- [DGX Spark 實機驗證（smoke test）](docs/spark-validation.md)

## 目錄

```
docs/          架構、UI 規格、實機驗證
smoke/         Spark smoke test（compose、runner、profiles）
mock-vllm/     假的 vLLM，供無 GPU 環境開發測試
scripts/       preflight、模型下載
```

## 狀態

- [x] 規劃與 UI 規格
- [x] P0a：smoke 工具
- [x] Spark smoke test（2026-10-05，16/16 PASS）
- [ ] P0b：Backend / Frontend 骨架
