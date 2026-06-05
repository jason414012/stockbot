import logging

import discord
from discord import app_commands

from .. import state
from ..config import MAX_WATCHLIST_SIZE
from ..data import get_stock_info
from ..db import add_watchlist, clear_watchlist, remove_watchlist

from .common import add_quote_field

logger = logging.getLogger(__name__)

watch_group = app_commands.Group(name="watch", description="自選股管理")


@watch_group.command(name="add", description="加入自選股（個股或指數，上限 10 檔）")
@app_commands.describe(sym="股票代號，例如：2330")
async def watch_add(interaction: discord.Interaction, sym: str):
    sym = sym.upper()
    uid = interaction.user.id
    state.watchlist.setdefault(uid, [])
    if sym in state.watchlist[uid]:
        await interaction.response.send_message(f"`{sym}` 已在您的自選股清單中！")
        return
    if len(state.watchlist[uid]) >= MAX_WATCHLIST_SIZE:
        await interaction.response.send_message(f"自選股上限為 {MAX_WATCHLIST_SIZE} 檔，請先移除部分股票再新增。")
        return
    await interaction.response.defer()
    try:
        get_stock_info(sym)
    except Exception:
        await interaction.followup.send(f"查無代號 `{sym}`，請確認後再新增。")
        return
    state.watchlist[uid].append(sym)
    add_watchlist(uid, sym)
    await interaction.followup.send(f"✅ `{sym}` 已加入您的自選股！目前共 {len(state.watchlist[uid])} 檔。")


@watch_group.command(name="remove", description="移除自選股")
@app_commands.describe(sym="股票代號，例如：2330")
async def watch_remove(interaction: discord.Interaction, sym: str):
    sym = sym.upper()
    uid = interaction.user.id
    lst = state.watchlist.get(uid, [])
    if sym not in lst:
        await interaction.response.send_message(f"`{sym}` 不在您的自選股清單中！")
        return
    lst.remove(sym)
    remove_watchlist(uid, sym)
    await interaction.response.send_message(f"🗑️ `{sym}` 已從您的自選股移除。")


@watch_group.command(name="list", description="查看自選股即時報價")
async def watch_list(interaction: discord.Interaction):
    uid = interaction.user.id
    lst = state.watchlist.get(uid, [])
    if not lst:
        await interaction.response.send_message("您的自選股清單是空的，請使用 `/watch add 代號` 新增。")
        return

    await interaction.response.defer()
    embed = discord.Embed(title="📋 我的自選股", color=discord.Color.blue())
    errors = []
    for sym in lst:
        try:
            info = get_stock_info(sym)
            add_quote_field(embed, info)
        except Exception as e:
            logger.warning("/watch list %s 查詢失敗：%s", sym, e)
            errors.append(sym)

    if embed.fields:
        await interaction.followup.send(embed=embed)
    if errors:
        await interaction.followup.send(f'⚠️ 以下代號查無資料：{", ".join(errors)}')


@watch_group.command(name="clear", description="清空自選股清單")
async def watch_clear(interaction: discord.Interaction):
    state.watchlist[interaction.user.id] = []
    clear_watchlist(interaction.user.id)
    await interaction.response.send_message("✅ 已清空您的自選股清單。")
