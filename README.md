# StockBot — 台股 Discord 機器人 (懶人看盤)

監控台灣股市（TWSE／TPEx）、推播財經新聞、管理個人投資組合的 Discord Bot。

---

## 功能概覽

- 即時股價查詢與多檔比較
- 到價警示（觸發後 @mention 通知）
- 自選股管理與大幅波動警示
- 交易記錄與損益追蹤（LIFO 成本法）
- 產業類別瀏覽
- 財經新聞自動推播（開盤晨報、即時快訊、收盤總整理、週報）

---

## 部署前置條件

### 1. Python

需要 Python 3.11 以上（使用 `zoneinfo` 標準函式庫）；目前已在 Python 3.14.5 測試通過。

### 2. Discord Bot

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications) 建立新 Application
2. 進入 **Bot** 頁籤 → 建立 Bot → 複製 **Token**
3. 在 **Bot** 頁籤開啟 **Message Content Intent**
4. 進入 **OAuth2 → URL Generator**，勾選 `bot` + `applications.commands`，Bot Permissions 勾選 `Send Messages`、`Embed Links`、`Read Message History`
5. 用產生的網址將 Bot 邀請進你的伺服器

**取得 Channel ID：**  
Discord 設定 → 進階 → 開啟「開發者模式」，右鍵點擊頻道 → 複製 ID。

### 3. Fugle Market Data API

1. 前往 [Fugle Developer](https://developer.fugle.tw/) 註冊並申請 API Key
2. 選擇支援 **Market Data REST API** 的方案（免費方案即可使用）

---

## 安裝與設定

```bash
# 1. 安裝相依套件
pip install -r requirements.txt

# 2. 建立 .env 檔案
cp .env.example .env
```

編輯 `.env`，填入以下四個變數：

```env
DISCORD_TOKEN=你的_Discord_Bot_Token
FUGLE_API_KEY=你的_Fugle_API_Key
NEWS_CHANNEL_ID=新聞推播頻道的_Channel_ID
ALERT_CHANNEL_ID=警示推播頻道的_Channel_ID
```

> `NEWS_CHANNEL_ID` 用於新聞推播；`ALERT_CHANNEL_ID` 用於到價警示、波動警示與週報。可以設定為同一個頻道。

---

## 啟動

```bash
python main.py
```

Bot 啟動後會自動同步 Slash Commands 並啟動所有排程任務。

---

## 開發與測試

核心交易與警示規則位於 `domain/`，可不依賴 Discord、Fugle API 或 SQLite 直接執行單元測試。

```bash
python -m unittest discover -s tests
```

目前測試涵蓋交易日期解析、手續費、證交稅、LIFO 成本計算、買賣持倉計算、價格警示與波動門檻判斷。

---

## Slash Commands

### 查詢

| 指令 | 說明 |
|---|---|
| `/q 2330` | 輸入代號 → 即時報價 |
| `/q 台積電` | 輸入名稱關鍵字 → 搜尋股票 |
| `/symbol 2330 2454 0050` | 並排比較多檔股票或指數（最多 5 檔） |

> 指數代號範例：`IX0001`（加權指數）、`IX0002`（櫃買指數）

### 價格警示

| 指令 | 說明 |
|---|---|
| `/alert set 2330 1000` | 設定到價提醒（自動判斷突破或跌破） |
| `/alert list` | 查看我的警示清單 |
| `/alert remove 編號` | 刪除指定警示 |

> 每支股票最多 3 個警示，觸發後自動刪除。

### 自選股

| 指令 | 說明 |
|---|---|
| `/watch add 2330` | 加入自選股（上限 10 檔） |
| `/watch remove 2330` | 移除自選股 |
| `/watch list` | 查看自選股即時報價 |
| `/watch clear` | 清空自選股 |

### 交易記錄與損益

所有交易指令皆為私訊（Ephemeral），只有本人可見。

| 指令 | 說明 |
|---|---|
| `/trade buy 2330 1000 1000` | 記錄買入（代號 價格 股數） |
| `/trade sell 2330 1100 1000` | 記錄賣出（自動計算手續費與當沖稅率） |
| `/trade profit` | 查看全部持倉損益摘要 |
| `/trade profit 2330` | 查看單一股票損益詳情 |
| `/trade history` | 查看全部交易明細 |
| `/trade history 2330` | 查看單一股票交易明細 |
| `/trade reset 2330` | 清除指定股票的紀錄 |
| `/trade reset` | 清除所有交易紀錄 |

> 買賣指令可選填交易日期（格式 `YYYY-MM-DD`），省略預設為當日。

### 產業類別

| 指令 | 說明 |
|---|---|
| `/sector list` | 列出所有產業類別及股票數量 |
| `/sector search 半導體業` | 查詢該產業所有股票（支援翻頁） |

---

## 自動推播排程

| 時間 | 內容 | 頻道 |
|---|---|---|
| 每 1 分鐘 | 財經＋國際新聞即時推播 | 新聞頻道 |
| 每 2 分鐘（盤中） | 到價警示掃描 | 警示頻道 |
| 每 5 分鐘（盤中） | 重大新聞速報 | 新聞頻道 |
| 每 5 分鐘（盤中） | 自選股大幅波動警示（±3%） | 警示頻道 |
| 週一至週五 09:00 | 開盤晨報（最新財經新聞） | 新聞頻道 |
| 週一至週五 13:30 | 收盤總整理 | 新聞頻道 |
| 週五 14:00 | 自選股本週績效週報 | 警示頻道 |

> 盤中時段定義：週一至週五 09:00–13:30（Asia/Taipei）

---

## 費用計算說明

| 項目 | 費率 |
|---|---|
| 買進手續費 | 成交金額 × 0.1425%，最低 20 元 |
| 賣出手續費 | 成交金額 × 0.1425%，最低 20 元 |
| 證交稅（一般股票） | 成交金額 × 0.3% |
| 證交稅（ETF） | 成交金額 × 0.1% |
| 現股當沖稅率 | 以上稅率各減半 |
