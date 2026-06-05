import discord
from discord import app_commands

from config import MAX_ALERTS_PER_SYMBOL
from data import get_stock_info
from db import add_alert, list_user_alerts, remove_alert
from domain.alerts import get_alert_direction


alert_group = app_commands.Group(name="alert", description="價格到價警示管理")


@alert_group.command(name="set", description="設定到價提醒（自動判斷突破或跌破）")
@app_commands.describe(sym="股票代號，例如：2330", target="目標價格")
async def alert_set(interaction: discord.Interaction, sym: str, target: float):
    sym = sym.upper()
    await interaction.response.defer()
    try:
        info = get_stock_info(sym)
        cur = info["price"]
    except Exception:
        await interaction.followup.send("查無此股票／指數，請確認代號！")
        return

    direction = get_alert_direction(target, cur)
    dir_str = f"突破 `{target}`" if direction == "above" else f"跌破 `{target}`"

    existing = [a for a in list_user_alerts(interaction.user.id) if a["symbol"] == sym]
    if len(existing) >= MAX_ALERTS_PER_SYMBOL:
        await interaction.followup.send(f"`{sym}` 警示已達上限（{MAX_ALERTS_PER_SYMBOL} 個），請先刪除後再設定。")
        return

    add_alert(interaction.user.id, sym, target, direction)
    await interaction.followup.send(
        f"✅ 已設定警示！`{sym}` {dir_str} 時將 DM 通知您。\n"
        f"目前值：`{cur}`"
    )


@alert_group.command(name="list", description="查看我的價格警示清單")
async def alert_list(interaction: discord.Interaction):
    alerts = list_user_alerts(interaction.user.id)
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
    if remove_alert(alert_id, interaction.user.id):
        await interaction.response.send_message(f"🗑️ 已刪除警示 **#{alert_id}**。")
    else:
        await interaction.response.send_message(f"找不到警示 **#{alert_id}**，請用 `/alert list` 確認編號。")
