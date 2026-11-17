from .market_types import QuoteInfo


def format_value(val: float) -> str:
    if val / 10_000 > 10_000:
        return f"{val / 100_000_000:.2f}億"
    return f"{val / 10_000:.2f}萬"


def format_volume_lots(info: QuoteInfo) -> str:
    """個股當日累計成交量文字（如「12,345 張」）；指數或無資料時回傳空字串。"""
    vol = info.get("volume")
    if info.get("is_index") or vol is None:
        return ""
    return f"{int(vol):,} 張"


def format_bid_ask(info: QuoteInfo) -> str:
    """內外盤文字，例如「🔻 外盤 5,971 / 內盤 10,874（賣方強）」。
    外盤佔內外盤合計 ≥ 55% 為買方強、≤ 45% 為賣方強，其餘為多空均衡。
    指數或無資料時回傳空字串。
    """
    ask, bid = info.get("vol_at_ask"), info.get("vol_at_bid")
    if info.get("is_index") or ask is None or bid is None or ask + bid <= 0:
        return ""
    ratio = ask / (ask + bid)
    if ratio >= 0.55:
        icon, label = "🔺", "買方強"
    elif ratio <= 0.45:
        icon, label = "🔻", "賣方強"
    else:
        icon, label = "⚖️", "多空均衡"
    return f"{icon} 外盤 {int(ask):,} / 內盤 {int(bid):,}（{label}）"


def format_stock_message(info: QuoteInfo) -> str:
    sym = info["symbol"]

    if info.get("is_index"):
        change = info["change"]
        change_pct = info["change_percent"]
        arrow = "🔺" if change >= 0 else "🔻"
        return (
            f'📊 **{info["name"]}（{sym}）**\n'
            f'最新指數：{info["price"]}\n'
            f"漲跌：{arrow} {change:+.2f}\n"
            f"漲跌幅：{arrow} {change_pct} %\n"
            f"即時查詢：https://www.fugle.tw/ai/{sym}\n"
        )

    val = info["value"]
    val_str = format_value(val)
    msg = (
        f'📊 **{info["name"]}（{sym}）**\n'
        f'最新價格：{info["price"]} 元\n'
        f'最新漲跌幅：{info["change_percent"]} %\n'
        f'累計成交量：{info["volume"]} 張\n'
        f"累計成交額：{val_str}\n"
        f"個股查詢：https://www.fugle.tw/ai/{sym}\n"
    )
    msg += f"相關報告：https://blog.fugle.tw/tag/{sym}"
    return msg
