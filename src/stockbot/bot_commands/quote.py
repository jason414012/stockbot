import logging

import discord
from discord import app_commands

from ..config import MAX_COMPARE_SYMBOLS, PAGE_SIZE
from ..data import format_value, get_stock_info, search_by_name
from ..display import format_table
from ..state import bot

from .common import PageView, build_quote_embed, looks_like_symbol

logger = logging.getLogger(__name__)


class SearchPageView(PageView):
    def __init__(self, keyword: str, rows: list[dict]):
        self.keyword = keyword
        self.rows = rows
        super().__init__(len(rows))

    def _build_content(self) -> str:
        start = self.page * PAGE_SIZE
        chunk = self.rows[start: start + PAGE_SIZE]
        lines = "代號　　名稱\n" + "─" * 20 + "\n"
        lines += "\n".join(f"`{r['symbol']}`　{r['name']}" for r in chunk)
        return (
            f"🔍 **「{self.keyword}」共 {len(self.rows)} 筆結果**　"
            f"（第 {self.page + 1} / {self.total_pages} 頁）\n"
            f"{lines}\n\n"
            "輸入 `/q 代號` 查詢詳細資訊，例如：`/q 2330`"
        )


@bot.tree.command(name="q", description="查詢股票即時報價（輸入代號或名稱關鍵字皆可）")
@app_commands.describe(query="股票代號（如 2330）或名稱關鍵字（如 台積電）")
async def cmd_quote(interaction: discord.Interaction, query: str):
    query = query.strip()
    if looks_like_symbol(query):
        await interaction.response.defer()
        try:
            info = get_stock_info(query)
            await interaction.followup.send(embed=build_quote_embed(info))
        except Exception as e:
            logger.warning("/q %s 查詢失敗：%s", query, e)
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
                await interaction.followup.send(embed=build_quote_embed(info))
            else:
                rows = df[["symbol", "name"]].to_dict("records")
                view = SearchPageView(query, rows)
                await interaction.followup.send(content=view._build_content(), view=view)
        except Exception as e:
            logger.warning("/q 搜尋 %s 失敗：%s", query, e)
            await interaction.followup.send("搜尋時發生錯誤，請稍後再試！")


@bot.tree.command(name="symbol", description="並排比較多檔股票或指數（最多 5 檔）")
@app_commands.describe(symbols="股票代號，以空格分隔，例如：2330 2454 0050")
async def cmd_compare(interaction: discord.Interaction, symbols: str):
    sym_list = symbols.split()
    if not sym_list:
        await interaction.response.send_message("請至少輸入一個股票代號，例如：`/symbol 2330 2454`")
        return
    if len(sym_list) > MAX_COMPARE_SYMBOLS:
        await interaction.response.send_message(f"一次最多比較 {MAX_COMPARE_SYMBOLS} 檔，請重新輸入！")
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
                    "成交量(張)": int(info["volume"] or 0),
                    "成交額":    format_value(info["value"] or 0),
                })
        except Exception as e:
            logger.warning("/symbol %s 查詢失敗：%s", sym, e)
            errors.append(sym.upper())

    sent_any = False
    if stock_rows:
        await interaction.followup.send(f"```{format_table(stock_rows)}```")
        sent_any = True
    if index_rows:
        await interaction.followup.send(f"```{format_table(index_rows)}```")
        sent_any = True
    if errors:
        await interaction.followup.send(f'⚠️ 以下代號查無資料：{", ".join(errors)}')
        sent_any = True
    if not sent_any:
        await interaction.followup.send("查無任何資料，請確認代號後再試。")
