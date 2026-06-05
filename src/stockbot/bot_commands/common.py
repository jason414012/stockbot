import re

import discord

from ..config import PAGE_SIZE
from ..data import format_value
from ..market_types import QuoteInfo


def looks_like_symbol(text: str) -> bool:
    """純數字（個股代號）或 IX 開頭（指數代號）視為代號，其餘視為關鍵字。"""
    return bool(re.fullmatch(r"\d+", text) or re.fullmatch(r"IX\d+", text, re.IGNORECASE))


class PageView(discord.ui.View):
    """分頁按鈕基底類別，子類別只需實作 _build_content()。"""

    def __init__(self, total_items: int):
        super().__init__(timeout=120)
        self.page = 0
        self.total_pages = max(1, -(-total_items // PAGE_SIZE))
        self._refresh_buttons()

    def _build_content(self) -> str:
        raise NotImplementedError

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


def add_quote_field(embed: discord.Embed, info: QuoteInfo):
    sym = info["symbol"]
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
        val_str = format_value(info["value"] or 0)
        embed.add_field(
            name=f'{info["name"]}（{sym}）',
            value=(
                f'最新價　`{info["price"]} 元`\n'
                f'漲跌　{arrow} `{info["change"]:+.2f} 元`\n'
                f'漲跌幅　{arrow} `{info["change_percent"]} %`\n'
                f'成交量　`{int(info["volume"] or 0)} 張`\n'
                f'成交額　`{val_str}`'
            ),
            inline=True,
        )


def build_quote_embed(info: QuoteInfo) -> discord.Embed:
    embed = discord.Embed(title="📊 股票查詢", color=discord.Color.blue())
    add_quote_field(embed, info)
    return embed
