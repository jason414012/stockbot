from dataclasses import dataclass
from datetime import date


BUY_FEE_RATE = 0.001425
STOCK_TAX_RATE = 0.003
ETF_TAX_RATE = 0.001
MIN_FEE = 20
MIN_TAX = 1


@dataclass(frozen=True)
class BuyPositionResult:
    fee: int
    avg_cost: float
    shares: int
    realized_pnl: float


@dataclass(frozen=True)
class SellPositionResult:
    fee: int
    tax: int
    tax_label: str
    sell_cost: float
    net_proceeds: float
    pnl: float
    pnl_pct: float
    avg_cost: float
    shares: int
    realized_pnl: float
    is_daytrade: bool
    is_etf: bool


def parse_trade_date(date_str: str | None, today: date | None = None) -> str | None:
    if date_str is None:
        return (today or date.today()).isoformat()
    try:
        return date.fromisoformat(date_str).isoformat()
    except ValueError:
        return None


def calculate_fee(price: float, shares: int) -> int:
    return max(round(price * shares * BUY_FEE_RATE), MIN_FEE)


def calculate_tax(price: float, shares: int, is_etf: bool, is_daytrade: bool) -> int:
    rate = ETF_TAX_RATE if is_etf else STOCK_TAX_RATE
    if is_daytrade:
        rate /= 2
    return max(int(price * shares * rate), MIN_TAX)


def get_tax_label(is_etf: bool, is_daytrade: bool) -> str:
    if is_etf and is_daytrade:
        return "ETF 當沖 0.05%"
    if is_etf:
        return "ETF 0.1%"
    if is_daytrade:
        return "現股當沖 0.15%"
    return "一般股票 0.3%"


def is_daytrade(transactions: list[dict], tx_date: str) -> bool:
    return any(t["type"] == "buy" and t["date"] == tx_date for t in transactions)


def build_lifo_lots(transactions: list[dict]) -> list[list[float]]:
    sorted_txs = sorted(transactions, key=lambda t: (t["date"], t.get("created_at", "")))
    lots: list[list[float]] = []
    for tx in sorted_txs:
        if tx["type"] == "buy":
            cost_per_share = (tx["price"] * tx["shares"] + tx["fee"]) / tx["shares"]
            lots.append([tx["shares"], cost_per_share])
        elif tx["type"] == "sell":
            remaining = tx["shares"]
            while remaining > 0 and lots:
                if lots[-1][0] <= remaining:
                    remaining -= lots[-1][0]
                    lots.pop()
                else:
                    lots[-1][0] -= remaining
                    remaining = 0
    return lots


def calc_sell_cost_and_new_avg(transactions: list[dict], sell_shares: int) -> tuple[float, float]:
    lots = build_lifo_lots(transactions)

    sell_cost = 0.0
    remaining = sell_shares
    for lot in reversed(lots):
        if remaining <= 0:
            break
        take = min(remaining, lot[0])
        sell_cost += take * lot[1]
        remaining -= take

    remaining = sell_shares
    for i in range(len(lots) - 1, -1, -1):
        if remaining <= 0:
            break
        if lots[i][0] <= remaining:
            remaining -= lots[i][0]
            lots[i][0] = 0
        else:
            lots[i][0] -= remaining
            remaining = 0

    remaining_lots = [lot for lot in lots if lot[0] > 0]
    if not remaining_lots:
        return sell_cost, 0.0

    total_shares = sum(lot[0] for lot in remaining_lots)
    new_avg = sum(lot[0] * lot[1] for lot in remaining_lots) / total_shares
    return sell_cost, new_avg


def calculate_buy_position(position: dict | None, price: float, shares: int) -> BuyPositionResult:
    fee = calculate_fee(price, shares)
    if position is None or position["shares"] == 0:
        return BuyPositionResult(
            fee=fee,
            avg_cost=(price * shares + fee) / shares,
            shares=shares,
            realized_pnl=position["realized_pnl"] if position else 0.0,
        )

    old_cost_total = position["avg_cost"] * position["shares"]
    new_shares = position["shares"] + shares
    return BuyPositionResult(
        fee=fee,
        avg_cost=(old_cost_total + price * shares + fee) / new_shares,
        shares=new_shares,
        realized_pnl=position["realized_pnl"],
    )


def calculate_sell_position(
    position: dict,
    transactions: list[dict],
    price: float,
    shares: int,
    tx_date: str,
    is_etf: bool,
) -> SellPositionResult:
    daytrade = is_daytrade(transactions, tx_date)
    fee = calculate_fee(price, shares)
    tax = calculate_tax(price, shares, is_etf, daytrade)
    net_proceeds = price * shares - fee - tax
    sell_cost, new_avg = calc_sell_cost_and_new_avg(transactions, shares)
    pnl = net_proceeds - sell_cost
    new_shares = position["shares"] - shares

    return SellPositionResult(
        fee=fee,
        tax=tax,
        tax_label=get_tax_label(is_etf, daytrade),
        sell_cost=sell_cost,
        net_proceeds=net_proceeds,
        pnl=pnl,
        pnl_pct=pnl / sell_cost * 100 if sell_cost > 0 else 0,
        avg_cost=new_avg,
        shares=new_shares,
        realized_pnl=position["realized_pnl"] + pnl,
        is_daytrade=daytrade,
        is_etf=is_etf,
    )
