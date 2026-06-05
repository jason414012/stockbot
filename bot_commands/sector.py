import logging

import discord
from discord import app_commands

from config import PAGE_SIZE
from data import get_sector_data

from .common import PageView

logger = logging.getLogger(__name__)


class SectorPageView(PageView):
    def __init__(self, sector_name: str, stocks: list[dict]):
        self.sector_name = sector_name
        self.stocks = stocks
        super().__init__(len(stocks))

    def _build_content(self) -> str:
        start = self.page * PAGE_SIZE
        chunk = self.stocks[start: start + PAGE_SIZE]
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


sector_group = app_commands.Group(name="sector", description="產業類別查詢")


@sector_group.command(name="list", description="列出所有產業類別及股票數量")
async def sector_list(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        data = get_sector_data()
    except Exception as e:
        logger.warning("/sector list 查詢失敗：%s", e)
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
        logger.warning("/sector search 查詢失敗：%s", e)
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
