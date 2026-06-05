from datetime import datetime

from discord.ext import tasks

from .. import state
from ..config import NEWS_CHANNEL_ID, TW
from ..data import is_trading_hours
from ..db import save_pushed_news
from ..market_types import NewsItem
from ..news import build_news_embed, fetch_latest_news, is_breaking_news


async def _push_news_to_channel(channel, new_items: list[NewsItem], label: str):
    if not new_items:
        return
    now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
    await channel.send(f"📡 **財經新聞快報** ｜ {now_str}　{label}")
    for news in new_items:
        embed = build_news_embed(news)
        await channel.send(embed=embed)
        state.pushed_news_ids.add(news["id"])
        save_pushed_news(news["id"])


async def _scheduled_news_push(hour: int, minute: int, state_attr: str, label: str):
    now = datetime.now(TW)
    if now.weekday() >= 5 or not (now.hour == hour and now.minute == minute):
        return
    if getattr(state, state_attr) == now.date():
        return
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return
    news_list = await fetch_latest_news(max_per_source=5)
    new_items = [n for n in news_list if n["id"] not in state.pushed_news_ids]
    await _push_news_to_channel(channel, new_items, label)
    setattr(state, state_attr, now.date())


@tasks.loop(minutes=1)
async def auto_news_push():
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return
    news_list = await fetch_latest_news(max_per_source=3)
    new_items = [n for n in news_list if n["id"] not in state.pushed_news_ids]
    await _push_news_to_channel(channel, new_items, "（即時推播）")


@tasks.loop(minutes=1)
async def market_open_push():
    await _scheduled_news_push(9, 0, "market_open_pushed_date", "🔔 **開盤晨報**")


@tasks.loop(minutes=1)
async def market_close_push():
    await _scheduled_news_push(13, 30, "market_close_pushed_date", "🔔 **收盤總整理**")


@tasks.loop(minutes=5)
async def breaking_news_scan():
    if not is_trading_hours():
        return
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return

    today = datetime.now(TW).date()
    if state.breaking_last_reset_date != today:
        state.breaking_checked_ids.clear()
        state.breaking_last_reset_date = today

    news_list = await fetch_latest_news(max_per_source=5)
    for news in news_list:
        if news["id"] in state.breaking_checked_ids:
            continue
        state.breaking_checked_ids.add(news["id"])

        if not is_breaking_news(news["title"]):
            continue

        now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
        await channel.send(f"🚨 **【重大新聞速報】** ｜ {now_str}")
        embed = build_news_embed(news)
        await channel.send(embed=embed)
        state.pushed_news_ids.add(news["id"])
        save_pushed_news(news["id"])
