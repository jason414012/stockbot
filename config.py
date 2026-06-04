import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# ════════════════════════════════════════════════════════
#  機密資訊（從 .env 載入）
# ════════════════════════════════════════════════════════

DISCORD_TOKEN    = os.getenv("DISCORD_TOKEN", "")
FUGLE_API_KEY    = os.getenv("FUGLE_API_KEY", "")
NEWS_CHANNEL_ID  = int(os.getenv("NEWS_CHANNEL_ID", "0"))
ALERT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID", "0"))

if not DISCORD_TOKEN:
    raise SystemExit("[FATAL] DISCORD_TOKEN 未設定，請檢查 .env 檔案")
if not FUGLE_API_KEY:
    raise SystemExit("[FATAL] FUGLE_API_KEY 未設定，請檢查 .env 檔案")
if not NEWS_CHANNEL_ID:
    print("[WARN] NEWS_CHANNEL_ID 未設定，新聞推播功能將無法運作")
if not ALERT_CHANNEL_ID:
    print("[WARN] ALERT_CHANNEL_ID 未設定，警示推播功能將無法運作")

# ════════════════════════════════════════════════════════
#  時區
# ════════════════════════════════════════════════════════

TW = ZoneInfo("Asia/Taipei")

# ════════════════════════════════════════════════════════
#  資料庫
# ════════════════════════════════════════════════════════

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.db")

# ════════════════════════════════════════════════════════
#  新聞來源
# ════════════════════════════════════════════════════════

NEWS_SOURCES = [
    {
        "name":     "中央社－財經",
        "url":      "https://feeds.feedburner.com/rsscna/finance",
        "category": "財經",
    },
    {
        "name":     "自由時報－財經",
        "url":      "https://news.ltn.com.tw/rss/business.xml",
        "category": "財經",
    },
    {
        "name":     "中央社－國際",
        "url":      "https://feeds.feedburner.com/rsscna/intworld",
        "category": "國際",
    },
    {
        "name":     "自由時報－國際",
        "url":      "https://news.ltn.com.tw/rss/world.xml",
        "category": "國際",
    },
]

BREAKING_KEYWORDS = [
    "緊急", "重大", "停牌", "下市", "暫停交易", "Fed", "升息", "降息",
    "央行", "地震", "戰爭", "制裁", "爆發", "倒閉", "破產", "財報",
]

