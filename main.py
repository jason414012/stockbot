import config
import state
import db
import tasks
import commands  # noqa: F401 — import 即註冊所有 @bot.command 裝飾器

# ════════════════════════════════════════════════════════
#  初始化
# ════════════════════════════════════════════════════════

db._init_db()
state._watchlist = db._load_watchlist()
state._pushed_news_ids = db._load_pushed_news(days=3)


# ════════════════════════════════════════════════════════
#  Bot 就緒事件：啟動排程任務
# ════════════════════════════════════════════════════════

@state.bot.event
async def on_ready():
    print(f"[INFO] Logged in as {state.bot.user.name}")
    synced = await state.bot.tree.sync()
    print(f"[INFO] Slash commands synced: {len(synced)} 個")
    task_loops = [
        tasks.auto_news_push,
        tasks.market_open_push,
        tasks.market_close_push,
        tasks.breaking_news_scan,
        tasks.price_alert_scan,
        tasks.watchlist_volatility_alert,
        tasks.weekly_report_push,
    ]
    for t in task_loops:
        if not t.is_running():
            t.start()
    print("[INFO] 所有自動推播任務已啟動")


# ════════════════════════════════════════════════════════
#  啟動
# ════════════════════════════════════════════════════════

state.bot.run(config.DISCORD_TOKEN)
