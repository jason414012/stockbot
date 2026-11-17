import asyncio
import calendar
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
                parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                all_news.append({
                    "id":        news_id,
                    "title":     entry.get("title", "（無標題）").strip(),
                    "link":      entry.get("link", ""),
                    "source":    src["name"],
                    "category":  src.get("category", ""),
                    "published": entry.get("published", ""),
                    "ts":        calendar.timegm(parsed) if parsed else 0,
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


def pick_latest_news(news_list: list[NewsItem], category: str, size: int) -> list[NewsItem]:
    """取指定類別、依發布時間由新到舊的前 size 則（晨報／收盤總整理用）。"""
    picked = [n for n in news_list if n.get("category") == category]
    picked.sort(key=lambda n: n.get("ts", 0), reverse=True)
    return picked[:size]


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
