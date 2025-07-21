from pyrogram import Client, filters
from helper.database import codeflixbots
from config import Config

@Client.on_message(filters.command("leaderboard") & (filters.private | filters.group))
async def leaderboard_handler(client, message):
    # 📊 Get top users from database
    users = await codeflixbots.get_top_renamers(limit=10)

    if not users:
        return await message.reply_text("📉 No users have renamed files yet.")

    # 🏆 Format leaderboard text
    leaderboard_text = "🏆 **Top Renamers Leaderboard**\n\n"
    total = 0

    for i, user in enumerate(users, 1):
        user_id = user["_id"]
        name = f"[User](tg://user?id={user_id})"
        count = user.get("rename_count", 0)
        total += count
        leaderboard_text += f"{i}. 👤 {name} [`{user_id}`] — `{count}` files renamed\n"

    leaderboard_text += f"\n📦 **Total Files Renamed:** `{total}` ✅"

    await message.reply_text(
        leaderboard_text,
        disable_web_page_preview=True,
        quote=True
    )