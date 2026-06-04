from datetime import date

import discord
import pandas as pd
from discord.ext import commands
from fugle_marketdata import RestClient

from config import DISCORD_TOKEN, FUGLE_API_KEY

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

_watchlist: dict[int, list[str]] = {}
_pushed_news_ids: set[str] = set()

_stock_list_cache: pd.DataFrame | None = None
_stock_list_date:  date | None         = None

_index_list_cache: pd.DataFrame | None = None
_index_list_date:  date | None         = None

_sector_cache: dict[str, list[dict]] | None = None
_sector_cache_date: date | None              = None

_market_open_pushed_date:  date | None = None
_market_close_pushed_date: date | None = None
_breaking_checked_ids: set[str] = set()
_weekly_report_pushed_week: int | None = None
