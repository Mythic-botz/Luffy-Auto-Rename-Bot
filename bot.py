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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        self.restart_count = 0  # Track number of restarts

    async def ping_service(self):
        max_ping_retries = 3
        ping_delay = 10  # Delay between retry attempts
        while True:
            for attempt in range(1, max_ping_retries + 1):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get("https://afrb-b6a8.onrender.com") as response:
                            if response.status == 200:
                                logger.info("Ping successful")
                                break
                            else:
                                logger.warning(f"Ping failed with status: {response.status}")
                except Exception as e:
                    logger.error(f"Ping error: {e}")
                if attempt < max_ping_retries:
                    logger.info(f"Retrying ping in {ping_delay} seconds... (Attempt {attempt}/{max_ping_retries})")
                    await asyncio.sleep(ping_delay)
                else:
                    logger.error("All ping attempts failed.")
                    # Notify LOG_CHANNEL about ping failure
                    try:
                        await self.send_message(
                            Config.LOG_CHANNEL,
                            f"⚠️ Ping to https://afrb-b6a8.onrender.com failed after {max_ping_retries} attempts."
                        )
                    except Exception as e:
                        logger.error(f"Failed to send ping failure notification: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before next ping cycle

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

            # Send startup notification
            try:
                startup_message = (
                    f"✅ Bot is online!\n"
                    f"Restart Count: {self.restart_count}\n"
                    f"Bot Username: @{self.username}"
                )
                await self.send_message(Config.LOG_CHANNEL, startup_message)
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
                            f"ɪ ᴅɪᴅɴ'ᴛ sʟᴇᴘᴛ sɪɴᴄᴇ: `{uptime_string}`\n"
                            f"Restart Count: `{self.restart_count}`"
                        ),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/MythicBots")]]
                        )
                    )
                except Exception as e:
                    logger.error(f"Failed to send message in chat {chat_id}: {e}")

            asyncio.create_task(self.ping_service())
            self.restart_count += 1  # Increment restart count
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise

    async def stop(self, *args):
        logger.info("🛑 Bot stopped.")
        try:
            await self.send_message(Config.LOG_CHANNEL, "🛑 Bot stopped.")
        except Exception as e:
            logger.error(f"Failed to send bot stop message: {e}")
        await super().stop()

async def run_bot_with_restart():
    max_retries = 5  # Maximum restart attempts
    retry_delay = 60  # Delay between restarts in seconds

    while True:
        bot = Bot()
        try:
            logger.info("Starting bot...")
            await bot.start()
            await asyncio.Event().wait()  # Keep bot running until stopped
        except Exception as e:
            logger.error(f"Bot crashed with error: {e}")
            try:
                await bot.send_message(
                    Config.LOG_CHANNEL,
                    f"⚠️ Bot crashed with error: {e}\nAttempting restart..."
                )
            except Exception as notify_error:
                logger.error(f"Failed to send crash notification: {notify_error}")

            if bot.restart_count >= max_retries:
                logger.error(f"Max retries ({max_retries}) reached. Exiting...")
                try:
                    await bot.send_message(
                        Config.LOG_CHANNEL,
                        f"🚫 Max retries ({max_retries}) reached. Bot will not restart."
                    )
                except Exception as notify_error:
                    logger.error(f"Failed to send max retries notification: {notify_error}")
                break

            logger.info(f"Restarting bot in {retry_delay} seconds... (Attempt {bot.restart_count}/{max_retries})")
            await asyncio.sleep(retry_delay)
        finally:
            try:
                await bot.stop()
            except Exception as e:
                logger.error(f"Error during bot shutdown: {e}")
        await asyncio.sleep(5)  # Prevent tight restart loops

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_bot_with_restart())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Shutting down...")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        logger.info("Event loop closed.")
