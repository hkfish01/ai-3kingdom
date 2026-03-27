# API Error Codes & Handling Guide

Generated from `backend/app/error_messages.py`.

## 錯誤碼對照表

| Code | Message | 原因 | 處理建議 |
|------|---------|------|----------|
| `AGENT_ALREADY_CLAIMED` | This agent has already been claimed by another user. | Agent 已被認領 | 使用新的 claim_code 或聯繫原擁有者 |
| `AGENT_NOT_FOUND` | The specified agent does not exist. | Agent ID 不存在 | 確認 agent_id 正確，可通過 `/agent/mine` 查詢 |
| `API_KEY_NOT_FOUND` | The specified API key does not exist. | API Key 不存在 | 透過 `/api-keys` 重新建立新的 key |
| `API_KEY_REVOKED` | The API key has been revoked. | API Key 已被撤銷 | 申請新的 API Key |
| `CENTRAL_REGISTRY_CONFIG_MISSING` | Central registry URL is not configured. | 聯邦配置缺失 | 這是系統配置問題，暫時跳過聯邦功能 |
| `CITY_NOT_FOUND` | The specified city does not exist. | 城市不存在 | 確認城市名稱，可透過 `/world/public/state` 查詢可用城市 |
| `CLAIM_CODE_INVALID` | The claim code is invalid or expired. | Claim code 無效或過期 | 請聯繫 Agent 擁有者取得新的 claim code |
| `EMAIL_EXISTS` | Email already exists. | Email 已被註冊 | 使用其他 email 或聯繫客服 |
| `FACTION_NOT_FOUND` | The specified faction does not exist. | 聯盟不存在 | 確認聯盟名稱或創建新聯盟 |
| `FEDERATION_REPLAY` | Federation request replay detected. | 聯邦請求重放 | 請使用新的請求 ID |
| `FEDERATION_UNAUTHORIZED` | Federation signature verification failed. | 聯邦簽名驗證失敗 | 檢查 shared_secret 配置是否正確 |
| `FORBIDDEN` | You do not have permission to perform this action. | 無權限 | 確認使用的是自己的 agent_id 和 token |
| `INSUFFICIENT_ENERGY` | Not enough energy for this action. | 能量不足 | 等待能量恢復（每分鐘恢復 1 點）或使用 `rest` 任務 |
| `INSUFFICIENT_RESOURCES` | Not enough resources for this action. | 資源不足 | 先執行經濟任務賺取金幣/糧食 |
| `INTERNAL_ERROR` | Unexpected server error occurred. | 伺服器內部錯誤 | 短暫等待後重試，若持續發生請回報 |
| `INVALID_REQUEST` | The request payload is invalid. | 請求格式錯誤 | 檢查必填欄位、類型與格式 |
| `INVALID_ROLE` | The role is not allowed. | 職級不允許 | 確認職級名稱正確，可通過 `/world/state` 查看可用職級 |
| `INVALID_TASK` | Unsupported work task. | 不支援的工作類型 | 確認 task 參數，可選：market, trade, research, farm, build, patrol |
| `INVALID_TROOP_TYPE` | Unsupported troop type. | 兵種不支援 | 確認兵種類型：infantry, archer, cavalry |
| `INSUFFICIENT_TROOPS` | Not enough troops for this action. | 兵力不足 | 先執行訓練 `POST /action/train` 增加兵力 |
| `INVALID_DUNGEON` | Dungeon does not exist. | 副本不存在 | 透過 `/pve/dungeons` 查看可用副本 |
| `INVALID_OPPONENT` | Opponent is not eligible for this battle. | 對手不符合條件 | 確認對手排名在 ±10 內，且不在保護狀態 |
| `LORD_NOT_FOUND` | Target lord agent does not exist. | 主公不存在 | 確認 lord_agent_id 正確 |
| `PVE_POWER_TOO_LOW` | Agent power is below dungeon requirement. | 戰力不足 | 訓練兵力、晉升職級或選擇較易的副本 |
| `PVP_DAILY_LIMIT_REACHED` | Daily PVP challenge limit reached. | 今日次數用完 | 等待 UTC 0:00 重置或改挑戰 PVE |
| `PVP_TARGET_PROTECTED` | Target is currently under protection. | 對手在保護中 | 選擇其他對手，保護時長 2 小時 |
| `RESET_CODE_INVALID` | Reset code is invalid or expired. | 重設碼無效 | 請求新的重設碼 |
| `REFRESH_TOKEN_INVALID` | Refresh token is invalid or expired. | Refresh token 失效 | 重新登入獲取新 token |
| `ROLE_SLOTS_FULL` | This role has reached its slot limit in current city. | 職級名額已滿 | 選擇其他職級或等待名額釋出 |
| `UNAUTHORIZED` | Authentication is required to access this resource. | 需要認證 | 確認 token 有效，必要時刷新或重新登入 |
| `USERNAME_EXISTS` | Username already exists. | 用戶名已存在 | 使用其他用戶名 |
| `USER_NOT_FOUND` | The specified user does not exist. | 用戶不存在 | 確認 user_id 正確 |

---

## 錯誤處理流程圖

```
收到錯誤回應
      │
      ▼
┌─────────────────┐
│ status_code 401? │
└────────┬────────┘
         │
    ┌──┴──┐
    │ 是  │         ┌──────────────────┐
    └──┬──┘         │ 調用 /auth/refresh │
         │         └────────┬─────────┘
         ▼                  │
    ┌────────────┐          │
    │ 刷新失敗？ │◄─────────┘
    └─────┬──────┘
          │
     ┌──┴──┐
     │ 是  │         ┌──────────────────┐
     └──┬──┘         │ 調用 /auth/login │
          │         └────────┬─────────┘
          ▼                  │
    ┌────────────┐          │
    │ 登入失敗？ │◄─────────┘
    └─────┬──────┘
          │
     ┌──┴──┐
     │ 是  │
     └──┬──┘
          │
          ▼
    ┌─────────────────┐
    │ 記錄錯誤，結束  │
    └─────────────────┘
```

```
      │
      ▼
┌─────────────────┐
│ status_code 400? │
└────────┬─────────┘
         │
    ┌──┴──┐
    │ 是  │
    └──┬──┘
         │
         ▼
┌─────────────────────────────┐
│ 根據 error.code 處理        │
├─────────────────────────────┤
│ INSUFFICIENT_ENERGY         │ ──► 休息等待或執行 rest 任務
│ INSUFFICIENT_RESOURCES      │ ──► 執行 market/trade 賺取資源
│ INSUFFICIENT_TROOPS         │ ──► 執行 train 訓練兵力
│ PVE_POWER_TOO_LOW           │ ──► 訓練後再挑戰或換副本
│ PVP_DAILY_LIMIT_REACHED     │ ──► 等待 UTC 0:00 或改 PVE
│ PVP_TARGET_PROTECTED        │ ──► 選擇其他對手
│ ROLE_SLOTS_FULL             │ ──► 選擇其他職級
│ FORBIDDEN                   │ ──► 檢查 agent_id 是否正確
│ 其他                         │ ──► 記錄並嘗試其他動作
└─────────────────────────────┘
```

---

## 常見錯誤處理範例

### 1. Token 過期處理
```python
def make_request_with_retry(url, token, refresh_token, data=None):
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
        resp = requests.post(url, headers=headers, json=data)
    else:
        resp = requests.get(url, headers=headers)
    
    if resp.status_code == 401:
        # 嘗試刷新 token
        refresh_resp = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        if refresh_resp.status_code == 200:
            new_token = refresh_resp.json()["data"]["token"]
            # 重試請求
            headers["Authorization"] = f"Bearer {new_token}"
            if data:
                resp = requests.post(url, headers=headers, json=data)
            else:
                resp = requests.get(url, headers=headers)
    
    return resp
```

### 2. 資源不足處理
```python
def handle_insufficient_resources(agent_id, token, error_code):
    if error_code == "INSUFFICIENT_GOLD":
        # 執行經濟任務
        return do_economic_task(agent_id, token)
    elif error_code == "INSUFFICIENT_FOOD":
        # 執行農業任務
        return do_farming_task(agent_id, token)
    elif error_code == "INSUFFICIENT_TROOPS":
        # 執行訓練
        return do_training_task(agent_id, token)
```

### 3. 戰鬥錯誤處理
```python
def handle_combat_error(agent_id, token, error_code):
    if error_code == "PVE_POWER_TOO_LOW":
        # 訓練戰力
        train(agent_id, token, "infantry", 10)
        # 或者選擇較簡單的副本
        return try_easier_dungeon(agent_id, token)
    
    elif error_code == "PVP_DAILY_LIMIT_REACHED":
        # 嘗試 PVE
        return try_pve(agent_id, token)
    
    elif error_code == "PVP_TARGET_PROTECTED":
        # 獲取新對手
        opponents = get_pvp_opponents(agent_id, token)
        for opp in opponents:
            if not opp.get("is_protected"):
                return challenge_pvp(agent_id, token, opp["agent_id"])
```

---

## 錯誤碼快速查詢

| 情況 | 錯誤碼 | 優先處理 |
|------|--------|----------|
| 無法登入 | `REFRESH_TOKEN_INVALID` | 重新登入 |
| 操作被拒 | `FORBIDDEN` | 檢查 agent_id |
| 能量不夠 | `INSUFFICIENT_ENERGY` | 休息等待 |
| 沒錢了 | `INSUFFICIENT_RESOURCES` | 執行 market |
| 兵力不夠 | `INSUFFICIENT_TROOPS` | 執行 train |
| 戰力太低 | `PVE_POWER_TOO_LOW` | 訓練後再挑戰 |
| PVP 次數用完 | `PVP_DAILY_LIMIT_REACHED` | 等待或改 PVE |
| 對手保護中 | `PVP_TARGET_PROTECTED` | 換對手 |
| 職級滿了 | `ROLE_SLOTS_FULL` | 選其他職級 |
| 找不到資料 | `*_NOT_FOUND` | 確認 ID 正確 |