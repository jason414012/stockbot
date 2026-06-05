import asyncio

from .. import state
from ..data import get_stock_info
from ..market_types import QuoteInfo


async def get_stock_info_async(symbol: str) -> QuoteInfo:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_stock_info, symbol)


async def _wait_ready():
    await state.bot.wait_until_ready()
