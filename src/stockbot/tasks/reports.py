import asyncio
import logging
from datetime import datetime, timedelta

from discord.ext import tasks

from .. import state
from ..config import ALERT_CHANNEL_ID, TW
from ..data import get_candles, get_stock_info
from ..db import get_meta, set_meta
from ..display import format_table

logger = logging.getLogger(__name__)

WEEKLY_META_KEY = "weekly_report_pushed"


def weekly_row(sym: str, now: datetime | None = None) -> dict | None:
    """（同步，於 executor 執行）計算單一代號「本週一至今」的績效列。
    日 K 若尚未包含今日，以即時報價的開高低收補上（需報價日期為今日，避免休市日誤補）。
    """
    today = (now or datetime.now(TW)).date()
    monday = today - timedelta(days=today.weekday())

    info = get_stock_info(sym)
    bars: list[dict] = []
    try:
        df = get_candles(sym, days=10)
        df = df[df["date"].dt.date >= monday]
        bars = [
            {"date": r["date"].date(), "open": r["open"], "high": r["high"],
             "low": r["low"], "close": r["close"]}
            for r in df.to_dict("records")
        ]
    except Exception as e:
        logger.warning("週報 %s 日K取得失敗：%s", sym, e)

    has_today = any(b["date"] == today for b in bars)
    if (not has_today and info.get("date") == today.isoformat()
            and None not in (info.get("open"), info.get("high"), info.get("low"))):
        bars.append({"date": today, "open": info["open"], "high": info["high"],
                     "low": info["low"], "close": info["price"]})

    if not bars:
        return None
    bars.sort(key=lambda b: b["date"])
    week_open = bars[0]["open"]
    week_close = bars[-1]["close"]
    pct = (week_close - week_open) / week_open * 100 if week_open else 0.0
    return {
        "代號": sym,
        "名稱": info["name"],
        "週漲跌%": f"{pct:+.2f}",
        "週高": f"{max(b['high'] for b in bars):.2f}",
        "週低": f"{min(b['low'] for b in bars):.2f}",
        "收盤": f"{week_close:.2f}",
    }


@tasks.loop(minutes=1)
async def weekly_report_push():
    """每週五 14:00 推播自選股本週績效週報；當日 14:00 後皆可補發，每 ISO 週一次。"""
    now = datetime.now(TW)
    if now.weekday() != 4 or now.hour < 14:
        return
    iso = now.isocalendar()
    week_key = f"{iso[0]}-W{iso[1]:02d}"
    if get_meta(WEEKLY_META_KEY) == week_key:
        return

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        logger.warning("找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    # 去重後每檔只計算一次，並放到 executor 避免阻塞 event loop
    loop = asyncio.get_running_loop()
    all_symbols = {sym for symbols in state.watchlist.values() for sym in symbols}
    rows_by_sym: dict[str, dict] = {}
    for sym in all_symbols:
        try:
            row = await loop.run_in_executor(None, weekly_row, sym)
        except Exception as e:
            logger.warning("週報 %s 計算失敗：%s", sym, e)
            continue
        if row:
            rows_by_sym[sym] = row

    for uid, symbols in state.watchlist.items():
        rows = [rows_by_sym[s] for s in symbols if s in rows_by_sym]
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

    set_meta(WEEKLY_META_KEY, week_key)
