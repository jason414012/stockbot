# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

Focused modules with lightweight layering:

| Module | Responsibility |
|---|---|
| `src/stockbot/config.py` | Loads `.env`, defines news sources, breaking-news keywords, timezone, DB path, business-limit constants |
| `src/stockbot/state.py` | Singleton bot/Fugle client instances, and all in-memory mutable caches |
| `src/stockbot/db.py` | All SQLite reads/writes (watchlist, alerts, transactions, positions) |
| `src/stockbot/data.py` | Backward-compatible facade for market helpers |
| `src/stockbot/market_data.py` | Fugle API calls, stock/index/sector list caching, and historical candles |
| `src/stockbot/market_search.py` | Name search and CJK keyword tokenization |
| `src/stockbot/market_formatting.py` | Quote/value formatting |
| `src/stockbot/market_clock.py` | Taiwan market-hours checks |
| `src/stockbot/display.py` | CJK-aware text formatting utilities: `cjk_width`, `pad_right`, `pad_left`, `format_table` |
| `src/stockbot/news.py` | RSS parsing, breaking-news detection, Discord Embed construction |
| `src/stockbot/domain/alerts.py` | Pure alert rules: target direction, trigger checks, volatility threshold checks |
| `src/stockbot/domain/trading.py` | Pure trading business rules: date parsing, fees, taxes, LIFO lots, position math |
| `src/stockbot/services/portfolio_service.py` | Coordinates trading rules with DB writes and quote lookups for buy/sell flows |
| `src/stockbot/commands.py` | Slash command registration entrypoint; imports command modules and calls `bot.tree.add_command(group)` |
| `src/stockbot/bot_commands/` | Discord slash command handlers split by feature (`quote`, `alerts`, `watchlist`, `trade`, `sector`, `menu`) plus shared UI helpers |
| `src/stockbot/tasks/` | Seven background `asyncio` tasks split by news, alerts, and reports |
| `src/stockbot/main.py` | Wires everything: initializes DB, preloads state, registers tasks, starts bot |
| `main.py` | Repository-root compatibility launcher |

**Command registration:** `src/stockbot/main.py` imports `stockbot.commands` — that import loads `bot_commands/*` modules, executes direct command decorators, and registers grouped commands in `commands.py`. Nothing further is needed.

**Async/sync boundary:** All Fugle API calls are synchronous. High-frequency task quote lookups use `loop.run_in_executor(None, fn, arg)` to avoid blocking the event loop. The weekly report computes each unique symbol once via `tasks.reports.weekly_row()` inside an executor. Commands use `await interaction.response.defer()` then call the sync API directly (acceptable since command handlers run in the event loop thread but Discord tolerates brief blocking for defer'd responses).

**Layering:** keep pure business rules in `src/stockbot/domain/` free of Discord, Fugle, SQLite, and `.env` dependencies. Application services in `src/stockbot/services/` may coordinate `db.py` and `data.py`. Discord commands and scheduled tasks should stay as orchestration/formatting layers.

**Shared utilities:** `display.py` contains CJK-aware formatting functions used by command modules and report tasks. Command-specific pagination and quote embed helpers live in `bot_commands/common.py`.

**Logging:** All modules use Python's `logging` module (configured in `config.py`). Use `logger = logging.getLogger(__name__)` in each module.

## Key Business Logic

**Trading math**
- Implemented in `src/stockbot/domain/trading.py`; keep new trading calculations there so they can be unit-tested without Discord/Fugle/SQLite.
- Buy fee: 0.1425% of trade value, minimum 20 TWD, rounded
- Sell tax: 0.3% stock / 0.1% ETF; stock day trades halved to 0.15% (ETF day trades stay 0.1%); floor at 1 TWD (truncated, not rounded)
- ETF detection: `domain.trading.is_etf_symbol()` — symbol starts with `00` (Taiwan ETF names usually lack "ETF")
- Stock list for name search accepts 4-digit stocks plus `00`-prefixed ETF codes (4–6 digits, optional letter suffix like `00632R`)
- Day-trade detection: any existing buy transaction for same symbol on same `transaction_date`
- Position cost basis uses LIFO. `build_lifo_lots()` reconstructs lot history from all prior transactions; `calc_sell_cost_and_new_avg()` uses it. `positions.avg_cost` is kept updated after every trade but LIFO lots are recomputed from raw `transactions` rows at sell time.
- `remove_position` cascades: also deletes all `transactions` rows for that symbol (code-level, not a DB FK).

**Business-limit constants (in `config.py`)**
- `MAX_ALERTS_PER_SYMBOL` (3), `MAX_WATCHLIST_SIZE` (10), `VOLATILITY_THRESHOLD_PCT` (3.0)
- `PAGE_SIZE` (15), `HISTORY_DISPLAY_LIMIT` (20), `MAX_COMPARE_SYMBOLS` (5)

**Alert rules**
- Implemented in `src/stockbot/domain/alerts.py`; keep direction and trigger/volatility checks there.
- Price alert direction is `'above'` if target is above current price, otherwise `'below'`.
- Price alerts trigger when current price crosses the stored target in the stored direction.

**Caches in `state.py`**
- `stock_list_cache` / `index_list_cache` / `sector_cache` — refreshed once per calendar day
- `watchlist` — loaded from DB at startup; mutated in memory and written to DB on every add/remove
- `pushed_news_ids` — in-memory set loaded from DB at startup (3-day lookback); `pushed_news` table entries older than 3 days are purged on load
- `breaking_checked_ids` — reset daily via `breaking_last_reset_date` in `state.py`

**Task deduplication pattern:** Time-triggered tasks (`market_open_push`, `market_close_push`, `weekly_report_push`) run on a 1-minute loop and check the clock inside the handler. They fire anywhere inside a catch-up window (`market_clock.in_time_window()`), and record "already sent" in the `bot_meta` table (`market_open_pushed` / `market_close_pushed` = ISO date, `weekly_report_pushed` = `YYYY-Www`) via `db.get_meta()` / `db.set_meta()`, so restarts neither skip nor double-send. The marker is written only after sending.

**Open/close digests** push the latest 5 `財經` items sorted by RSS publish time (`news.pick_latest_news()`, `NewsItem["ts"]`), including items already pushed by `auto_news_push`.

**Weekly report** covers Monday-to-date bars (`tasks.reports.weekly_row()`); if today's daily candle isn't in history yet, it is filled from the intraday quote's `date`/`open`/`high`/`low`/`price` (only when the quote date is today).

**Quote display:** `get_stock_info` returns `vol_at_ask` (外盤, buyer-initiated) and `vol_at_bid` (內盤, seller-initiated) from Fugle `total.tradeVolumeAtAsk/AtBid` (ESB converted to 張). `market_formatting.format_bid_ask()` labels them (外盤 share ≥55% 買方強, ≤45% 賣方強, else 多空均衡) and is shown in `/q` and `/watch list` via `add_quote_field()`. Price and volatility alerts append volume via `format_volume_lots()` but not 內外盤. Both helpers return "" for indices.

**Taiwan market hours:** `data.is_trading_hours()` / `market_clock.is_trading_hours(now=None, close_grace_min=0)` — weekdays 09:00–13:30 Asia/Taipei; `price_alert_scan` passes `close_grace_min=5` so the 13:30 closing auction price is checked.

**Symbol detection:** `looks_like_symbol()` in `bot_commands/common.py` matches pure digits (股票代號) or `IX\d+` pattern (指數代號 like `IX0001`).

**CJK display width:** `cjk_width()` / `pad_right()` / `pad_left()` in `display.py` count full-width chars as 2. `format_table()` uses these for aligned monospace output. Match this pattern when adding tabular output.

## Scheduled Tasks (`src/stockbot/tasks/`)

| Task | Loop interval | Fires when |
|---|---|---|
| `auto_news_push` | 1 min | always |
| `market_open_push` | 1 min | weekday 09:00–09:29, once per day |
| `market_close_push` | 1 min | weekday 13:30–13:59, once per day |
| `breaking_news_scan` | 5 min | trading hours only |
| `price_alert_scan` | 2 min | trading hours + 5 min after close |
| `watchlist_volatility_alert` | 5 min | trading hours only; threshold ±`VOLATILITY_THRESHOLD_PCT`% |
| `weekly_report_push` | 1 min | Friday from 14:00, once per ISO week |

All tasks share a single `_wait_ready()` before-loop hook that calls `await state.bot.wait_until_ready()`.

## Database Schema (db.py)

All db functions use descriptive names: `add_watchlist`, `remove_watchlist`, `list_user_alerts`, `add_transaction`, `get_position`, etc. Connection handling uses a shared `_connect()` helper with `sqlite3.Row` factory.

- `watchlist(user_id, symbol, added_at)` — PK (user_id, symbol); max `MAX_WATCHLIST_SIZE` per user enforced in commands
- `price_alerts(id, user_id, symbol, target, direction)` — direction is `'above'` or `'below'`; auto-deleted on trigger; max `MAX_ALERTS_PER_SYMBOL` per user per symbol; indexed by `symbol`
- `transactions(id, user_id, symbol, type, price, shares, transaction_date, fee, tax)` — type is `'buy'` or `'sell'`; indexed by `(user_id, symbol, transaction_date)`
- `positions(user_id, symbol, avg_cost, shares, realized_pnl)` — PK (user_id, symbol)
- `pushed_news(news_id, pushed_at)` — 3-day TTL purged on load
- `bot_meta(key, value)` — scheduled-push "already sent" markers

## Slash Commands (`bot_commands/`)

- `/q <symbol|name>` — direct quote if symbol-like; name search uses `SearchPageView` for multiple results (`PAGE_SIZE`/page, 120s timeout)
- `/symbol <s1> [s2..s5]` — side-by-side compare; indices and stocks rendered in separate code blocks
- `/alert set|list|remove` — price target alerts; direction auto-detected from current price vs target
- `/watch add|remove|list|clear` — personal watchlist
- `/trade buy|sell|profit|history|reset` — portfolio tracking; `buy`/`sell`/`profit`/`history` are ephemeral
- `/sector list|search` — browse 38 industry sectors with paginated `SectorPageView`
- `/menu` — help text listing all commands and auto-push schedule

**UI patterns:** `PageView` is a shared base class for pagination (used by `SearchPageView` and `SectorPageView`). `add_quote_field(embed, info)` is the shared helper for adding stock/index quote fields to embeds.

## Dependencies

```
discord.py
fugle-marketdata
pandas
feedparser
python-dotenv
```

Install: `pip install -r requirements.txt`

Python: requires 3.11+; tested with Python 3.14.5.

SQLite database file: `watchlist.db` in the project root (path set in `config.DB_FILE`).
