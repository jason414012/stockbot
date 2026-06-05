from .market_types import QuoteInfo


def format_value(val: float) -> str:
    if val / 10_000 > 10_000:
        return f"{val / 100_000_000:.2f}億"
    return f"{val / 10_000:.2f}萬"


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
