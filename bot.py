import aiohttp
import asyncio
import warnings
import pytz
from datetime import datetime, timedelta
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from config import Config
from aiohttp import web
from route import web_server
import pyrogram.utils
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import os
import time
import logging

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

pyrogram.utils.MIN_CHANNEL_ID = -1002258136705

SUPPORT_CHAT = os.environ.get("SUPPORT_CHAT", "MythicBot_Support")

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

    async def ping_service(self):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://afrb-b6a8.onrender.com") as response:
                        if response.status == 200:
                            logger.info("Ping successful")
                        else:
                            logger.warning(f"Ping failed with status: {response.status}")
            except Exception as e:
                logger.error(f"Error while pinging: {e}")
            await asyncio.sleep(300)

    async def start(self):
        try:
            await super().start()
            me = await self.get_me()
            self.mention = me.mention
            self.username = me.username
            self.uptime = Config.BOT_UPTIME

            if Config.WEBHOOK:
                try:
                    app = web.AppRunner(await web_server())
                    await app.setup()
                    await web.TCPSite(app, "0.0.0.0", 8080).start()
                    logger.info("Webhook server started on port 8080")
                except Exception as e:
                    logger.error(f"Failed to start webhook server: {e}")

            logger.info(f"{me.first_name} Is Started.....✨️")
            logger.info("✅ Bot started.")

            # Send log message
            try:
                await self.send_message(Config.LOG_CHANNEL, "✅ Bot is online!")
            except Exception as e:
                logger.error(f"Failed to send bot online message to LOG_CHANNEL: {e}")

            uptime_seconds = int(time.time() - self.start_time)
            uptime_string = str(timedelta(seconds=uptime_seconds))

            for chat_id in [Config.LOG_CHANNEL, SUPPORT_CHAT]:
                try:
                    curr = datetime.now(timezone("Asia/Kolkata"))
                    await self.send_photo(
                        chat_id=chat_id,
                        photo=Config.START_PIC,
                        caption=(
                            "**ᴀɴʏᴀ ɪs ʀᴇsᴛᴀʀᴛᴇᴅ ᴀɢᴀɪɴ  !**\n\n"
                            f"ɪ ᴅɪᴅɴ'ᴛ sʟᴇᴘᴛ sɪɴᴄᴇ: `{uptime_string}`"
                        ),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/MythicBots")]]
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to send message in chat {chat_id}: {e}")

            asyncio.create_task(self.ping_service())
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

    async def stop(self, *args):
        logger.info("🛑 Bot stopped.")
        return await super().stop()



if __name__ == "__main__":
    try:
        Bot().run()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise