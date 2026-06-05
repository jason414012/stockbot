import logging

from . import config
from . import state
from . import db
from . import tasks
from . import commands  # noqa: F401 — import 即註冊所有 @bot.command 裝飾器

logger = logging.getLogger(__name__)

def _initialize():
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
    for t in tasks.TASK_LOOPS:
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

def main():
    _initialize()
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
