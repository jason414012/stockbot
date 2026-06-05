import logging
import sqlite3
from contextlib import contextmanager

from .config import DB_FILE

logger = logging.getLogger(__name__)


@contextmanager
def _connect():
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


# ════════════════════════════════════════════════════════
#  SQLite：資料表初始化
# ════════════════════════════════════════════════════════


def init_db():
    """建立所有資料表（若不存在）。"""
    with _connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id  INTEGER NOT NULL,
                symbol   TEXT    NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, symbol)
            );
            CREATE TABLE IF NOT EXISTS pushed_news (
                news_id    TEXT      NOT NULL PRIMARY KEY,
                pushed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS price_alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                symbol     TEXT    NOT NULL,
                target     REAL    NOT NULL,
                direction  TEXT    NOT NULL CHECK (direction IN ('above', 'below')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                symbol           TEXT    NOT NULL,
                type             TEXT    NOT NULL CHECK (type IN ('buy', 'sell')),
                price            REAL    NOT NULL CHECK (price > 0),
                shares           INTEGER NOT NULL CHECK (shares > 0),
                transaction_date DATE    NOT NULL,
                fee              INTEGER NOT NULL,
                tax              INTEGER NOT NULL DEFAULT 0,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS positions (
                user_id       INTEGER NOT NULL,
                symbol        TEXT    NOT NULL,
                avg_cost      REAL    NOT NULL,
                shares        INTEGER NOT NULL,
                realized_pnl  REAL    NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol ON price_alerts(symbol);
            CREATE INDEX IF NOT EXISTS idx_transactions_user_symbol_date
                ON transactions(user_id, symbol, transaction_date);
        """)
    logger.info("SQLite 資料庫已就緒：%s", DB_FILE)


# ── 已推播新聞 ────────────────────────────────────────────────────────────────


def load_pushed_news(days: int = 3) -> set[str]:
    with _connect() as con:
        con.execute(
            "DELETE FROM pushed_news WHERE pushed_at < datetime('now', ?)",
            (f"-{days} days",)
        )
        rows = con.execute("SELECT news_id FROM pushed_news").fetchall()
    return {row["news_id"] for row in rows}


def save_pushed_news(news_id: str):
    with _connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO pushed_news (news_id) VALUES (?)",
            (news_id,)
        )


# ── 自選股 ────────────────────────────────────────────────────────────────────


def load_watchlist() -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    try:
        with _connect() as con:
            rows = con.execute(
                "SELECT user_id, symbol FROM watchlist ORDER BY added_at"
            ).fetchall()
        for row in rows:
            result.setdefault(row["user_id"], []).append(row["symbol"])
    except Exception as e:
        logger.warning("讀取自選股失敗：%s", e)
    return result


def add_watchlist(user_id: int, symbol: str):
    with _connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, symbol) VALUES (?, ?)",
            (user_id, symbol)
        )


def remove_watchlist(user_id: int, symbol: str):
    with _connect() as con:
        con.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
            (user_id, symbol)
        )


def clear_watchlist(user_id: int):
    with _connect() as con:
        con.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))


# ── 價格警示 ──────────────────────────────────────────────────────────────────


def add_alert(user_id: int, symbol: str, target: float, direction: str):
    with _connect() as con:
        con.execute(
            "INSERT INTO price_alerts (user_id, symbol, target, direction) VALUES (?, ?, ?, ?)",
            (user_id, symbol, target, direction)
        )


def remove_alert(alert_id: int, user_id: int) -> bool:
    with _connect() as con:
        cur = con.execute(
            "DELETE FROM price_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user_id)
        )
        return cur.rowcount > 0


def list_user_alerts(user_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, symbol, target, direction FROM price_alerts WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def list_all_alerts() -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, user_id, symbol, target, direction FROM price_alerts"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_alert(alert_id: int):
    with _connect() as con:
        con.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))


# ── 交易記錄 / 持倉 ──────────────────────────────────────────────────────────


def add_transaction(
    user_id: int, symbol: str, tx_type: str,
    price: float, shares: int, transaction_date: str,
    fee: int, tax: int
):
    with _connect() as con:
        con.execute(
            "INSERT INTO transactions (user_id, symbol, type, price, shares, transaction_date, fee, tax) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, symbol, tx_type, price, shares, transaction_date, fee, tax)
        )


def list_transactions(user_id: int, symbol: str) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, type, price, shares, transaction_date, fee, tax, created_at "
            "FROM transactions WHERE user_id = ? AND symbol = ? ORDER BY transaction_date DESC, created_at DESC",
            (user_id, symbol)
        ).fetchall()
    return [
        {"id": r["id"], "type": r["type"], "price": r["price"], "shares": r["shares"],
         "date": r["transaction_date"], "fee": r["fee"], "tax": r["tax"], "created_at": r["created_at"]}
        for r in rows
    ]


def list_all_transactions(user_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT id, symbol, type, price, shares, transaction_date, fee, tax "
            "FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC, created_at DESC",
            (user_id,)
        ).fetchall()
    return [
        {"id": r["id"], "symbol": r["symbol"], "type": r["type"], "price": r["price"],
         "shares": r["shares"], "date": r["transaction_date"], "fee": r["fee"], "tax": r["tax"]}
        for r in rows
    ]


def get_position(user_id: int, symbol: str) -> dict | None:
    with _connect() as con:
        row = con.execute(
            "SELECT avg_cost, shares, realized_pnl FROM positions WHERE user_id = ? AND symbol = ?",
            (user_id, symbol)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def upsert_position(user_id: int, symbol: str, avg_cost: float, shares: int, realized_pnl: float):
    with _connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO positions (user_id, symbol, avg_cost, shares, realized_pnl) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, symbol, avg_cost, shares, realized_pnl)
        )


def add_transaction_and_upsert_position(
    user_id: int,
    symbol: str,
    tx_type: str,
    price: float,
    shares: int,
    transaction_date: str,
    fee: int,
    tax: int,
    avg_cost: float,
    position_shares: int,
    realized_pnl: float,
):
    with _connect() as con:
        con.execute(
            "INSERT INTO transactions (user_id, symbol, type, price, shares, transaction_date, fee, tax) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, symbol, tx_type, price, shares, transaction_date, fee, tax)
        )
        con.execute(
            "INSERT OR REPLACE INTO positions (user_id, symbol, avg_cost, shares, realized_pnl) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, symbol, avg_cost, position_shares, realized_pnl)
        )


def remove_position(user_id: int, symbol: str):
    with _connect() as con:
        con.execute("DELETE FROM positions WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        con.execute("DELETE FROM transactions WHERE user_id = ? AND symbol = ?", (user_id, symbol))


def remove_all_positions(user_id: int):
    with _connect() as con:
        con.execute("DELETE FROM positions WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))


def list_positions(user_id: int) -> list[dict]:
    with _connect() as con:
        rows = con.execute(
            "SELECT symbol, avg_cost, shares, realized_pnl FROM positions "
            "WHERE user_id = ? AND (shares > 0 OR realized_pnl != 0) "
            "ORDER BY shares DESC, symbol",
            (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]
