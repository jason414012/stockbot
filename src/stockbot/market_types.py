from typing import NotRequired, TypedDict


class QuoteInfo(TypedDict):
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    volume: float | None
    value: float | None
    is_index: bool
    vol_at_ask: NotRequired[float | None]  # 外盤（買方主動，張）
    vol_at_bid: NotRequired[float | None]  # 內盤（賣方主動，張）
    # 當日日期與開高低（週報補今日 K 棒用）
    date: NotRequired[str | None]
    open: NotRequired[float | None]
    high: NotRequired[float | None]
    low: NotRequired[float | None]


class SectorStock(TypedDict):
    symbol: str
    name: str
    market: str


class NewsItem(TypedDict):
    id: str
    title: str
    link: str
    source: str
    category: str
    published: str
    ts: NotRequired[int]  # 發布時間（UTC 秒），排序用
