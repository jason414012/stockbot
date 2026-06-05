import discord

from ..state import bot


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
