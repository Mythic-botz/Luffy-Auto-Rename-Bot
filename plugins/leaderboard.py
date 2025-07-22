import os
from pyrogram import Client, filters
from helper.database import codeflixbots

@Client.on_message(filters.command("leaderboard") & (filters.private | filters.group))
async def leaderboard_handler(client, message):
    users = await codeflixbots.get_top_renamers(limit=10)

    if not users:
        return await message.reply_text("📉 No users have renamed files yet.")

    leaderboard_text = "🏆 **Top Renamers Leaderboard**\n\n"
    total = 0
    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(users, 1):
        user_id = user["_id"]
        name = user.get("name", "User")
        mention = f"[{name}](tg://user?id={user_id})"  # ✅ clickable mention
        count = user.get("rename_count", 0)
        total += count
        medal = medals[i - 1] if i <= 3 else f"{i}."
        leaderboard_text += f"{medal} 👤 {mention} — `{count}` files\n"

    leaderboard_text += f"\n📦 **Total Files Renamed:** `{total}` ✅"

    await message.reply_text(
        leaderboard_text,
        disable_web_page_preview=True,
        quote=True
    )