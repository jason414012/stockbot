# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

StockBot is a Discord bot for Taiwan stock market monitoring and portfolio management. It monitors TWSE/TPEx stocks via the Fugle Market Data API, sends scheduled news/alerts, and tracks user trading positions.

## Running the Bot

```bash
python main.py
```

Requires a `.env` with all four variables set:
- `DISCORD_TOKEN`
- `FUGLE_API_KEY`
- `NEWS_CHANNEL_ID`
- `ALERT_CHANNEL_ID`

The bot validates `DISCORD_TOKEN` and `FUGLE_API_KEY` on startup and exits if either is missing. The channel IDs only warn.

## Architecture

Six focused modules with clear boundaries:

| Module | Responsibility |
|---|---|
| `config.py` | Loads `.env`, defines news sources, breaking-news keywords, timezone, DB path |
| `state.py` | Singleton bot/Fugle client instances, and all in-memory mutable caches |
| `db.py` | All SQLite reads/writes (watchlist, alerts, transactions, positions) |
| `data.py` | Fugle API calls, stock/index/sector list caching, fee/tax math, formatting |
| `news.py` | RSS parsing, breaking-news detection, Discord Embed construction |
| `commands.py` | All Discord slash command handlers; `bot.tree.add_command(group)` calls at end of file |
| `tasks.py` | Seven background `asyncio` tasks that fire on schedules |
| `main.py` | Wires everything: initializes DB, preloads state, registers tasks, starts bot |

**Command registration:** `main.py` does `import commands  # noqa: F401` — the import itself executes all decorators and `bot.tree.add_command()` calls at module level. Nothing further is needed.

**Async/sync boundary:** All Fugle API calls are synchronous. `tasks.py` wraps them with `loop.run_in_executor(None, fn, arg)` to avoid blocking the event loop. Commands use `await interaction.response.defer()` then call the sync API directly (acceptable since command handlers run in the event loop thread but Discord tolerates brief blocking for defer'd responses).

**Cross-module dependency:** `tasks.py` imports `_format_table` from `commands.py` for the weekly report. This is the only cross-command import.

## Key Business Logic

**Trading math**
- Buy fee: 0.1425% of trade value, minimum 20 TWD, rounded
- Sell tax: 0.3% stock / 0.1% ETF; halved for same-date day trades; floor at 1 TWD (truncated, not rounded)
- ETF detection: `"ETF" in info["name"].upper()` — name-based, not symbol-based
- Day-trade detection: any existing buy transaction for same symbol on same `transaction_date`
- Position cost basis uses LIFO. `_build_lifo_lots()` reconstructs lot history from all prior transactions; `_calc_sell_cost_and_new_avg()` uses it. `positions.avg_cost` is kept updated after every trade but LIFO lots are recomputed from raw `transactions` rows at sell time.
- `_db_remove_position` cascades: also deletes all `transactions` rows for that symbol (code-level, not a DB FK).

**Caches in `state.py`**
- `_stock_list_cache` / `_index_list_cache` / `_sector_cache` — refreshed once per calendar day
- `_watchlist` — loaded from DB at startup; mutated in memory and written to DB on every add/remove
- `_pushed_news_ids` — in-memory set loaded from DB at startup (3-day lookback); `pushed_news` table entries older than 3 days are purged on load
- `_breaking_checked_ids` — reset daily inside `breaking_news_scan` via a `_last_reset` attr on the task function itself

**Task deduplication pattern:** Time-triggered tasks (`market_open_push`, `market_close_push`, `weekly_report_push`) run on a 1-minute loop and check the clock inside the handler. They guard against double-fire across restarts with a date/week-number stored in `state.*_pushed_date` variables.

**Taiwan market hours:** `data.is_trading_hours()` — weekdays 09:00–13:30 Asia/Taipei.

**Symbol detection:** `_looks_like_symbol()` in `commands.py` matches pure digits (股票代號) or `IX\d+` pattern (指數代號 like `IX0001`).

**CJK display width:** `_dw()` / `_rpad()` / `_lpad()` in `commands.py` count full-width chars as 2. `_format_table()` uses these for aligned monospace output. Match this pattern when adding tabular output.

## Scheduled Tasks (tasks.py)

| Task | Loop interval | Fires when |
|---|---|---|
| `auto_news_push` | 1 min | always |
| `market_open_push` | 1 min | weekday 09:00 exactly |
| `market_close_push` | 1 min | weekday 13:30 exactly |
| `breaking_news_scan` | 5 min | trading hours only |
| `price_alert_scan` | 2 min | trading hours only |
| `watchlist_volatility_alert` | 5 min | trading hours only; threshold ±3% |
| `weekly_report_push` | 1 min | Friday 14:00 exactly |

Each task has a `before_loop` hook that calls `await state.bot.wait_until_ready()`.

## Database Schema (db.py)

- `watchlist(user_id, symbol, added_at)` — PK (user_id, symbol); max 10 per user enforced in commands
- `price_alerts(id, user_id, symbol, target, direction)` — direction is `'above'` or `'below'`; auto-deleted on trigger; max 3 per user per symbol
- `transactions(id, user_id, symbol, type, price, shares, transaction_date, fee, tax)`
- `positions(user_id, symbol, avg_cost, shares, realized_pnl)` — PK (user_id, symbol)
- `pushed_news(news_id, pushed_at)` — 3-day TTL purged on load

## Slash Commands (commands.py)

- `/q <symbol|name>` — direct quote if symbol-like; name search with paginated `SearchPageView` (15/page, 120s timeout) if ≥15 results
- `/symbol <s1> [s2..s5]` — side-by-side compare; indices and stocks rendered in separate code blocks
- `/alert set|list|remove` — price target alerts; direction auto-detected from current price vs target
- `/watch add|remove|list|clear` — personal watchlist
- `/trade buy|sell|profit|history|reset` — portfolio tracking; `buy`/`sell`/`profit`/`history` are ephemeral
- `/sector list|search` — browse 38 industry sectors with paginated `SectorPageView`
- `/menu` — help text listing all commands and auto-push schedule

## Dependencies

```
discord.py
fugle-marketdata
pandas
feedparser
python-dotenv
```

Install: `pip install -r requirements.txt`

SQLite database file: `watchlist.db` in the project root (path set in `config.DB_FILE`).
