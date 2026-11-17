from datetime import date

import discord
import pandas as pd
from discord.ext import commands
from fugle_marketdata import RestClient

from .config import DISCORD_TOKEN, FUGLE_API_KEY
from .market_types import SectorStock

# ════════════════════════════════════════════════════════
#  Bot 與 API Client
# ════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
bot   = commands.Bot(command_prefix="!", intents=intents)
stock = RestClient(api_key=FUGLE_API_KEY).stock

# ════════════════════════════════════════════════════════
#  共用 Mutable State（由 main.py 初始化）
# ════════════════════════════════════════════════════════

watchlist: dict[int, list[str]] = {}
pushed_news_ids: set[str] = set()

stock_list_cache: pd.DataFrame | None = None
stock_list_date:  date | None         = None

index_list_cache: pd.DataFrame | None = None
index_list_date:  date | None         = None

sector_cache: dict[str, list[SectorStock]] | None = None
sector_cache_date: date | None              = None

volatility_alerted: set[tuple[int, str]] = set()
volatility_last_reset_date: date | None = None
