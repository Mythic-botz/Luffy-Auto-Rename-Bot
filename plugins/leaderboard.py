import os
from pyrogram import Client, filters
from helper.database import codeflixbots
from config import Config

@Client.on_message(filters.command("leaderboard") & (filters.private | filters.group))
async def leaderboard_handler(client, message):
    users = await codeflixbots.get_top_renamers(limit=10)

    if not users:
        return await message.reply_text("📉 No users have renamed files yet.")

    medals = ["🥇", "🥈", "🥉"]
    leaderboard_lines = ["🏆 Top Renamers Leaderboard 🏆\n"]
    total = 0

    for i, user in enumerate(users, 1):
        user_id = user["_id"]
        count = user.get("rename_count", 0)
        total += count
        emoji = medals[i-1] if i <= 3 else "👤"

        mention = f"@{user.get('username', f'user{user_id}')}"  # fallback if no username
        line = f"{i}. {emoji} User: {mention} | ID: {user_id} | Files Renamed: {count}"
        leaderboard_lines.append(line)

    leaderboard_lines.append(f"\n📦 Total Files Renamed: {total} ✅")

    text_content = "\n".join(leaderboard_lines)
    file_path = "leaderboard.txt"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text_content)

    await message.reply_document(
        document=file_path,
        caption="📊 **Here's the top renamers leaderboard!**",
    )

    os.remove(file_path)