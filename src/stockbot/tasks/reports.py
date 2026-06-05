import logging
from datetime import datetime

from discord.ext import tasks

from .. import state
from ..config import ALERT_CHANNEL_ID, TW
from ..data import get_candles, get_stock_info
from ..display import format_table

logger = logging.getLogger(__name__)


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
                df = get_candles(sym, days=7)
                if len(df) < 2:
                    continue
                week_open = df.iloc[0]["open"]
                week_close = df.iloc[-1]["close"]
                week_high = df["high"].max()
                week_low = df["low"].min()
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
