import re
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd

import state
from config import TW


# ════════════════════════════════════════════════════════
#  股票清單快取
# ════════════════════════════════════════════════════════


def get_stock_list() -> pd.DataFrame:
    today = date.today()
    if state._stock_list_cache is not None and state._stock_list_date == today:
        return state._stock_list_cache

    records = []
    for exchange, label in [("TWSE", "上市"), ("TPEx", "上櫃")]:
        try:
            resp = state.stock.intraday.tickers(type="EQUITY", exchange=exchange)
            for item in resp.get("data", []):
                code = item.get("symbol", "")
                if re.match(r"^\d{4}$", code):
                    records.append({"symbol": code, "name": item.get("name", "")})
        except Exception as e:
            print(f"[WARN] 無法取得{label}清單：{e}")

    if not records:
        if state._stock_list_cache is not None:
            print("[WARN] 股票清單更新失敗，沿用前次快取")
            return state._stock_list_cache
        return pd.DataFrame(columns=["symbol", "name"])

    result = pd.DataFrame(records)
    state._stock_list_cache = result
    state._stock_list_date  = today
    print(f"[INFO] 股票清單已更新，共 {len(result)} 筆")
    return result


# ════════════════════════════════════════════════════════
#  指數清單快取
# ════════════════════════════════════════════════════════


def get_index_list() -> pd.DataFrame:
    today = date.today()
    if state._index_list_cache is not None and state._index_list_date == today:
        return state._index_list_cache

    records = []
    for exchange in ["TWSE", "TPEx"]:
        try:
            resp = state.stock.intraday.tickers(type="INDEX", exchange=exchange)
            for item in resp.get("data", []):
                records.append({"symbol": item["symbol"], "name": item.get("name", "")})
        except Exception as e:
            print(f"[WARN] 無法取得指數清單（{exchange}）：{e}")

    if not records:
        if state._index_list_cache is not None:
            print("[WARN] 指數清單更新失敗，沿用前次快取")
            return state._index_list_cache
        return pd.DataFrame(columns=["symbol", "name"])

    result = pd.DataFrame(records).drop_duplicates("symbol").reset_index(drop=True)
    state._index_list_cache = result
    state._index_list_date  = today
    print(f"[INFO] 指數清單已更新，共 {len(result)} 筆")
    return result


def _is_index(symbol: str) -> bool:
    idx = get_index_list()
    return symbol.upper() in idx["symbol"].str.upper().values


# ════════════════════════════════════════════════════════
#  產業類別快取
# ════════════════════════════════════════════════════════


SECTOR_CODE_MAP = {
    "00": "ETF",
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業",
    "04": "紡織纖維", "05": "電機機械", "06": "電器電纜",
    "08": "玻璃陶瓷", "09": "造紙工業", "10": "鋼鐵工業",
    "11": "橡膠工業", "12": "汽車工業", "14": "建材營造業",
    "15": "航運業",   "16": "觀光餐旅", "17": "金融保險業",
    "18": "貿易百貨業", "20": "其他業", "21": "化學工業",
    "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業",
    "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業",
    "31": "其他電子業", "32": "文化創意業", "33": "農業科技業",
    "35": "綠能環保", "36": "數位雲端", "37": "運動休閒",
    "38": "居家生活", "91": "存託憑證",
}


def get_sector_data() -> dict[str, list[dict]]:
    today = date.today()
    if state._sector_cache is not None and state._sector_cache_date == today:
        return state._sector_cache

    records = []
    for exchange, market_label in [("TWSE", "上市"), ("TPEx", "上櫃")]:
        try:
            resp = state.stock.intraday.tickers(type="EQUITY", exchange=exchange)
            for item in resp.get("data", []):
                code = item.get("symbol", "")
                if re.match(r"^\d{4,6}$", code):
                    sector_code = str(item.get("industry", "")).strip()
                    records.append({
                        "symbol": code,
                        "name": item.get("name", ""),
                        "sector": SECTOR_CODE_MAP.get(sector_code, "其他"),
                        "market": market_label,
                    })
        except Exception as e:
            print(f"[WARN] 無法取得{market_label}產業分類：{e}")

    if not records:
        if state._sector_cache is not None:
            print("[WARN] 產業分類更新失敗，沿用前次快取")
            return state._sector_cache
        return {}

    result: dict[str, list[dict]] = {}
    for r in records:
        result.setdefault(r["sector"], []).append({
            "symbol": r["symbol"],
            "name": r["name"],
            "market": r["market"],
        })

    for sector in result:
        result[sector].sort(key=lambda x: x["symbol"])

    state._sector_cache = result
    state._sector_cache_date = today
    total = sum(len(v) for v in result.values())
    print(f"[INFO] 產業分類已更新，共 {len(result)} 個產業、{total} 筆")
    return result


# ════════════════════════════════════════════════════════
#  股票 / 指數報價
# ════════════════════════════════════════════════════════


def _get_index_quote(symbol: str) -> dict:
    sym  = symbol.upper()
    idx  = get_index_list()
    row  = idx[idx["symbol"].str.upper() == sym]
    fallback_name = row.iloc[0]["name"] if not row.empty else sym

    data = state.stock.intraday.quote(symbol=sym)
    return {
        "symbol":         sym,
        "name":           data.get("name", fallback_name),
        "price":          data["closePrice"],
        "change":         data["change"],
        "change_percent": data["changePercent"],
        "volume":         None,
        "value":          None,
        "is_index":       True,
    }


def get_stock_info(symbol: str) -> dict:
    """查詢個股或指數即時報價。"""
    sym = symbol.upper()

    if _is_index(sym):
        return _get_index_quote(sym)

    data = state.stock.intraday.quote(symbol=sym)
    return {
        "symbol":         sym,
        "name":           data["name"],
        "price":          data["lastTrade"]["price"],
        "change":         data["change"],
        "change_percent": data["changePercent"],
        "volume":         (data["total"]["tradeVolume"] / 1000
                           if data["market"] == "ESB"
                           else data["total"]["tradeVolume"]),
        "value":          data["total"]["tradeValue"],
        "is_index":       False,
    }


def _tokenize(keyword: str) -> list[str]:
    tokens = []
    for part in keyword.split():
        if len(part) > 2 and all(unicodedata.east_asian_width(c) in ('W', 'F') for c in part):
            tokens.extend(part[i:i+2] for i in range(0, len(part), 2))
        else:
            tokens.append(part)
    return tokens


def search_by_name(keyword: str) -> pd.DataFrame:
    tokens = _tokenize(keyword)

    def matches(name: str) -> bool:
        return all(t in name for t in tokens)

    stock_df = get_stock_list()
    stock_matches = stock_df[stock_df["name"].apply(matches)].copy()
    idx = get_index_list()
    index_matches = idx[idx["name"].apply(matches)].copy()
    if not index_matches.empty:
        stock_matches = pd.concat([index_matches, stock_matches], ignore_index=True)
    return stock_matches.reset_index(drop=True)


def calculate_fee(price: float, shares: int) -> int:
    """手續費：0.1425%，最低 20 元，四捨五入。"""
    return max(round(price * shares * 0.001425), 20)


def calculate_tax(price: float, shares: int, is_etf: bool, is_daytrade: bool) -> int:
    """證交稅（賣出才有）：去尾法，最低 1 元。
    一般股票 0.3%、ETF 0.1%；現股當沖各減半。
    """
    rate = 0.001 if is_etf else 0.003
    if is_daytrade:
        rate /= 2
    return max(int(price * shares * rate), 1)


def format_value(val: float) -> str:
    if val / 10_000 > 10_000:
        return f'{val / 100_000_000:.2f}億'
    return f'{val / 10_000:.2f}萬'


def format_stock_message(info: dict) -> str:
    sym = info["symbol"]

    if info.get("is_index"):
        change    = info["change"]
        change_pct = info["change_percent"]
        arrow     = "🔺" if change >= 0 else "🔻"
        return (
            f'📊 **{info["name"]}（{sym}）**\n'
            f'最新指數：{info["price"]}\n'
            f'漲跌：{arrow} {change:+.2f}\n'
            f'漲跌幅：{arrow} {change_pct} %\n'
            f'即時查詢：https://www.fugle.tw/ai/{sym}\n'
        )

    val     = info["value"]
    val_str = format_value(val)
    msg = (
        f'📊 **{info["name"]}（{sym}）**\n'
        f'最新價格：{info["price"]} 元\n'
        f'最新漲跌幅：{info["change_percent"]} %\n'
        f'累計成交量：{info["volume"]} 張\n'
        f'累計成交額：{val_str}\n'
        f'個股查詢：https://www.fugle.tw/ai/{sym}\n'
    )
    msg += f'相關報告：https://blog.fugle.tw/tag/{sym}'
    return msg


# ════════════════════════════════════════════════════════
#  歷史 K 線（Fugle REST API）
# ════════════════════════════════════════════════════════


def get_candles(symbol: str, days: int = 65) -> pd.DataFrame:
    """取得近 N 個交易日的日 K 資料。"""
    end_date   = date.today()
    start_date = end_date - timedelta(days=days * 2)
    data = state.stock.historical.candles(
        symbol=symbol.upper(),
        from_=start_date.strftime("%Y-%m-%d"),
        to=end_date.strftime("%Y-%m-%d"),
        fields="open,high,low,close,volume",
    )
    df = pd.DataFrame(data["data"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    if "volume" not in df.columns:
        df["volume"] = 0
    df["volume"] = df["volume"].fillna(0)

    return df.tail(days)


# ════════════════════════════════════════════════════════
#  盤中時間判斷
# ════════════════════════════════════════════════════════


def is_trading_hours() -> bool:
    now        = datetime.now(TW)
    open_time  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    close_time = now.replace(hour=13, minute=30, second=0, microsecond=0)
    return now.weekday() < 5 and open_time <= now <= close_time


