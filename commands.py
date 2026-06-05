"""Register all Discord slash commands.

Importing this module keeps the existing main.py contract: command decorators
run at import time, and grouped commands are added to the shared bot tree here.
"""

from state import bot

from bot_commands import menu as _menu  # noqa: F401
from bot_commands import quote as _quote  # noqa: F401
from bot_commands.alerts import alert_group
from bot_commands.sector import sector_group
from bot_commands.trade import trade_group
from bot_commands.watchlist import watch_group


bot.tree.add_command(alert_group)
bot.tree.add_command(watch_group)
bot.tree.add_command(trade_group)
bot.tree.add_command(sector_group)
