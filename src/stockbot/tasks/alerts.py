import logging
from datetime import datetime

from discord.ext import tasks

from .. import state
from ..config import ALERT_CHANNEL_ID, TW, VOLATILITY_THRESHOLD_PCT
from ..data import is_trading_hours
from ..db import delete_alert, list_all_alerts
from ..domain.alerts import is_price_alert_triggered, is_volatile
from ..market_types import QuoteInfo
from .common import get_stock_info_async

logger = logging.getLogger(__name__)


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
            info = await get_stock_info_async(sym)
            prices[sym] = info["price"]
        except Exception:
            pass

    for alert in alerts:
        sym = alert["symbol"]
        price = prices.get(sym)
        if price is None:
            continue
        try:
            triggered = is_price_alert_triggered(alert["direction"], price, alert["target"])
        except ValueError:
            logger.warning("未知價格警示方向（id=%s）：%s", alert["id"], alert["direction"])
            continue
        if not triggered:
            continue

        delete_alert(alert["id"])

        try:
            direction_str = "突破" if alert["direction"] == "above" else "跌破"
            now_str = datetime.now(TW).strftime("%Y/%m/%d %H:%M")
            await alert_channel.send(
                f'🔔 <@{alert["user_id"]}> **價格警示觸發！** ｜ {now_str}\n'
                f'`{sym}` 已{direction_str}目標價 **{alert["target"]} 元**\n'
                f"目前價格：**{price} 元**"
            )
        except Exception as e:
            logger.warning("頻道價格警示發送失敗（uid=%s）：%s", alert["user_id"], e)


@tasks.loop(minutes=5)
async def watchlist_volatility_alert():
    if not is_trading_hours():
        return

    alert_channel = state.bot.get_channel(ALERT_CHANNEL_ID)
    if alert_channel is None:
        logger.warning("找不到警示頻道，請確認 ALERT_CHANNEL_ID 設定是否正確。")
        return

    all_symbols = list({sym for symbols in state.watchlist.values() for sym in symbols})
    prices_info: dict[str, QuoteInfo] = {}
    for sym in all_symbols:
        try:
            prices_info[sym] = await get_stock_info_async(sym)
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
                if is_volatile(pct, VOLATILITY_THRESHOLD_PCT):
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
                f"⚠️ <@{uid}> **自選股大幅波動警示** ｜ {now_str}\n"
                + "\n".join(alerts)
            )
            await alert_channel.send(msg)
        except Exception as e:
            logger.warning("自選股波動頻道通知失敗（uid=%s）：%s", uid, e)
