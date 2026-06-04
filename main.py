import logging

import config
import state
import db
import tasks
import commands  # noqa: F401 — import 即註冊所有 @bot.command 裝飾器

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════
#  初始化
# ════════════════════════════════════════════════════════

db.init_db()
state.watchlist = db.load_watchlist()
state.pushed_news_ids = db.load_pushed_news(days=3)


# ════════════════════════════════════════════════════════
#  Bot 就緒事件：啟動排程任務
# ════════════════════════════════════════════════════════

@state.bot.event
async def on_ready():
    logger.info("Logged in as %s", state.bot.user.name)
    synced = await state.bot.tree.sync()
    logger.info("Slash commands synced: %d 個", len(synced))
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
    logger.info("所有自動推播任務已啟動")


# ════════════════════════════════════════════════════════
#  啟動
# ════════════════════════════════════════════════════════

import asyncio

async def _run():
    async with state.bot:
        await state.bot.start(config.DISCORD_TOKEN)

try:
    asyncio.run(_run())
except KeyboardInterrupt:
    pass
