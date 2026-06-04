import discord
from discord import app_commands
import pandas as pd
import unicodedata
from datetime import date

import state
from state import bot
from db import (
    _db_add, _db_remove, _db_clear,
    _db_add_alert, _db_remove_alert, _db_list_alerts,
    _db_add_transaction, _db_list_transactions, _db_list_all_transactions,
    _db_get_position, _db_upsert_position,
    _db_remove_position, _db_remove_all_positions, _db_list_positions,
)
from data import (
    get_stock_info, search_by_name, format_value,
    get_sector_data, calculate_fee, calculate_tax,
)
from news import fetch_latest_news, build_news_embed

import re as _re


def _dw(s: str) -> int:
    """CJK-aware 顯示寬度（全形字元算 2）。"""
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

def _rpad(s: str, w: int) -> str:
    return s + ' ' * max(0, w - _dw(s))

def _lpad(s: str, w: int) -> str:
    return ' ' * max(0, w - _dw(s)) + s


def _format_table(rows: list[dict], right_cols: set[str] | None = None) -> str:
    """CJK-aware monospace table formatter.
    right_cols: column names that should be right-aligned (default: all except first two).
    """
    if not rows:
        return ""
    cols = list(rows[0].keys())
    if right_cols is None:
        right_cols = set(cols[2:])
    # convert every cell to str
    str_rows = [{c: str(r[c]) for c in cols} for r in rows]
    # compute max display width per column (header vs data)
    widths = {c: _dw(c) for c in cols}
    for r in str_rows:
        for c in cols:
            widths[c] = max(widths[c], _dw(r[c]))
    # build header + separator + data lines
    header = "  ".join(
        (_lpad(c, widths[c]) if c in right_cols else _rpad(c, widths[c])) for c in cols
    )
    sep = "─" * _dw(header)
    data_lines = []
    for r in str_rows:
        line = "  ".join(
            (_lpad(r[c], widths[c]) if c in right_cols else _rpad(r[c], widths[c])) for c in cols
        )
        data_lines.append(line)
    return "\n".join([header, sep] + data_lines)


def _looks_like_symbol(text: str) -> bool:
    """純數字（個股代號）或 IX 開頭（指數代號）視為代號，其餘視為關鍵字。"""
    return bool(_re.fullmatch(r'\d+', text) or _re.fullmatch(r'IX\d+', text, _re.IGNORECASE))


class SearchPageView(discord.ui.View):
    """搜尋結果翻頁按鈕，每頁顯示 PAGE_SIZE 筆。"""
    PAGE_SIZE = 15

    def __init__(self, keyword: str, rows: list[dict]):
        super().__init__(timeout=120)
        self.keyword = keyword
        self.rows = rows
        self.page = 0
        self.total_pages = max(1, -(-len(rows) // self.PAGE_SIZE))
        self._refresh_buttons()

    def _build_content(self) -> str:
        start = self.page * self.PAGE_SIZE
        chunk = self.rows[start: start + self.PAGE_SIZE]
        lines = "代號　　名稱\n" + "─" * 20 + "\n"
        lines += "\n".join(f"`{r['symbol']}`　{r['name']}" for r in chunk)
        total = len(self.rows)
        return (
            f"🔍 **「{self.keyword}」共 {total} 筆結果**　"
            f"（第 {self.page + 1} / {self.total_pages} 頁）\n"
            f"{lines}\n\n"
            "輸入 `/q 代號` 查詢詳細資訊，例如：`/q 2330`"
        )

    def _refresh_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀ 上一頁", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(content=self._build_content(), view=self)

    @discord.ui.button(label="下一頁 ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(content=self._build_content(), view=self)


# ════════════════════════════════════════════════════════
#  /q  查詢股票（代號或名稱關鍵字皆可）
# ════════════════════════════════════════════════════════


def _build_quote_embed(info: dict) -> discord.Embed:
    sym = info["symbol"]
    arrow = "🔺" if info["change"] >= 0 else "🔻"
    embed = discord.Embed(title="📊 股票查詢", color=discord.Color.blue())

    if info.get("is_index"):
        embed.add_field(
            name=f'{info["name"]}（{sym}）',
            value=(
                f'最新指數　`{info["price"]}`\n'
                f'漲跌　{arrow} `{info["change"]:+.2f}`\n'
                f'漲跌幅　{arrow} `{info["change_percent"]} %`'
            ),
            inline=True,
        )
    else:
        val_str = format_value(info["value"])
        embed.add_field(
            name=f'{info["name"]}（{sym}）',
            value=(
                f'最新價　`{info["price"]} 元`\n'
                f'漲跌　{arrow} `{info["change"]:+.2f} 元`\n'
                f'漲跌幅　{arrow} `{info["change_percent"]} %`\n'
                f'成交量　`{int(info["volume"])} 張`\n'
                f'成交額　`{val_str}`'
            ),
            inline=True,
        )
    return embed


@bot.tree.command(name="q", description="查詢股票即時報價（輸入代號或名稱關鍵字皆可）")
@app_commands.describe(query="股票代號（如 2330）或名稱關鍵字（如 台積電）")
async def cmd_quote(interaction: discord.Interaction, query: str):
    query = query.strip()
    if _looks_like_symbol(query):
        await interaction.response.defer()
        try:
            info = get_stock_info(query)
            await interaction.followup.send(embed=_build_quote_embed(info))
        except Exception as e:
            print(f"[WARN] /q {query} 查詢失敗：{e}")
            await interaction.followup.send(
                f"查無代號 `{query}`，請確認是否正確。\n"
                "也可以輸入公司名稱關鍵字，例如：`/q 台積電`"
            )
    else:
        await interaction.response.defer()
        try:
            df = search_by_name(query)
            if df.empty:
                await interaction.followup.send(f"找不到包含「{query}」的股票，請換個關鍵字試試！")
                return
            if len(df) == 1:
                info = get_stock_info(df.iloc[0]["symbol"])
                await interaction.followup.send(embed=_build_quote_embed(info))
            else:
                rows = df[["symbol", "name"]].to_dict("records")
                view = SearchPageView(query, rows)
                await interaction.followup.send(content=view._build_content(), view=view)
        except Exception as e:
            print(f"[WARN] /q 搜尋 {query} 失敗：{e}")
            await interaction.followup.send("搜尋時發生錯誤，請稍後再試！")


# ════════════════════════════════════════════════════════
#  /symbol  比較多檔股票
# ════════════════════════════════════════════════════════


@bot.tree.command(name="symbol", description="並排比較多檔股票或指數（最多 5 檔）")
@app_commands.describe(symbols="股票代號，以空格分隔，例如：2330 2454 0050")
async def cmd_compare(interaction: discord.Interaction, symbols: str):
    sym_list = symbols.split()
    if not sym_list:
        await interaction.response.send_message("請至少輸入一個股票代號，例如：`/symbol 2330 2454`")
        return
    if len(sym_list) > 5:
        await interaction.response.send_message("一次最多比較 5 檔，請重新輸入！")
        return

    await interaction.response.defer()
    index_rows, stock_rows, errors = [], [], []
    for sym in sym_list:
        try:
            info = get_stock_info(sym)
            if info.get("is_index"):
                index_rows.append({
                    "代號":    info["symbol"],
                    "名稱":    info["name"],
                    "最新指數": f"{info['price']:.2f}",
                    "漲跌":    f"{info['change']:.2f}",
                    "漲跌幅%": f"{info['change_percent']:.2f}",
                })
            else:
                stock_rows.append({
                    "代號":      info["symbol"],
                    "名稱":      info["name"],
                    "最新價":    f"{info['price']:.2f}",
                    "漲跌":      f"{info['change']:.2f}",
                    "漲跌幅%":   f"{info['change_percent']:.2f}",
                    "成交量(張)": int(info["volume"]),
                    "成交額":    format_value(info["value"]),
                })
        except Exception as e:
            print(f"[WARN] /symbol {sym} 查詢失敗：{e}")
            errors.append(sym.upper())

    sent_any = False
    if stock_rows:
        await interaction.followup.send(f"```{_format_table(stock_rows)}```")
        sent_any = True
    if index_rows:
        await interaction.followup.send(f"```{_format_table(index_rows)}```")
        sent_any = True
    if errors:
        await interaction.followup.send(f'⚠️ 以下代號查無資料：{", ".join(errors)}')
        sent_any = True
    if not sent_any:
        await interaction.followup.send("查無任何資料，請確認代號後再試。")


# ════════════════════════════════════════════════════════
#  /alert  價格到價警示
# ════════════════════════════════════════════════════════


alert_group = app_commands.Group(name="alert", description="價格到價警示管理")


@alert_group.command(name="set", description="設定到價提醒（自動判斷突破或跌破）")
@app_commands.describe(sym="股票代號，例如：2330", target="目標價格")
async def alert_set(interaction: discord.Interaction, sym: str, target: float):
    sym = sym.upper()
    await interaction.response.defer()
    try:
        info = get_stock_info(sym)
        cur  = info["price"]
    except Exception:
        await interaction.followup.send("查無此股票／指數，請確認代號！")
        return

    direction = "above" if target > cur else "below"
    dir_str   = f"突破 `{target}`" if direction == "above" else f"跌破 `{target}`"

    existing = [a for a in _db_list_alerts(interaction.user.id) if a["symbol"] == sym]
    if len(existing) >= 3:
        await interaction.followup.send(f"`{sym}` 警示已達上限（3 個），請先刪除後再設定。")
        return

    _db_add_alert(interaction.user.id, sym, target, direction)
    await interaction.followup.send(
        f"✅ 已設定警示！`{sym}` {dir_str} 時將 DM 通知您。\n"
        f"目前值：`{cur}`"
    )


@alert_group.command(name="list", description="查看我的價格警示清單")
async def alert_list(interaction: discord.Interaction):
    alerts = _db_list_alerts(interaction.user.id)
    if not alerts:
        await interaction.response.send_message("您目前沒有設定任何價格警示。")
        return
    lines = []
    for a in alerts:
        dir_str = "突破" if a["direction"] == "above" else "跌破"
        lines.append(f"**#{a['id']}**　`{a['symbol']}` {dir_str} `{a['target']}`")
    await interaction.response.send_message("📋 **您的價格警示清單**\n" + "\n".join(lines))


@alert_group.command(name="remove", description="刪除指定警示")
@app_commands.describe(alert_id="警示編號（用 /alert list 查詢）")
async def alert_remove(interaction: discord.Interaction, alert_id: int):
    if _db_remove_alert(alert_id, interaction.user.id):
        await interaction.response.send_message(f"🗑️ 已刪除警示 **#{alert_id}**。")
    else:
        await interaction.response.send_message(f"找不到警示 **#{alert_id}**，請用 `/alert list` 確認編號。")


# ════════════════════════════════════════════════════════
#  /watch  自選股管理
# ════════════════════════════════════════════════════════


watch_group = app_commands.Group(name="watch", description="自選股管理")


@watch_group.command(name="add", description="加入自選股（個股或指數，上限 10 檔）")
@app_commands.describe(sym="股票代號，例如：2330")
async def watch_add(interaction: discord.Interaction, sym: str):
    sym = sym.upper()
    uid = interaction.user.id
    state._watchlist.setdefault(uid, [])
    if sym in state._watchlist[uid]:
        await interaction.response.send_message(f"`{sym}` 已在您的自選股清單中！")
        return
    if len(state._watchlist[uid]) >= 10:
        await interaction.response.send_message("自選股上限為 10 檔，請先移除部分股票再新增。")
        return
    await interaction.response.defer()
    try:
        get_stock_info(sym)
    except Exception:
        await interaction.followup.send(f"查無代號 `{sym}`，請確認後再新增。")
        return
    state._watchlist[uid].append(sym)
    _db_add(uid, sym)
    await interaction.followup.send(f"✅ `{sym}` 已加入您的自選股！目前共 {len(state._watchlist[uid])} 檔。")


@watch_group.command(name="remove", description="移除自選股")
@app_commands.describe(sym="股票代號，例如：2330")
async def watch_remove(interaction: discord.Interaction, sym: str):
    sym = sym.upper()
    uid = interaction.user.id
    lst = state._watchlist.get(uid, [])
    if sym not in lst:
        await interaction.response.send_message(f"`{sym}` 不在您的自選股清單中！")
        return
    lst.remove(sym)
    _db_remove(uid, sym)
    await interaction.response.send_message(f"🗑️ `{sym}` 已從您的自選股移除。")


@watch_group.command(name="list", description="查看自選股即時報價")
async def watch_list(interaction: discord.Interaction):
    uid = interaction.user.id
    lst = state._watchlist.get(uid, [])
    if not lst:
        await interaction.response.send_message("您的自選股清單是空的，請使用 `/watch add 代號` 新增。")
        return

    await interaction.response.defer()
    embed  = discord.Embed(title="📋 我的自選股", color=discord.Color.blue())
    errors = []
    for sym in lst:
        try:
            info = get_stock_info(sym)
            arrow = "🔺" if info["change"] >= 0 else "🔻"

            if info.get("is_index"):
                embed.add_field(
                    name=f'{info["name"]}（{sym}）',
                    value=(
                        f'最新指數　`{info["price"]}`\n'
                        f'漲跌　{arrow} `{info["change"]:+.2f}`\n'
                        f'漲跌幅　{arrow} `{info["change_percent"]} %`'
                    ),
                    inline=True,
                )
            else:
                val_str = format_value(info["value"])
                embed.add_field(
                    name=f'{info["name"]}（{sym}）',
                    value=(
                        f'最新價　`{info["price"]} 元`\n'
                        f'漲跌　{arrow} `{info["change"]:+.2f} 元`\n'
                        f'漲跌幅　{arrow} `{info["change_percent"]} %`\n'
                        f'成交量　`{int(info["volume"])} 張`\n'
                        f'成交額　`{val_str}`'
                    ),
                    inline=True,
                )
        except Exception as e:
            print(f"[WARN] /watch list {sym} 查詢失敗：{e}")
            errors.append(sym)

    if embed.fields:
        await interaction.followup.send(embed=embed)
    if errors:
        await interaction.followup.send(f'⚠️ 以下代號查無資料：{", ".join(errors)}')


@watch_group.command(name="clear", description="清空自選股清單")
async def watch_clear(interaction: discord.Interaction):
    state._watchlist[interaction.user.id] = []
    _db_clear(interaction.user.id)
    await interaction.response.send_message("✅ 已清空您的自選股清單。")


# ════════════════════════════════════════════════════════
#  /trade  交易記錄與損益追蹤
# ════════════════════════════════════════════════════════


def _parse_date(date_str: str | None) -> str | None:
    """解析日期字串，回傳 YYYY-MM-DD；省略時回傳今日。"""
    if date_str is None:
        return date.today().isoformat()
    try:
        return date.fromisoformat(date_str).isoformat()
    except ValueError:
        return None


def _build_lifo_lots(txs: list[dict]) -> list[list]:
    """依歷史交易（不含本次）建立 LIFO 剩餘批次清單，回傳 [[shares, cost_per_share], ...]（舊→新）。"""
    sorted_txs = sorted(txs, key=lambda t: (t["date"], t.get("created_at", "")))
    lots: list[list] = []
    for tx in sorted_txs:
        if tx["type"] == "buy":
            cost_per_share = (tx["price"] * tx["shares"] + tx["fee"]) / tx["shares"]
            lots.append([tx["shares"], cost_per_share])
        elif tx["type"] == "sell":
            remaining = tx["shares"]
            while remaining > 0 and lots:
                if lots[-1][0] <= remaining:
                    remaining -= lots[-1][0]
                    lots.pop()
                else:
                    lots[-1][0] -= remaining
                    remaining = 0
    return lots


def _calc_sell_cost_and_new_avg(txs: list[dict], sell_shares: int) -> tuple[float, float]:
    """以 LIFO 計算賣出成本，並回傳賣出後剩餘持倉的新均攤成本。"""
    lots = _build_lifo_lots(txs)

    sell_cost = 0.0
    remaining = sell_shares
    for lot in reversed(lots):
        if remaining <= 0:
            break
        take = min(remaining, lot[0])
        sell_cost += take * lot[1]
        remaining -= take

    remaining = sell_shares
    for i in range(len(lots) - 1, -1, -1):
        if remaining <= 0:
            break
        if lots[i][0] <= remaining:
            remaining -= lots[i][0]
            lots[i][0] = 0
        else:
            lots[i][0] -= remaining
            remaining = 0

    remaining_lots = [lot for lot in lots if lot[0] > 0]
    if remaining_lots:
        total_shares = sum(lot[0] for lot in remaining_lots)
        new_avg = sum(lot[0] * lot[1] for lot in remaining_lots) / total_shares
    else:
        new_avg = 0.0

    return sell_cost, new_avg


trade_group = app_commands.Group(name="trade", description="交易記錄與損益追蹤")


@trade_group.command(name="buy", description="記錄買入交易（🔒 只有您自己看得到）")
@app_commands.describe(
    sym="股票代號，例如：2330",
    price="買入價格（元）",
    shares="買入股數",
    date_str="交易日期（格式 YYYY-MM-DD，省略預設今日）"
)
async def trade_buy(interaction: discord.Interaction, sym: str, price: float, shares: int, date_str: str = None):
    sym = sym.upper()
    uid = interaction.user.id

    if price <= 0:
        await interaction.response.send_message("買入價格必須大於 0。", ephemeral=True)
        return
    if shares <= 0:
        await interaction.response.send_message("買入股數必須大於 0。", ephemeral=True)
        return

    tx_date = _parse_date(date_str)
    if tx_date is None:
        await interaction.response.send_message("日期格式錯誤，請使用 `YYYY-MM-DD`，例如 `2025-05-25`。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        get_stock_info(sym)
    except Exception:
        await interaction.followup.send(f"查無代號 `{sym}`，請確認後再試。", ephemeral=True)
        return

    fee = calculate_fee(price, shares)
    pos = _db_get_position(uid, sym)

    if pos is None or pos["shares"] == 0:
        new_avg = (price * shares + fee) / shares
        new_shares = shares
        realized = pos["realized_pnl"] if pos else 0.0
    else:
        old_cost_total = pos["avg_cost"] * pos["shares"]
        new_shares = pos["shares"] + shares
        new_avg = (old_cost_total + price * shares + fee) / new_shares
        realized = pos["realized_pnl"]

    _db_add_transaction(uid, sym, "buy", price, shares, tx_date, fee, 0)
    _db_upsert_position(uid, sym, new_avg, new_shares, realized)

    await interaction.followup.send(
        f"✅ **買入成功**　`{sym}`\n"
        f"買入股數　`{shares:,} 股` @ `{price:,.2f} 元`\n"
        f"手續費　　`{fee:,} 元`\n"
        f"均攤成本　`{new_avg:,.4f} 元/股`\n"
        f"目前持股　`{new_shares:,} 股`　（交易日期：{tx_date}）",
        ephemeral=True,
    )


@trade_group.command(name="sell", description="記錄賣出交易（自動計算當沖稅率）（🔒 只有您自己看得到）")
@app_commands.describe(
    sym="股票代號，例如：2330",
    price="賣出價格（元）",
    shares="賣出股數",
    date_str="交易日期（格式 YYYY-MM-DD，省略預設今日）"
)
async def trade_sell(interaction: discord.Interaction, sym: str, price: float, shares: int, date_str: str = None):
    sym = sym.upper()
    uid = interaction.user.id

    if price <= 0:
        await interaction.response.send_message("賣出價格必須大於 0。", ephemeral=True)
        return
    if shares <= 0:
        await interaction.response.send_message("賣出股數必須大於 0。", ephemeral=True)
        return

    pos = _db_get_position(uid, sym)
    if pos is None or pos["shares"] == 0:
        await interaction.response.send_message(f"您目前沒有 `{sym}` 的持倉，無法賣出。", ephemeral=True)
        return
    if shares > pos["shares"]:
        await interaction.response.send_message(
            f"賣出股數（{shares:,}）超過目前持股（{pos['shares']:,}），請確認後再試。",
            ephemeral=True,
        )
        return

    tx_date = _parse_date(date_str)
    if tx_date is None:
        await interaction.response.send_message("日期格式錯誤，請使用 `YYYY-MM-DD`，例如 `2025-05-25`。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        info = get_stock_info(sym)
        is_etf = "ETF" in info["name"].upper()
    except Exception:
        is_etf = False

    txs = _db_list_transactions(uid, sym)
    is_daytrade = any(t["type"] == "buy" and t["date"] == tx_date for t in txs)

    fee = calculate_fee(price, shares)
    tax = calculate_tax(price, shares, is_etf, is_daytrade)
    net_proceeds = price * shares - fee - tax
    sell_cost, new_avg = _calc_sell_cost_and_new_avg(txs, shares)
    this_pnl = net_proceeds - sell_cost

    new_shares = pos["shares"] - shares
    new_realized = pos["realized_pnl"] + this_pnl

    _db_add_transaction(uid, sym, "sell", price, shares, tx_date, fee, tax)
    _db_upsert_position(uid, sym, new_avg, new_shares, new_realized)

    if is_etf and is_daytrade:
        tax_label = "ETF 當沖 0.05%"
    elif is_etf:
        tax_label = "ETF 0.1%"
    elif is_daytrade:
        tax_label = "現股當沖 0.15%"
    else:
        tax_label = "一般股票 0.3%"

    pnl_sign = "+" if this_pnl >= 0 else ""
    pnl_pct = this_pnl / sell_cost * 100 if sell_cost > 0 else 0

    msg = (
        f"✅ **賣出成功**　`{sym}`\n"
        f"賣出股數　`{shares:,} 股` @ `{price:,.2f} 元`\n"
        f"手續費　　`{fee:,} 元`\n"
        f"證交稅　　`{tax:,} 元`（{tax_label}）\n"
        f"本次損益　`{pnl_sign}{this_pnl:,.0f} 元`（{pnl_sign}{pnl_pct:.2f}%）\n"
        f"剩餘持股　`{new_shares:,} 股`　（交易日期：{tx_date}）"
    )
    if is_daytrade:
        msg += "\n⚡ **偵測到當沖交易**，已套用減半稅率。"
    await interaction.followup.send(msg, ephemeral=True)


@trade_group.command(name="profit", description="查看持倉損益（🔒 只有您自己看得到）")
@app_commands.describe(sym="股票代號（省略顯示全部持倉摘要）")
async def trade_profit(interaction: discord.Interaction, sym: str = None):
    uid = interaction.user.id

    if sym is None:
        positions = _db_list_positions(uid)
        if not positions:
            await interaction.response.send_message(
                "您目前沒有任何持倉紀錄，請用 `/trade buy 代號 價格 股數` 開始記錄。",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="📊 我的持倉損益摘要", color=discord.Color.gold())

        for p in positions:
            s = p["symbol"]
            field_name = s
            if p["shares"] > 0:
                try:
                    info = get_stock_info(s)
                    cur = info["price"]
                    field_name = f'{info["name"]}（{s}）'
                    unreal_pnl = (cur - p["avg_cost"]) * p["shares"]
                    unreal_pct = unreal_pnl / (p["avg_cost"] * p["shares"]) * 100
                    sign = "+" if unreal_pnl >= 0 else ""
                    arrow = "🔺" if unreal_pnl >= 0 else "🔻"
                    field_val = (
                        f'持股　`{p["shares"]:,} 股`\n'
                        f'均攤成本　`{p["avg_cost"]:,.2f} 元`\n'
                        f'現價　`{cur:,.2f} 元`\n'
                        f'未實現損益　{arrow} `{sign}{unreal_pnl:,.0f} 元`（{sign}{unreal_pct:.2f}%）'
                    )
                    if p["realized_pnl"] != 0:
                        r_sign = "+" if p["realized_pnl"] >= 0 else ""
                        field_val += f'\n已實現損益　`{r_sign}{p["realized_pnl"]:,.0f} 元`'
                except Exception:
                    field_val = f'持股　`{p["shares"]:,} 股`\n⚠️ 無法取得即時報價'
            else:
                try:
                    info = get_stock_info(s)
                    field_name = f'{info["name"]}（{s}）'
                except Exception:
                    pass
                r_sign = "+" if p["realized_pnl"] >= 0 else ""
                field_val = (
                    f'🏁 已清倉\n'
                    f'已實現損益　`{r_sign}{p["realized_pnl"]:,.0f} 元`'
                )
            embed.add_field(name=field_name, value=field_val, inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    else:
        sym = sym.upper()
        pos = _db_get_position(uid, sym)
        if pos is None or (pos["shares"] == 0 and pos["realized_pnl"] == 0):
            await interaction.response.send_message(
                f"`{sym}` 無持倉紀錄，請先使用 `/trade buy {sym} 價格 股數`。",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            _pre_info = get_stock_info(sym)
            sym_title = f'{_pre_info["name"]}（{sym}）'
        except Exception:
            _pre_info = None
            sym_title = sym

        embed = discord.Embed(title=f"📊 {sym_title} 損益詳情", color=discord.Color.gold())

        if pos["shares"] > 0:
            try:
                info = _pre_info if _pre_info is not None else get_stock_info(sym)
                cur = info["price"]
                is_etf = "ETF" in info["name"].upper()
                cost_total = pos["avg_cost"] * pos["shares"]
                sell_fee = calculate_fee(cur, pos["shares"])
                sell_tax = calculate_tax(cur, pos["shares"], is_etf, False)
                net = cur * pos["shares"] - sell_fee - sell_tax
                unreal_pnl = net - cost_total
                unreal_pct = unreal_pnl / cost_total * 100
                sign = "+" if unreal_pnl >= 0 else ""
                arrow = "🔺" if unreal_pnl >= 0 else "🔻"

                embed.add_field(name="買入資訊", value=(
                    f'均攤成本　`{pos["avg_cost"]:,.4f} 元/股`\n'
                    f'持股股數　`{pos["shares"]:,} 股`\n'
                    f'總成本　　`{cost_total:,.0f} 元`'
                ), inline=False)

                embed.add_field(name="當前估值（若現在賣出）", value=(
                    f'現價　　　`{cur:,.2f} 元`\n'
                    f'市值　　　`{cur * pos["shares"]:,.0f} 元`\n'
                    f'預估手續費　`{sell_fee:,} 元`\n'
                    f'預估證交稅　`{sell_tax:,} 元`（{"ETF 0.1%" if is_etf else "股票 0.3%"}）\n'
                    f'預估淨收益　`{net:,.0f} 元`'
                ), inline=False)

                embed.add_field(name="未實現損益", value=(
                    f'{arrow} `{sign}{unreal_pnl:,.0f} 元`（{sign}{unreal_pct:.2f}%）'
                ), inline=True)
            except Exception as e:
                embed.add_field(name="⚠️ 無法取得即時報價", value=str(e), inline=False)

        if pos["realized_pnl"] != 0 or pos["shares"] == 0:
            r_sign = "+" if pos["realized_pnl"] >= 0 else ""
            embed.add_field(name="已實現損益（歷史）", value=(
                f'`{r_sign}{pos["realized_pnl"]:,.0f} 元`'
            ), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)


@trade_group.command(name="history", description="查看交易明細（🔒 只有您自己看得到）")
@app_commands.describe(sym="股票代號（省略顯示全部）")
async def trade_history(interaction: discord.Interaction, sym: str = None):
    uid = interaction.user.id
    await interaction.response.defer(ephemeral=True)

    if sym is None:
        txs = _db_list_all_transactions(uid)
        if not txs:
            await interaction.followup.send("您目前沒有任何交易紀錄。", ephemeral=True)
            return
        shown = txs[:20]
        title = f"📋 全部交易明細（共 {len(txs)} 筆{'，顯示最近 20 筆' if len(txs) > 20 else ''}）"
        unique_syms = list({t["symbol"] for t in shown})
        sym_names: dict[str, str] = {}
        for _s in unique_syms:
            try:
                sym_names[_s] = get_stock_info(_s)["name"]
            except Exception:
                sym_names[_s] = _s
    else:
        sym = sym.upper()
        txs = _db_list_transactions(uid, sym)
        if not txs:
            await interaction.followup.send(f"`{sym}` 尚無交易紀錄。", ephemeral=True)
            return
        shown = txs[:20]
        try:
            sym_display = f'{get_stock_info(sym)["name"]}（{sym}）'
        except Exception:
            sym_display = sym
        title = f"📋 {sym_display} 交易明細（共 {len(txs)} 筆{'，顯示最近 20 筆' if len(txs) > 20 else ''}）"
        sym_names = {}

    embed = discord.Embed(title=title, color=discord.Color.blue())
    for t in shown:
        type_str = "買入" if t["type"] == "buy" else "賣出"
        tax_str  = f'`{t["tax"]:,} 元`' if t["tax"] else "`—`"
        if sym is None:
            _name = sym_names.get(t["symbol"], t["symbol"])
            field_name = f'{t["date"]}　{_name}（{t["symbol"]}）　{type_str}'
        else:
            field_name = f'{t["date"]}　{type_str}'
        embed.add_field(
            name=field_name,
            value=(
                f'價格　`{t["price"]:,.2f} 元`　'
                f'股數　`{t["shares"]:,}`　'
                f'手續費　`{t["fee"]:,} 元`　'
                f'稅　{tax_str}'
            ),
            inline=False,
        )
    await interaction.followup.send(embed=embed, ephemeral=True)


class _ConfirmResetView(discord.ui.View):
    def __init__(self, uid: int, sym: str | None):
        super().__init__(timeout=30)
        self.uid = uid
        self.sym = sym

    @discord.ui.button(label="確認清除", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("這不是您的操作！", ephemeral=True)
            return
        if self.sym is None:
            _db_remove_all_positions(self.uid)
            msg = "✅ 已清除您所有股票的交易紀錄與持倉資料。"
        else:
            _db_remove_position(self.uid, self.sym)
            msg = f"✅ 已清除 `{self.sym}` 的所有交易紀錄與持倉資料。"
        self.stop()
        await interaction.response.edit_message(content=msg, view=None)

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("這不是您的操作！", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content="已取消清除。", view=None)


@trade_group.command(name="reset", description="清除指定股票（或全部）的交易紀錄與持倉")
@app_commands.describe(sym="股票代號（省略則清除所有股票）")
async def trade_reset(interaction: discord.Interaction, sym: str = None):
    uid = interaction.user.id

    if sym is None:
        positions = _db_list_positions(uid)
        if not positions:
            await interaction.response.send_message("您目前沒有任何交易紀錄可清除。")
            return
        total_txs = sum(len(_db_list_transactions(uid, p["symbol"])) for p in positions)
        view = _ConfirmResetView(uid, None)
        await interaction.response.send_message(
            f"⚠️ 確定要清除您 **所有股票**（共 {len(positions)} 檔）的持倉與 {total_txs} 筆交易紀錄？\n"
            "**此操作無法復原。**",
            view=view,
        )
    else:
        sym = sym.upper()
        pos = _db_get_position(uid, sym)
        txs = _db_list_transactions(uid, sym)
        if pos is None and not txs:
            await interaction.response.send_message(f"`{sym}` 沒有任何交易紀錄可清除。")
            return
        view = _ConfirmResetView(uid, sym)
        await interaction.response.send_message(
            f"⚠️ 確定要清除 `{sym}` 的所有持倉與 {len(txs)} 筆交易紀錄？\n"
            "**此操作無法復原。**",
            view=view,
        )


# ════════════════════════════════════════════════════════
#  /sector  產業類別查詢
# ════════════════════════════════════════════════════════


class SectorPageView(discord.ui.View):
    PAGE_SIZE = 15

    def __init__(self, sector_name: str, stocks: list[dict]):
        super().__init__(timeout=120)
        self.sector_name = sector_name
        self.stocks = stocks
        self.page = 0
        self.total_pages = max(1, -(-len(stocks) // self.PAGE_SIZE))
        self._refresh_buttons()

    def _build_content(self) -> str:
        start = self.page * self.PAGE_SIZE
        chunk = self.stocks[start: start + self.PAGE_SIZE]
        lines = "代號　　名稱　　　　市場\n" + "─" * 28 + "\n"
        lines += "\n".join(
            f"`{s['symbol']}`　{s['name']}　({s['market']})" for s in chunk
        )
        return (
            f"🏭 **{self.sector_name}　共 {len(self.stocks)} 檔**　"
            f"（第 {self.page + 1} / {self.total_pages} 頁）\n"
            f"{lines}\n\n"
            "輸入 `/q 代號` 查詢詳細資訊，例如：`/q 2330`"
        )

    def _refresh_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀ 上一頁", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._refresh_buttons()
        await interaction.response.edit_message(content=self._build_content(), view=self)

    @discord.ui.button(label="下一頁 ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._refresh_buttons()
        await interaction.response.edit_message(content=self._build_content(), view=self)


sector_group = app_commands.Group(name="sector", description="產業類別查詢")


@sector_group.command(name="list", description="列出所有產業類別及股票數量")
async def sector_list(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = get_sector_data()
    except Exception as e:
        print(f"[WARN] /sector list 查詢失敗：{e}")
        await interaction.followup.send("產業分類資料載入失敗，請稍後再試！")
        return

    if not data:
        await interaction.followup.send("目前無法取得產業分類資料，請稍後再試！")
        return

    sorted_sectors = sorted(data.items(), key=lambda x: x[0])
    lines = [f"• **{name}**　{len(stocks)} 檔" for name, stocks in sorted_sectors]

    total_stocks = sum(len(v) for v in data.values())
    header = f"🏭 **產業類別總覽**（共 {len(data)} 個類別、{total_stocks} 檔股票）\n\n"
    footer = "\n\n輸入 `/sector search 類別名稱` 查看該產業股票，例如：`/sector search 半導體業`"
    content = header + "\n".join(lines) + footer

    if len(content) <= 2000:
        await interaction.followup.send(content)
    else:
        chunks, current = [], header
        for line in lines:
            if len(current) + len(line) + 1 > 1900:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            current += footer
            chunks.append(current)
        for chunk in chunks:
            await interaction.followup.send(chunk)


@sector_group.command(name="search", description="查詢指定產業的所有股票（支援翻頁）")
@app_commands.describe(category="產業名稱，例如：半導體業、ETF")
async def sector_search(interaction: discord.Interaction, category: str):
    await interaction.response.defer()
    try:
        data = get_sector_data()
    except Exception as e:
        print(f"[WARN] /sector search 查詢失敗：{e}")
        await interaction.followup.send("產業分類資料載入失敗，請稍後再試！")
        return

    if not data:
        await interaction.followup.send("目前無法取得產業分類資料，請稍後再試！")
        return

    if category in data:
        stocks = data[category]
        view = SectorPageView(category, stocks)
        await interaction.followup.send(content=view._build_content(), view=view)
        return

    matches = [name for name in data if category.lower() in name.lower()]
    if len(matches) == 1:
        stocks = data[matches[0]]
        view = SectorPageView(matches[0], stocks)
        await interaction.followup.send(content=view._build_content(), view=view)
    elif len(matches) > 1:
        lines = "\n".join(f"• {name}（{len(data[name])} 檔）" for name in sorted(matches))
        await interaction.followup.send(
            f"🔍 找到 {len(matches)} 個相關產業類別：\n{lines}\n\n"
            "請輸入完整類別名稱查詢，例如：`/sector search 半導體業`"
        )
    else:
        await interaction.followup.send(
            f"找不到「{category}」相關的產業類別。\n"
            "請使用 `/sector list` 查看所有可用類別。"
        )


# ════════════════════════════════════════════════════════
#  /menu  顯示所有指令說明
# ════════════════════════════════════════════════════════


@bot.tree.command(name="menu", description="顯示所有指令說明")
async def cmd_menu(interaction: discord.Interaction):
    msg = (
        "📖 **股票 Bot 指令說明**\n"
        "```\n"
        "【查詢】\n"
        "/q 2330                    輸入代號 → 直接查即時報價\n"
        "/q 台積電                   輸入名稱 → 自動搜尋符合股票\n"
        "                           指數代號：IX0001（加權）IX0002（櫃買）\n"
        "/symbol 代號1 代號2 …      比較多檔股票或指數（最多 5 個）\n\n"
        "【警示設定】\n"
        "/alert set 代號 數值       設定到價提醒（個股或指數皆可）\n"
        "/alert list                查看我的警示清單\n"
        "/alert remove 編號         刪除指定警示\n\n"
        "【自選股】\n"
        "/watch add 代號            加入自選股（個股或指數，上限 10 檔）\n"
        "/watch remove 代號         移除自選股\n"
        "/watch list                查看自選股即時報價\n"
        "/watch clear               清空自選股\n\n"
        "【交易記錄與損益】\n"
        "/trade buy 代號 價格 股數  買入記錄 🔒（只有您看得到，可選填日期 YYYY-MM-DD）\n"
        "/trade sell 代號 價格 股數 賣出記錄 🔒（只有您看得到，自動計算手續費/當沖稅率）\n"
        "/trade profit [代號]       查看損益 🔒 只有您看得到\n"
        "/trade history [代號]      查看交易明細 🔒 只有您看得到\n"
        "/trade reset [代號]        清除交易紀錄\n\n"
        "【產業類別】\n"
        "/sector list               列出所有產業類別（含股票數量）\n"
        "/sector search 半導體業    查詢該產業所有股票（支援翻頁）\n"
        "/sector search ETF         查看所有 ETF\n"
        "```\n"
        "📡 **自動推播功能**\n"
        "```\n"
        "09:00      開盤晨報（最新 5 則財經新聞）\n"
        "每 1 分鐘  財經＋國際新聞即時推播（全天候）\n"
        "每 2 分鐘  到價警示掃描（盤中，觸發後於警示頻道 @mention 通知）\n"
        "每 5 分鐘  重大新聞即時警示掃描（盤中）\n"
        "每 5 分鐘  自選股大幅波動警示（漲跌 ±3%，於警示頻道 @mention 通知）\n"
        "13:30      收盤總整理（最新 5 則財經新聞）\n"
        "週五 14:00 自選股績效週報（於警示頻道 @mention 通知）\n"
        "```"
    )
    await interaction.response.send_message(msg)


# ════════════════════════════════════════════════════════
#  向 bot.tree 註冊所有 slash command group
# ════════════════════════════════════════════════════════

bot.tree.add_command(alert_group)
bot.tree.add_command(watch_group)
bot.tree.add_command(trade_group)
bot.tree.add_command(sector_group)
