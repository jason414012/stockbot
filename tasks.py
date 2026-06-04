import asyncio
import logging
from datetime import datetime

from discord.ext import tasks

logger = logging.getLogger(__name__)

import state
from config import TW, NEWS_CHANNEL_ID, ALERT_CHANNEL_ID, VOLATILITY_THRESHOLD_PCT
from db import save_pushed_news, list_all_alerts, delete_alert
from data import get_stock_info, get_candles, is_trading_hours
from news import fetch_latest_news, is_breaking_news, build_news_embed
from display import format_table


async def _get_stock_info_async(symbol: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_stock_info, symbol)


# ════════════════════════════════════════════════════════
#  共用 helpers
# ════════════════════════════════════════════════════════


async def _push_news_to_channel(channel, new_items: list[dict], label: str):
    if not new_items:
        return
    now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
    await channel.send(f'📡 **財經新聞快報** ｜ {now_str}　{label}')
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


# ── ① 即時推播：每 1 分鐘 ──────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def auto_news_push():
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return
    news_list = await fetch_latest_news(max_per_source=3)
    new_items = [n for n in news_list if n["id"] not in state.pushed_news_ids]
    await _push_news_to_channel(channel, new_items, "（即時推播）")


# ── ② 開盤推播：09:00 ──────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def market_open_push():
    await _scheduled_news_push(9, 0, "market_open_pushed_date", "🔔 **開盤晨報**")


# ── ③ 收盤推播：13:30 ──────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def market_close_push():
    await _scheduled_news_push(13, 30, "market_close_pushed_date", "🔔 **收盤總整理**")


# ── ④ 重大新聞即時掃描：每 5 分鐘（盤中）──────────────────────────────────────

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
        await channel.send(f'🚨 **【重大新聞速報】** ｜ {now_str}')
        embed = build_news_embed(news)
        await channel.send(embed=embed)
        state.pushed_news_ids.add(news["id"])
        save_pushed_news(news["id"])


# ── ⑤ 價格警示掃描：每 2 分鐘（盤中）─────────────────────────────────────────

@tasks.loop(minutes=2)
async def price_alert_scan():
    if not is_trading_hours():
        return

    alerts = list_all_alerts()
    if not alerts:
        return

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        logger.warning("找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    symbols = list({a["symbol"] for a in alerts})
    prices: dict[str, float] = {}
    for sym in symbols:
        try:
            info = await _get_stock_info_async(sym)
            prices[sym] = info["price"]
        except Exception:
            pass

    for alert in alerts:
        sym   = alert["symbol"]
        price = prices.get(sym)
        if price is None:
            continue
        triggered = (
            (alert["direction"] == "above" and price >= alert["target"]) or
            (alert["direction"] == "below" and price <= alert["target"])
        )
        if not triggered:
            continue

        delete_alert(alert["id"])

        try:
            direction_str = "突破" if alert["direction"] == "above" else "跌破"
            now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
            await alert_channel.send(
                f'🔔 <@{alert["user_id"]}> **價格警示觸發！** ｜ {now_str}\n'
                f'`{sym}` 已{direction_str}目標價 **{alert["target"]} 元**\n'
                f'目前價格：**{price} 元**'
            )
        except Exception as e:
            logger.warning("頻道價格警示發送失敗（uid=%s）：%s", alert['user_id'], e)


# ── ⑥ 自選股漲跌幅警示：每 5 分鐘（盤中）────────────────────────────────────

@tasks.loop(minutes=5)
async def watchlist_volatility_alert():
    if not is_trading_hours():
        return

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        logger.warning("找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    all_symbols = list({sym for symbols in state.watchlist.values() for sym in symbols})
    prices_info: dict[str, dict] = {}
    for sym in all_symbols:
        try:
            prices_info[sym] = await _get_stock_info_async(sym)
        except Exception:
            pass

    for uid, symbols in state.watchlist.items():
        if not symbols:
            continue
        alerts = []
        for sym in symbols:
            info = prices_info.get(sym)
            if info is None:
                continue
            try:
                pct = float(info["change_percent"])
                if abs(pct) >= VOLATILITY_THRESHOLD_PCT:
                    direction = "🔺" if pct > 0 else "🔻"
                    alerts.append(
                        f'{direction} **{info["name"]}（{sym}）** '
                        f'漲跌幅 `{pct:+.2f}%`，現價 `{info["price"]} 元`'
                    )
            except Exception:
                pass

        if not alerts:
            continue
        try:
            now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
            msg = (
                f'⚠️ <@{uid}> **自選股大幅波動警示** ｜ {now_str}\n'
                + "\n".join(alerts)
            )
            await alert_channel.send(msg)
        except Exception as e:
            logger.warning("自選股波動頻道通知失敗（uid=%s）：%s", uid, e)


# ── ⑦ 週報推播：每週五 14:00 ──────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def weekly_report_push():
    now = datetime.now(TW)
    if not (now.weekday() == 4 and now.hour == 14 and now.minute == 0):
        return
    week_no = now.isocalendar()[1]
    if state.weekly_report_pushed_week == week_no:
        return
    state.weekly_report_pushed_week = week_no

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        logger.warning("找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    for uid, symbols in state.watchlist.items():
        if not symbols:
            continue
        rows = []
        for sym in symbols:
            try:
                df   = get_candles(sym, days=7)
                if len(df) < 2:
                    continue
                week_open  = df.iloc[0]["open"]
                week_close = df.iloc[-1]["close"]
                week_high  = df["high"].max()
                week_low   = df["low"].min()
                pct = round((week_close - week_open) / week_open * 100, 2)
                try:
                    sym_name = get_stock_info(sym)["name"]
                except Exception:
                    sym_name = sym
                rows.append({
                    "代號": sym,
                    "名稱": sym_name,
                    "週漲跌%": f"{pct:+.2f}",
                    "週高": week_high,
                    "週低": week_low,
                    "收盤": week_close,
                })
            except Exception:
                pass
        if not rows:
            continue
        try:
            table = format_table(rows)
            msg = (
                f"📅 <@{uid}> **本週自選股績效週報** ｜ {now.strftime('%Y/%m/%d')}\n"
                f"```{table}```"
            )
            await alert_channel.send(msg)
        except Exception as e:
            logger.warning("週報頻道通知失敗（uid=%s）：%s", uid, e)


# ── 統一 before_loop hook ──────────────────────────────────────────────────────

async def _wait_ready():
    await state.bot.wait_until_ready()

auto_news_push.before_loop(_wait_ready)
market_open_push.before_loop(_wait_ready)
market_close_push.before_loop(_wait_ready)
breaking_news_scan.before_loop(_wait_ready)
price_alert_scan.before_loop(_wait_ready)
watchlist_volatility_alert.before_loop(_wait_ready)
weekly_report_push.before_loop(_wait_ready)
