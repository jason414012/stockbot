import asyncio
from datetime import datetime

from discord.ext import tasks

import state
from config import TW, NEWS_CHANNEL_ID, ALERT_CHANNEL_ID
from db import _save_pushed_news, _db_all_alerts, _db_delete_alert_by_id
from data import get_stock_info, get_candles, is_trading_hours
from news import fetch_latest_news, is_breaking_news, build_news_embed
from commands import _format_table


async def _get_stock_info_async(symbol: str) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_stock_info, symbol)

# ════════════════════════════════════════════════════════
#  定時推播任務
# ════════════════════════════════════════════════════════


async def _push_news_to_channel(channel, new_items: list[dict], label: str):
    if not new_items:
        return
    now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
    await channel.send(f'📡 **財經新聞快報** ｜ {now_str}　{label}')
    for news in new_items:
        embed = build_news_embed(news)
        await channel.send(embed=embed)
        state._pushed_news_ids.add(news["id"])
        _save_pushed_news(news["id"])


# ── ① 即時推播：每 1 分鐘 ──────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def auto_news_push():
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return
    news_list = await fetch_latest_news(max_per_source=3)
    new_items = [n for n in news_list if n["id"] not in state._pushed_news_ids]
    await _push_news_to_channel(channel, new_items, "（即時推播）")


@auto_news_push.before_loop
async def before_auto_news():
    await state.bot.wait_until_ready()


# ── ② 開盤推播：09:00 ──────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def market_open_push():
    now = datetime.now(TW)
    if now.weekday() >= 5 or not (now.hour == 9 and now.minute == 0):
        return
    if state._market_open_pushed_date == now.date():
        return
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return
    news_list = await fetch_latest_news(max_per_source=5)
    new_items = [n for n in news_list if n["id"] not in state._pushed_news_ids]
    await _push_news_to_channel(channel, new_items, "🔔 **開盤晨報**")
    state._market_open_pushed_date = now.date()


@market_open_push.before_loop
async def before_open_push():
    await state.bot.wait_until_ready()


# ── ③ 收盤推播：13:30 ──────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def market_close_push():
    now = datetime.now(TW)
    if now.weekday() >= 5 or not (now.hour == 13 and now.minute == 30):
        return
    if state._market_close_pushed_date == now.date():
        return
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return
    news_list = await fetch_latest_news(max_per_source=5)
    new_items = [n for n in news_list if n["id"] not in state._pushed_news_ids]
    await _push_news_to_channel(channel, new_items, "🔔 **收盤總整理**")
    state._market_close_pushed_date = now.date()


@market_close_push.before_loop
async def before_close_push():
    await state.bot.wait_until_ready()


# ── ④ 重大新聞即時掃描：每 5 分鐘（盤中）──────────────────────────────────────

@tasks.loop(minutes=5)
async def breaking_news_scan():
    if not is_trading_hours():
        return
    channel = state.bot.get_channel(NEWS_CHANNEL_ID)
    if channel is None:
        return

    # 防止 _breaking_checked_ids 無限增長（每日重置）
    today = datetime.now(TW).date()
    if not hasattr(breaking_news_scan, "_last_reset") or breaking_news_scan._last_reset != today:
        state._breaking_checked_ids.clear()
        breaking_news_scan._last_reset = today

    news_list = await fetch_latest_news(max_per_source=5)
    for news in news_list:
        if news["id"] in state._breaking_checked_ids:
            continue
        state._breaking_checked_ids.add(news["id"])

        if not is_breaking_news(news["title"]):
            continue

        now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
        await channel.send(f'🚨 **【重大新聞速報】** ｜ {now_str}')
        embed = build_news_embed(news)
        await channel.send(embed=embed)
        state._pushed_news_ids.add(news["id"])
        _save_pushed_news(news["id"])


@breaking_news_scan.before_loop
async def before_breaking_scan():
    await state.bot.wait_until_ready()


# ── ⑤ 價格警示掃描：每 2 分鐘（盤中）─────────────────────────────────────────

@tasks.loop(minutes=2)
async def price_alert_scan():
    """盤中每 2 分鐘掃描所有使用者的價格警示。"""
    if not is_trading_hours():
        return

    alerts = _db_all_alerts()
    if not alerts:
        return

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        print("[WARN] 找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
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

        _db_delete_alert_by_id(alert["id"])

        try:
            direction_str = "突破" if alert["direction"] == "above" else "跌破"
            now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
            await alert_channel.send(
                f'🔔 <@{alert["user_id"]}> **價格警示觸發！** ｜ {now_str}\n'
                f'`{sym}` 已{direction_str}目標價 **{alert["target"]} 元**\n'
                f'目前價格：**{price} 元**'
            )
        except Exception as e:
            print(f"[WARN] 頻道價格警示發送失敗（uid={alert['user_id']}）：{e}")


@price_alert_scan.before_loop
async def before_alert_scan():
    await state.bot.wait_until_ready()


# ── ⑥ 自選股漲跌幅警示：每 5 分鐘（盤中）────────────────────────────────────

@tasks.loop(minutes=5)
async def watchlist_volatility_alert():
    """盤中每 5 分鐘掃描自選股，漲跌幅超過 ±3% 時通知使用者。"""
    if not is_trading_hours():
        return

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        print("[WARN] 找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    # 去重：先收集所有 symbol，統一查價一次
    all_symbols = list({sym for symbols in state._watchlist.values() for sym in symbols})
    prices_info: dict[str, dict] = {}
    for sym in all_symbols:
        try:
            prices_info[sym] = await _get_stock_info_async(sym)
        except Exception:
            pass

    for uid, symbols in state._watchlist.items():
        if not symbols:
            continue
        alerts = []
        for sym in symbols:
            info = prices_info.get(sym)
            if info is None:
                continue
            try:
                pct = float(info["change_percent"])
                if abs(pct) >= 3:
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
            print(f"[WARN] 自選股波動頻道通知失敗（uid={uid}）：{e}")


@watchlist_volatility_alert.before_loop
async def before_vol_alert():
    await state.bot.wait_until_ready()


# ── ⑦ 週報推播：每週五 14:00 ──────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def weekly_report_push():
    """每週五 14:00 推播各使用者自選股本週績效週報。"""
    now = datetime.now(TW)
    if not (now.weekday() == 4 and now.hour == 14 and now.minute == 0):
        return
    week_no = now.isocalendar()[1]
    if state._weekly_report_pushed_week == week_no:
        return
    state._weekly_report_pushed_week = week_no

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        print("[WARN] 找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    for uid, symbols in state._watchlist.items():
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
            table = _format_table(rows)
            msg = (
                f"📅 <@{uid}> **本週自選股績效週報** ｜ {now.strftime('%Y/%m/%d')}\n"
                f"```{table}```"
            )
            await alert_channel.send(msg)
        except Exception as e:
            print(f"[WARN] 週報頻道通知失敗（uid={uid}）：{e}")


@weekly_report_push.before_loop
async def before_weekly_report():
    await state.bot.wait_until_ready()
