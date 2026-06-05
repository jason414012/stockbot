from typing import TypedDict


class QuoteInfo(TypedDict):
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    volume: float | None
    value: float | None
    is_index: bool


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
