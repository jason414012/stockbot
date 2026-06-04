import sqlite3

from config import DB_FILE

# ════════════════════════════════════════════════════════
#  SQLite：自選股 / 已推播新聞 / 價格警示
# ════════════════════════════════════════════════════════


def _init_db():
    """建立所有資料表（若不存在）。"""
    with sqlite3.connect(DB_FILE) as con:
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
                direction  TEXT    NOT NULL,   -- 'above' 或 'below'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                symbol           TEXT    NOT NULL,
                type             TEXT    NOT NULL,
                price            REAL    NOT NULL,
                shares           INTEGER NOT NULL,
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
        """)
    print(f"[INFO] SQLite 資料庫已就緒：{DB_FILE}")


def _load_pushed_news(days: int = 3) -> set[str]:
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "DELETE FROM pushed_news WHERE pushed_at < datetime('now', ?)",
            (f"-{days} days",)
        )
        rows = con.execute("SELECT news_id FROM pushed_news").fetchall()
    return {row[0] for row in rows}


def _save_pushed_news(news_id: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "INSERT OR IGNORE INTO pushed_news (news_id) VALUES (?)",
            (news_id,)
        )


def _load_watchlist() -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    try:
        with sqlite3.connect(DB_FILE) as con:
            rows = con.execute(
                "SELECT user_id, symbol FROM watchlist ORDER BY added_at"
            ).fetchall()
        for uid, sym in rows:
            result.setdefault(uid, []).append(sym)
    except Exception as e:
        print(f"[WARN] 讀取自選股失敗：{e}")
    return result


def _db_add(user_id: int, symbol: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, symbol) VALUES (?, ?)",
            (user_id, symbol)
        )


def _db_remove(user_id: int, symbol: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
            (user_id, symbol)
        )


def _db_clear(user_id: int):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))


# ── 價格警示 DB 操作 ──────────────────────────────────────────────────────────

def _db_add_alert(user_id: int, symbol: str, target: float, direction: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "INSERT INTO price_alerts (user_id, symbol, target, direction) VALUES (?, ?, ?, ?)",
            (user_id, symbol, target, direction)
        )


def _db_remove_alert(alert_id: int, user_id: int) -> bool:
    with sqlite3.connect(DB_FILE) as con:
        cur = con.execute(
            "DELETE FROM price_alerts WHERE id = ? AND user_id = ?",
            (alert_id, user_id)
        )
        return cur.rowcount > 0


def _db_list_alerts(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_FILE) as con:
        rows = con.execute(
            "SELECT id, symbol, target, direction FROM price_alerts WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    return [{"id": r[0], "symbol": r[1], "target": r[2], "direction": r[3]} for r in rows]


def _db_all_alerts() -> list[dict]:
    with sqlite3.connect(DB_FILE) as con:
        rows = con.execute(
            "SELECT id, user_id, symbol, target, direction FROM price_alerts"
        ).fetchall()
    return [{"id": r[0], "user_id": r[1], "symbol": r[2], "target": r[3], "direction": r[4]} for r in rows]


def _db_delete_alert_by_id(alert_id: int):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))


# ── 交易記錄 / 持倉 DB 操作 ──────────────────────────────────────────────────

def _db_add_transaction(
    user_id: int, symbol: str, tx_type: str,
    price: float, shares: int, transaction_date: str,
    fee: int, tax: int
):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "INSERT INTO transactions (user_id, symbol, type, price, shares, transaction_date, fee, tax) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, symbol, tx_type, price, shares, transaction_date, fee, tax)
        )


def _db_list_transactions(user_id: int, symbol: str) -> list[dict]:
    with sqlite3.connect(DB_FILE) as con:
        rows = con.execute(
            "SELECT id, type, price, shares, transaction_date, fee, tax, created_at "
            "FROM transactions WHERE user_id = ? AND symbol = ? ORDER BY transaction_date DESC, created_at DESC",
            (user_id, symbol)
        ).fetchall()
    return [
        {"id": r[0], "type": r[1], "price": r[2], "shares": r[3],
         "date": r[4], "fee": r[5], "tax": r[6], "created_at": r[7]}
        for r in rows
    ]


def _db_list_all_transactions(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_FILE) as con:
        rows = con.execute(
            "SELECT id, symbol, type, price, shares, transaction_date, fee, tax "
            "FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC, created_at DESC",
            (user_id,)
        ).fetchall()
    return [
        {"id": r[0], "symbol": r[1], "type": r[2], "price": r[3], "shares": r[4],
         "date": r[5], "fee": r[6], "tax": r[7]}
        for r in rows
    ]


def _db_get_position(user_id: int, symbol: str) -> dict | None:
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT avg_cost, shares, realized_pnl FROM positions WHERE user_id = ? AND symbol = ?",
            (user_id, symbol)
        ).fetchone()
    if row is None:
        return None
    return {"avg_cost": row[0], "shares": row[1], "realized_pnl": row[2]}


def _db_upsert_position(user_id: int, symbol: str, avg_cost: float, shares: int, realized_pnl: float):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "INSERT OR REPLACE INTO positions (user_id, symbol, avg_cost, shares, realized_pnl) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, symbol, avg_cost, shares, realized_pnl)
        )


def _db_remove_position(user_id: int, symbol: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("DELETE FROM positions WHERE user_id = ? AND symbol = ?", (user_id, symbol))
        con.execute("DELETE FROM transactions WHERE user_id = ? AND symbol = ?", (user_id, symbol))


def _db_remove_all_positions(user_id: int):
    with sqlite3.connect(DB_FILE) as con:
        con.execute("DELETE FROM positions WHERE user_id = ?", (user_id,))
        con.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))


def _db_list_positions(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_FILE) as con:
        rows = con.execute(
            "SELECT symbol, avg_cost, shares, realized_pnl FROM positions "
            "WHERE user_id = ? AND (shares > 0 OR realized_pnl != 0) "
            "ORDER BY shares DESC, symbol",
            (user_id,)
        ).fetchall()
    return [
        {"symbol": r[0], "avg_cost": r[1], "shares": r[2], "realized_pnl": r[3]}
        for r in rows
    ]
