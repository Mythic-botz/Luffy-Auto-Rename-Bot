import aiohttp
import asyncio
import warnings
import pytz
from datetime import datetime, timedelta
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import Config
from aiohttp import web
from route import web_server
import pyrogram.utils
import pyromod
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import time
from plugins import leaderboard
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Adjust MIN_CHANNEL_ID for Telegram
pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

# Support chat from ENV or default
SUPPORT_CHAT = int(os.environ.get("SUPPORT_CHAT", "-1002625476694"))

PORT = Config.PORT


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="codeflixbots",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
        )
        self.start_time = time.time()
        logger.info("Bot instance created")

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username

        logger.info(f"{me.first_name} started successfully (Username: @{me.username})")

        # Send startup message
        uptime_string = str(timedelta(seconds=int(time.time() - self.start_time)))
        curr = datetime.now(pytz.timezone("Asia/Kolkata"))
        date = curr.strftime("%d %B, %Y")
        time_str = curr.strftime("%I:%M:%S %p")

        for chat_id in [Config.LOG_CHANNEL, SUPPORT_CHAT]:
            try:
                await self.send_video(
                    chat_id=chat_id,
                    video=Config.START_VID,
                    caption=(
                        "**ʟᴜғғʏ ɪs ʀᴇsᴛᴀʀᴛᴇᴅ ᴀɢᴀɪɴ!**\n\n"
                        f"⏳ Uptime: `{uptime_string}`\n"
                        f"📅 Date: {date}\n"
                        f"⏰ Time: {time_str}"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/+rB9N1pKnJ783NWJl"),
                            InlineKeyboardButton("ᴄʜᴇᴄᴋ ʙᴏᴛ •", url="https://t.me/NexusRenameBot")
                        ]
                    ])
                )
                logger.info(f"Startup message sent to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send startup message to {chat_id}: {e}")

        # Start webhook server if enabled
        if Config.WEBHOOK:
            try:
                app = web_server()  # should return web.Application
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, "0.0.0.0", PORT)
                await site.start()
                logger.info(f"Webhook server started on port {PORT}")
            except Exception as e:
                logger.error(f"Failed to start webhook server: {e}")

    async def stop(self):
        await super().stop()
        logger.info("Bot stopped cleanly")


async def main():
    bot = Bot()
    try:
        await bot.start()
        await asyncio.Event().wait()  # keep running
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
        await bot.stop()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error, bot could not start: {e}")
        exit(1)