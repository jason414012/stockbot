import asyncio
import logging

import discord
import feedparser

from .config import NEWS_SOURCES, BREAKING_KEYWORDS
from .market_types import NewsItem

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════
#  新聞抓取
# ════════════════════════════════════════════════════════


def _fetch_news_sync(max_per_source: int = 5) -> list[NewsItem]:
    all_news = []
    for src in NEWS_SOURCES:
        try:
            feed = feedparser.parse(src["url"])
            for entry in feed.entries[:max_per_source]:
                news_id = entry.get("id") or entry.get("link", "")
                all_news.append({
                    "id":        news_id,
                    "title":     entry.get("title", "（無標題）").strip(),
                    "link":      entry.get("link", ""),
                    "source":    src["name"],
                    "category":  src.get("category", ""),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            logger.warning("抓取 %s RSS 失敗：%s", src['name'], e)
    return all_news


async def fetch_latest_news(max_per_source: int = 5) -> list[NewsItem]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_news_sync, max_per_source)


# ════════════════════════════════════════════════════════
#  重大新聞判斷
# ════════════════════════════════════════════════════════


def is_breaking_news(title: str) -> bool:
    return any(kw in title for kw in BREAKING_KEYWORDS)


def build_news_embed(news: NewsItem) -> discord.Embed:
    category_tag = f'【{news["category"]}】' if news.get("category") else ""

    embed = discord.Embed(
        title=news["title"][:256],
        url=news["link"],
        color=0x3498db,
    )
    embed.set_author(name=f'📰 {category_tag}{news["source"]}')
    if news["published"]:
        embed.set_footer(text=f'發布時間：{news["published"]}')
    return embed
