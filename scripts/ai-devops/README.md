# AI DevOps 自動化系統

## 概述

這是一個基於 Kimi K2.7 API 和 Cursor CLI 的 GitHub PR 自動化系統。

## 工作流程

```
GitHub PR (label: ai-devops)
         ↓
   [Cron Job 觸發]
         ↓
┌─────────────────────────────────────┐
│  1. Kimi K2.7 生成代碼              │
│     - 解析 planned_features         │
│     - 生成代碼文件                   │
│     - 創建 branch + PR              │
├─────────────────────────────────────┤
│  2. Cursor CLI 做代碼審查           │
│     - 分析代碼變更                   │
│     - 檢查邏輯/效能/安全            │
│     - 在 PR 留言審查報告             │
└─────────────────────────────────────┘
```

## 腳本說明

| 腳本 | 功能 |
|------|------|
| `ai_devops.py` | 主調度腳本，由 cron 觸發 |
| `kimi_coder.py` | Kimi K2.7 代碼生成器 |
| `cursor_reviewer.py` | Cursor CLI 代碼審查器 |
| `setup_cron.sh` | Cron job 設定腳本 |

## 設定步驟

### 1. 確認依賴

```bash
# 確認 Python 3
python3 --version

# 確認 GitHub CLI
gh auth status
gh auth login  # 如未登入
```

### 2. 設定 Cron Job

```bash
cd scripts/ai-devops
./setup_cron.sh
```

預設為每日凌晨 2:00 執行。可自行修改 `setup_cron.sh` 中的 `CRON_EXPRESSION`。

### 3. 手動測試

```bash
# 測試整個流程
python3 ai_devops.py

# 單獨測試 Kimi 代碼生成
python3 kimi_coder.py --pr 123 --body "## Feature 1\nName: 新功能"

# 單獨測試 Cursor 審查
python3 cursor_reviewer.py --pr 123
```

## PR 標籤要求

觸發自動化的 PR 需要：
- 標籤：`ai-devops`
- 描述包含 `planned_features` 區塊

### 描述格式示例

```markdown
## AI DevOps 任務

### planned_features

## Feature 1: 用戶登入功能
Name: 用戶登入功能
Description: 實現基於 JWT 的用戶登入功能

```python
# 代碼模板（可選）
def login(username, password):
    pass
```

## Feature 2: 用戶註冊功能
Name: 用戶註冊功能
Description: 實現用戶註冊功能
```

## 配置

腳本頂部的配置變數：

```python
# kimi_coder.py
KIMI_ENDPOINT = "https://api.kimi.com/coding/v1"
MODEL = "kimi-k2.7-code"
API_KEY = "your-api-key"  # 已在腳本中設定
```

## 查看日誌

```bash
# 實時查看日誌
tail -f logs/ai_devops.log

# 查看歷史日誌
cat logs/ai_devops.log
```

## 常見問題

### Q: Cron job 沒有執行？
```bash
# 檢查 crontab
crontab -l

# 測試 cron 是否正常
sudo systemcrontab -l  # macOS
```

### Q: Kimi API 調用失敗？
- 檢查 API key 是否正確
- 確認網路可以訪問 `api.kimi.com`

### Q: GitHub CLI 未認證？
```bash
gh auth login
```

## License

MIT
