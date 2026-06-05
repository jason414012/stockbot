import discord
from discord import app_commands

from ..config import HISTORY_DISPLAY_LIMIT
from ..data import get_stock_info
from ..db import (
    get_position,
    list_all_transactions,
    list_positions,
    list_transactions,
    remove_all_positions,
    remove_position,
)
from ..domain.trading import calculate_fee, calculate_tax, parse_trade_date
from ..services.portfolio_service import (
    NoPositionError,
    OversellError,
    UnknownSymbolError,
    record_buy,
    record_sell,
)


trade_group = app_commands.Group(name="trade", description="交易記錄與損益追蹤")


@trade_group.command(name="buy", description="記錄買入交易（🔒 只有您自己看得到）")
@app_commands.describe(
    sym="股票代號，例如：2330",
    price="買入價格（元）",
    shares="買入股數",
    date_str="交易日期（格式 YYYY-MM-DD，省略預設今日）",
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

    tx_date = parse_trade_date(date_str)
    if tx_date is None:
        await interaction.response.send_message("日期格式錯誤，請使用 `YYYY-MM-DD`，例如 `2025-05-25`。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        result = record_buy(uid, sym, price, shares, tx_date)
    except UnknownSymbolError:
        await interaction.followup.send(f"查無代號 `{sym}`，請確認後再試。", ephemeral=True)
        return

    position = result.position
    await interaction.followup.send(
        f"✅ **買入成功**　`{sym}`\n"
        f"買入股數　`{shares:,} 股` @ `{price:,.2f} 元`\n"
        f"手續費　　`{position.fee:,} 元`\n"
        f"均攤成本　`{position.avg_cost:,.4f} 元/股`\n"
        f"目前持股　`{position.shares:,} 股`　（交易日期：{result.date}）",
        ephemeral=True,
    )


@trade_group.command(name="sell", description="記錄賣出交易（自動計算當沖稅率）（🔒 只有您自己看得到）")
@app_commands.describe(
    sym="股票代號，例如：2330",
    price="賣出價格（元）",
    shares="賣出股數",
    date_str="交易日期（格式 YYYY-MM-DD，省略預設今日）",
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

    tx_date = parse_trade_date(date_str)
    if tx_date is None:
        await interaction.response.send_message("日期格式錯誤，請使用 `YYYY-MM-DD`，例如 `2025-05-25`。", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        result = record_sell(uid, sym, price, shares, tx_date)
    except NoPositionError:
        await interaction.followup.send(f"您目前沒有 `{sym}` 的持倉，無法賣出。", ephemeral=True)
        return
    except OversellError as e:
        await interaction.followup.send(
            f"賣出股數（{e.requested:,}）超過目前持股（{e.available:,}），請確認後再試。",
            ephemeral=True,
        )
        return

    position = result.position
    pnl_sign = "+" if position.pnl >= 0 else ""
    msg = (
        f"✅ **賣出成功**　`{sym}`\n"
        f"賣出股數　`{shares:,} 股` @ `{price:,.2f} 元`\n"
        f"手續費　　`{position.fee:,} 元`\n"
        f"證交稅　　`{position.tax:,} 元`（{position.tax_label}）\n"
        f"本次損益　`{pnl_sign}{position.pnl:,.0f} 元`（{pnl_sign}{position.pnl_pct:.2f}%）\n"
        f"剩餘持股　`{position.shares:,} 股`　（交易日期：{result.date}）"
    )
    if position.is_daytrade:
        msg += "\n⚡ **偵測到當沖交易**，已套用減半稅率。"
    await interaction.followup.send(msg, ephemeral=True)


@trade_group.command(name="profit", description="查看持倉損益（🔒 只有您自己看得到）")
@app_commands.describe(sym="股票代號（省略顯示全部持倉摘要）")
async def trade_profit(interaction: discord.Interaction, sym: str = None):
    uid = interaction.user.id

    if sym is None:
        positions = list_positions(uid)
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
                    f"🏁 已清倉\n"
                    f'已實現損益　`{r_sign}{p["realized_pnl"]:,.0f} 元`'
                )
            embed.add_field(name=field_name, value=field_val, inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    sym = sym.upper()
    pos = get_position(uid, sym)
    if pos is None or (pos["shares"] == 0 and pos["realized_pnl"] == 0):
        await interaction.response.send_message(
            f"`{sym}` 無持倉紀錄，請先使用 `/trade buy {sym} 價格 股數`。",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    try:
        pre_info = get_stock_info(sym)
        sym_title = f'{pre_info["name"]}（{sym}）'
    except Exception:
        pre_info = None
        sym_title = sym

    embed = discord.Embed(title=f"📊 {sym_title} 損益詳情", color=discord.Color.gold())

    if pos["shares"] > 0:
        try:
            info = pre_info if pre_info is not None else get_stock_info(sym)
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
        txs = list_all_transactions(uid)
        if not txs:
            await interaction.followup.send("您目前沒有任何交易紀錄。", ephemeral=True)
            return
        shown = txs[:HISTORY_DISPLAY_LIMIT]
        title = f"📋 全部交易明細（共 {len(txs)} 筆{'，顯示最近 %d 筆' % HISTORY_DISPLAY_LIMIT if len(txs) > HISTORY_DISPLAY_LIMIT else ''}）"
        unique_syms = list({t["symbol"] for t in shown})
        sym_names: dict[str, str] = {}
        for item_sym in unique_syms:
            try:
                sym_names[item_sym] = get_stock_info(item_sym)["name"]
            except Exception:
                sym_names[item_sym] = item_sym
    else:
        sym = sym.upper()
        txs = list_transactions(uid, sym)
        if not txs:
            await interaction.followup.send(f"`{sym}` 尚無交易紀錄。", ephemeral=True)
            return
        shown = txs[:HISTORY_DISPLAY_LIMIT]
        try:
            sym_display = f'{get_stock_info(sym)["name"]}（{sym}）'
        except Exception:
            sym_display = sym
        title = f"📋 {sym_display} 交易明細（共 {len(txs)} 筆{'，顯示最近 %d 筆' % HISTORY_DISPLAY_LIMIT if len(txs) > HISTORY_DISPLAY_LIMIT else ''}）"
        sym_names = {}

    embed = discord.Embed(title=title, color=discord.Color.blue())
    for t in shown:
        type_str = "買入" if t["type"] == "buy" else "賣出"
        tax_str = f'`{t["tax"]:,} 元`' if t["tax"] else "`—`"
        if sym is None:
            item_name = sym_names.get(t["symbol"], t["symbol"])
            field_name = f'{t["date"]}　{item_name}（{t["symbol"]}）　{type_str}'
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


class ConfirmResetView(discord.ui.View):
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
            remove_all_positions(self.uid)
            msg = "✅ 已清除您所有股票的交易紀錄與持倉資料。"
        else:
            remove_position(self.uid, self.sym)
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
        positions = list_positions(uid)
        if not positions:
            await interaction.response.send_message("您目前沒有任何交易紀錄可清除。")
            return
        total_txs = sum(len(list_transactions(uid, p["symbol"])) for p in positions)
        view = ConfirmResetView(uid, None)
        await interaction.response.send_message(
            f"⚠️ 確定要清除您 **所有股票**（共 {len(positions)} 檔）的持倉與 {total_txs} 筆交易紀錄？\n"
            "**此操作無法復原。**",
            view=view,
        )
    else:
        sym = sym.upper()
        pos = get_position(uid, sym)
        txs = list_transactions(uid, sym)
        if pos is None and not txs:
            await interaction.response.send_message(f"`{sym}` 沒有任何交易紀錄可清除。")
            return
        view = ConfirmResetView(uid, sym)
        await interaction.response.send_message(
            f"⚠️ 確定要清除 `{sym}` 的所有持倉與 {len(txs)} 筆交易紀錄？\n"
            "**此操作無法復原。**",
            view=view,
        )
