import logging
import re
from datetime import date, timedelta

import pandas as pd

from . import state
from .market_types import QuoteInfo, SectorStock

logger = logging.getLogger(__name__)


def get_stock_list() -> pd.DataFrame:
    today = date.today()
    if state.stock_list_cache is not None and state.stock_list_date == today:
        return state.stock_list_cache

    records = []
    for exchange, label in [("TWSE", "上市"), ("TPEx", "上櫃")]:
        try:
            resp = state.stock.intraday.tickers(type="EQUITY", exchange=exchange)
            for item in resp.get("data", []):
                code = item.get("symbol", "")
                if re.match(r"^\d{4}$", code):
                    records.append({"symbol": code, "name": item.get("name", "")})
        except Exception as e:
            logger.warning("無法取得%s清單：%s", label, e)

    if not records:
        if state.stock_list_cache is not None:
            logger.warning("股票清單更新失敗，沿用前次快取")
            return state.stock_list_cache
        return pd.DataFrame(columns=["symbol", "name"])

    result = pd.DataFrame(records)
    state.stock_list_cache = result
    state.stock_list_date = today
    logger.info("股票清單已更新，共 %d 筆", len(result))
    return result


def get_index_list() -> pd.DataFrame:
    today = date.today()
    if state.index_list_cache is not None and state.index_list_date == today:
        return state.index_list_cache

    records = []
    for exchange in ["TWSE", "TPEx"]:
        try:
            resp = state.stock.intraday.tickers(type="INDEX", exchange=exchange)
            for item in resp.get("data", []):
                records.append({"symbol": item["symbol"], "name": item.get("name", "")})
        except Exception as e:
            logger.warning("無法取得指數清單（%s）：%s", exchange, e)

    if not records:
        if state.index_list_cache is not None:
            logger.warning("指數清單更新失敗，沿用前次快取")
            return state.index_list_cache
        return pd.DataFrame(columns=["symbol", "name"])

    result = pd.DataFrame(records).drop_duplicates("symbol").reset_index(drop=True)
    state.index_list_cache = result
    state.index_list_date = today
    logger.info("指數清單已更新，共 %d 筆", len(result))
    return result


def _is_index(symbol: str) -> bool:
    idx = get_index_list()
    return symbol.upper() in idx["symbol"].str.upper().values


SECTOR_CODE_MAP = {
    "00": "ETF",
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業",
    "04": "紡織纖維", "05": "電機機械", "06": "電器電纜",
    "08": "玻璃陶瓷", "09": "造紙工業", "10": "鋼鐵工業",
    "11": "橡膠工業", "12": "汽車工業", "14": "建材營造業",
    "15": "航運業", "16": "觀光餐旅", "17": "金融保險業",
    "18": "貿易百貨業", "20": "其他業", "21": "化學工業",
    "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業",
    "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業",
    "31": "其他電子業", "32": "文化創意業", "33": "農業科技業",
    "35": "綠能環保", "36": "數位雲端", "37": "運動休閒",
    "38": "居家生活", "91": "存託憑證",
}


def get_sector_data() -> dict[str, list[SectorStock]]:
    today = date.today()
    if state.sector_cache is not None and state.sector_cache_date == today:
        return state.sector_cache

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
            logger.warning("無法取得%s產業分類：%s", market_label, e)

    if not records:
        if state.sector_cache is not None:
            logger.warning("產業分類更新失敗，沿用前次快取")
            return state.sector_cache
        return {}

    result: dict[str, list[SectorStock]] = {}
    for r in records:
        result.setdefault(r["sector"], []).append({
            "symbol": r["symbol"],
            "name": r["name"],
            "market": r["market"],
        })

    for sector in result:
        result[sector].sort(key=lambda x: x["symbol"])

    state.sector_cache = result
    state.sector_cache_date = today
    total = sum(len(v) for v in result.values())
    logger.info("產業分類已更新，共 %d 個產業、%d 筆", len(result), total)
    return result


def _get_index_quote(symbol: str) -> QuoteInfo:
    sym = symbol.upper()
    idx = get_index_list()
    row = idx[idx["symbol"].str.upper() == sym]
    fallback_name = row.iloc[0]["name"] if not row.empty else sym

    data = state.stock.intraday.quote(symbol=sym)
    return {
        "symbol": sym,
        "name": data.get("name", fallback_name),
        "price": data["closePrice"],
        "change": data["change"],
        "change_percent": data["changePercent"],
        "volume": None,
        "value": None,
        "is_index": True,
    }


def get_stock_info(symbol: str) -> QuoteInfo:
    sym = symbol.upper()

    if _is_index(sym):
        return _get_index_quote(sym)

    data = state.stock.intraday.quote(symbol=sym)
    return {
        "symbol": sym,
        "name": data["name"],
        "price": data["lastTrade"]["price"],
        "change": data["change"],
        "change_percent": data["changePercent"],
        "volume": (
            data["total"]["tradeVolume"] / 1000
            if data["market"] == "ESB"
            else data["total"]["tradeVolume"]
        ),
        "value": data["total"]["tradeValue"],
        "is_index": False,
    }


def get_candles(symbol: str, days: int = 65) -> pd.DataFrame:
    end_date = date.today()
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
