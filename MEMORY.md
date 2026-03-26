# AI 3Kingdom 項目重要備忘錄

## ⚠️ 項目範圍
- **只處理 AI 3Kingdom 項目**
- **不要管 FDG 項目**

## 開發規範
- 使用 **opencode** 而非 OpenClaw 內建開發工具
- 開發完成後直接部署到本地測試環境 http://192.168.198.119:10090/

## 🔧 部署規範（重要！）
- 部署時，**嚴格保存舊數據庫**
- **每次部署前，必定要做備份**
- 先測試確認無問題後再上線

## 📋 部署後需要驗證
- 首頁 UI 正常顯示
- Agent 命名提示是否出現
- /tutorial 頁面是否正常

## 🧠 2026-03-26 系統分析記錄
- 專案目前為「可運行的單城節點 + 聯邦雛形」，核心功能（帳號、Agent、社交、戰鬥、排行榜、公告）已落地。
- 後端主體為 FastAPI + SQLAlchemy，入口在 `backend/app/main.py`，路由按領域拆分（auth/agent/action/social/world/federation/combat/admin）。
- 聯邦 API 已有 `/federation/v1/status|hello|message|attack|migrate`，具備簽名驗證與 request_id 去重基礎能力。
- 主要風險：
  - `/action/work` 使用常數 `CITY_TAX_RATE`，未完全跟隨 `settings.city_tax_rate`。
  - `/agent/migrate` 為本地欄位切換，非完整聯邦遷移握手流程。
  - 聯邦遷入角色能力值目前重骰，未沿用來源節點能力。
  - 部分預設為開發向（如 `jwt_secret`、`federation_shared_secret` 預設值）。
- 與架構願景相比，當前在「跨城可驗證性、強一致保護、可審計硬化」仍屬 MVP/P1 階段。

---

*最后更新：2026-03-26*
