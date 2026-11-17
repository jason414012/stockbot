"""Backward-compatible facade for market data helpers.

Implementation is split across focused modules, while existing callers can
keep importing from stockbot.data.
"""

from .market_clock import is_trading_hours
from .market_data import (
    SECTOR_CODE_MAP,
    get_candles,
    get_index_list,
    get_sector_data,
    get_stock_info,
    get_stock_list,
)
from .market_formatting import (
    format_bid_ask,
    format_stock_message,
    format_value,
    format_volume_lots,
)
from .market_search import search_by_name


__all__ = [
    "SECTOR_CODE_MAP",
    "format_bid_ask",
    "format_stock_message",
    "format_value",
    "format_volume_lots",
    "get_candles",
    "get_index_list",
    "get_sector_data",
    "get_stock_info",
    "get_stock_list",
    "is_trading_hours",
    "search_by_name",
]
