from datetime import datetime

from discord.ext import tasks

from .. import state
from ..config import NEWS_CHANNEL_ID, TW
from ..data import is_trading_hours
from ..db import get_meta, save_pushed_news, set_meta
from ..market_clock import in_time_window
from ..market_types import NewsItem
from ..news import build_news_embed, fetch_latest_news, is_breaking_news, pick_latest_news

DIGEST_SIZE = 5          # 晨報／收盤總整理的新聞則數
DIGEST_GRACE_MIN = 30    # 錯過整點（重啟、卡頓）時允許補發的分鐘數


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


async def _scheduled_news_push(hour: int, minute: int, meta_key: str, label: str):
    """推播最新 DIGEST_SIZE 則財經新聞（不排除已推播過的），時間窗內可補發；
    發送後才把今日日期寫入 bot_meta，重啟不會重發也不會漏發。"""
    now = datetime.now(TW)
    if now.weekday() >= 5 or not in_time_window(now, hour, minute, DIGEST_GRACE_MIN):
        return
    today = now.date().isoformat()
    if get_meta(meta_key) == today:
        return
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return

    news_list = await fetch_latest_news(max_per_source=DIGEST_SIZE)
    picked = pick_latest_news(news_list, "財經", DIGEST_SIZE)
    now_str = now.strftime("%Y/%m/%d %H:%M")
    if not picked:
        await channel.send(f"{label} ｜ {now_str}\n目前無法取得財經新聞。")
    else:
        await channel.send(f"{label} ｜ {now_str}　最新 {len(picked)} 則財經新聞")
        for news in picked:
            await channel.send(embed=build_news_embed(news))
            if news["id"] not in state.pushed_news_ids:
                state.pushed_news_ids.add(news["id"])
                save_pushed_news(news["id"])
    set_meta(meta_key, today)


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
    await _scheduled_news_push(9, 0, "market_open_pushed", "🔔 **開盤晨報**")


@tasks.loop(minutes=1)
async def market_close_push():
    await _scheduled_news_push(13, 30, "market_close_pushed", "🔔 **收盤總整理**")


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
