from dataclasses import dataclass
from typing import Callable

from ..data import get_stock_info
from ..db import add_transaction_and_upsert_position, get_position, list_transactions
from ..domain.trading import (
    BuyPositionResult,
    SellPositionResult,
    calculate_buy_position,
    calculate_sell_position,
)
from ..market_types import QuoteInfo


class PortfolioError(Exception):
    pass


class UnknownSymbolError(PortfolioError):
    pass


class NoPositionError(PortfolioError):
    pass


class OversellError(PortfolioError):
    def __init__(self, requested: int, available: int):
        super().__init__("sell shares exceed current position")
        self.requested = requested
        self.available = available


@dataclass(frozen=True)
class BuyTradeResult:
    symbol: str
    date: str
    position: BuyPositionResult


@dataclass(frozen=True)
class SellTradeResult:
    symbol: str
    date: str
    position: SellPositionResult


QuoteLookup = Callable[[str], QuoteInfo]


def record_buy(
    user_id: int,
    symbol: str,
    price: float,
    shares: int,
    tx_date: str,
    quote_lookup: QuoteLookup = get_stock_info,
) -> BuyTradeResult:
    sym = symbol.upper()
    try:
        quote_lookup(sym)
    except Exception as exc:
        raise UnknownSymbolError(sym) from exc

    position = get_position(user_id, sym)
    result = calculate_buy_position(position, price, shares)
    add_transaction_and_upsert_position(
        user_id,
        sym,
        "buy",
        price,
        shares,
        tx_date,
        result.fee,
        0,
        result.avg_cost,
        result.shares,
        result.realized_pnl,
    )
    return BuyTradeResult(symbol=sym, date=tx_date, position=result)


def record_sell(
    user_id: int,
    symbol: str,
    price: float,
    shares: int,
    tx_date: str,
    quote_lookup: QuoteLookup = get_stock_info,
) -> SellTradeResult:
    sym = symbol.upper()
    position = get_position(user_id, sym)
    if position is None or position["shares"] == 0:
        raise NoPositionError(sym)
    if shares > position["shares"]:
        raise OversellError(shares, position["shares"])

    try:
        info = quote_lookup(sym)
        is_etf = "ETF" in info["name"].upper()
    except Exception:
        is_etf = False

    transactions = list_transactions(user_id, sym)
    result = calculate_sell_position(position, transactions, price, shares, tx_date, is_etf)
    add_transaction_and_upsert_position(
        user_id,
        sym,
        "sell",
        price,
        shares,
        tx_date,
        result.fee,
        result.tax,
        result.avg_cost,
        result.shares,
        result.realized_pnl,
    )
    return SellTradeResult(symbol=sym, date=tx_date, position=result)
