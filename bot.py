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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Adjust MIN_CHANNEL_ID for Telegram
pyrogram.utils.MIN_CHANNEL_ID = -1009147483647

# Set SUPPORT_CHAT from environment or default
SUPPORT_CHAT = int(os.environ.get("SUPPORT_CHAT", "-1002625476694"))

PORT = Config.PORT

class Bot(Client):
    def __init__(self, loop=None):
        super().__init__(
            name="codeflixbots",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=200,
            plugins={"root": "plugins"},
            sleep_threshold=15,
            loop=loop  # Pass the event loop to Pyrogram
        )
        self.start_time = time.time()
        logger.info("Bot initialized")

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username
        self.uptime = time.time() - self.start_time
        logger.info(f"{me.first_name} is started (Username: @{me.username})")

        # Send startup message to log and support chats
        uptime_string = str(timedelta(seconds=int(self.uptime)))
        curr = datetime.now(pytz.timezone("Asia/Kolkata"))
        date = curr.strftime('%d %B, %Y')
        time_str = curr.strftime('%I:%M:%S %p')

        for chat_id in [Config.LOG_CHANNEL, SUPPORT_CHAT]:
            try:
                await self.send_video(
                    chat_id=chat_id,
                    video=Config.START_VID,
                    caption=(
                        "**ʟᴜғғʏ ɪs ʀᴇsᴛᴀʀᴛᴇᴅ ᴀɢᴀɪɴ  !**\n\n"
                        f"ɪ ᴅɪᴅɴ'ᴛ sʟᴇᴘᴛ sɪɴᴄᴇ: `{uptime_string}`\n"
                        f"Date: {date}\nTime: {time_str}"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("• ᴜᴘᴅᴀᴛᴇꜱ", url="https://t.me/+rB9N1pKnJ783NWJl"),
                            InlineKeyboardButton("ᴄʜᴇᴄᴋ ʙᴏᴛ •", url="https://t.me/NexusRenameBot")
                        ]
                    ])
                )
                logger.info(f"Sent startup message to chat {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send startup message to chat {chat_id}: {e}")

        # Start web server if webhook is enabled
        if Config.WEBHOOK:
            try:
                app = web.AppRunner(await web_server())
                await app.setup()
                await web.TCPSite(app, "0.0.0.0", PORT, loop=self.loop).start()
                logger.info(f"Webhook server started on port {PORT}")
            except Exception as e:
                logger.error(f"Failed to start webhook server: {e}")

    async def stop(self):
        await super().stop()
        logger.info("Bot stopped")

async def main():
    loop = asyncio.get_event_loop()  # Get the current event loop
    bot = Bot(loop=loop)  # Pass the loop to the Bot
    try:
        await bot.start()
        await asyncio.Event().wait()  # Keep the bot running
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, stopping bot")
        await bot.stop()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        await bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        exit(1)