import aiohttp
import asyncio
import warnings
import pytz
from datetime import datetime, timedelta
from pytz import timezone
from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from pyrogram.errors.exceptions.bad_request_400 import ChatAdminRequired
from config import Config
from aiohttp import web
from route import web_server
import pyrogram.utils
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import filters
import os
import time
import logging
from logging.handlers import RotatingFileHandler

# Configure logging with rotation
log_file = "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5),  # 10MB per file, 5 backups
        logging.StreamHandler()  # Also log to console
    ]
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
        self.restart_count = 0
        self.ping_url = "https://luffy-auto-rename-bot-c487.onrender.com"
        self.fallback_ping_url = os.environ.get("FALLBACK_PING_URL", "https://api.telegram.org")  # Fallback URL

    async def check_admin_privileges(self, chat_id):
        """Check if the bot has admin privileges in the given chat."""
        try:
            chat_member = await self.get_chat_member(chat_id, self.me.id)
            if chat_member.status in ["administrator", "creator"]:
                return True
            else:
                logger.warning(f"Bot is not an admin in chat {chat_id}")
                return False
        except ChatAdminRequired as e:
            logger.error(f"Bot lacks admin privileges in chat {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking admin privileges in chat {chat_id}: {e}")
            return False

    async def ping_service(self):
        max_ping_retries = 3
        ping_delay = 10
        while True:
            urls = [self.ping_url, self.fallback_ping_url]
            ping_success = False
            for url in urls:
                for attempt in range(1, max_ping_retries + 1):
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(url) as response:
                                if response.status == 200:
                                    logger.info(f"Ping successful to {url}")
                                    ping_success = True
                                    break
                                else:
                                    logger.warning(f"Ping to {url} failed with status: {response.status}")
                    except Exception as e:
                        logger.error(f"Ping error to {url}: {e}")
                    if attempt < max_ping_retries:
                        logger.info(f"Retrying ping to {url} in {ping_delay} seconds... (Attempt {attempt}/{max_ping_retries})")
                        await asyncio.sleep(ping_delay)
                    else:
                        logger.error(f"All ping attempts failed for {url}.")
                        try:
                            await self.send_message(
                                Config.LOG_CHANNEL,
                                f"⚠️ All ping attempts failed for {url} after {max_ping_retries} attempts."
                            )
                        except Exception as e:
                            logger.error(f"Failed to send ping failure notification: {e}")
                if ping_success:
                    break  # Exit URL loop if ping is successful
            if not ping_success:
                logger.error("All URLs failed to ping. Bot continues running.")
            await asyncio.sleep(300)  # Wait 5 minutes before next ping cycle

    async def start(self):
        try:
            await super().start()
            self.me = await self.get_me()
            self.mention = self.me.mention
            self.username = self.me.username
            self.uptime = Config.BOT_UPTIME

            # Check admin privileges for required chats
            for chat_id in [Config.LOG_CHANNEL, SUPPORT_CHAT]:
                if chat_id and not await self.check_admin_privileges(chat_id):
                    try:
                        await self.send_message(
                            Config.LOG_CHANNEL,
                            f"⚠️ Bot lacks admin privileges in chat {chat_id}. Some features may not work."
                        )
                    except Exception as e:
                        logger.error(f"Failed to send admin privilege warning for {chat_id}: {e}")

            if Config.WEBHOOK:
                try:
                    app = web.AppRunner(await web_server())
                    await app.setup()
                    await web.TCPSite(app, "0.0.0.0", 8080).start()
                    logger.info("Webhook server started on port 8080")
                except Exception as e:
                    logger.error(f"Failed to start webhook server: {e}")

            logger.info(f"{self.me.first_name} Is Started.....✨️")
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
                if not chat_id:
                    continue
                try:
                    curr = datetime.now(timezone("Asia/Kolkata"))
                    await self.send_photo(
                        chat_id=chat_id,
                        photo=Config.START_PIC,
                        caption=(
                            "**Test bot ɪs ʀᴇsᴛᴀʀᴛᴇᴅ ᴀɢᴀɪɴ  !**\n\n"
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
            self.restart_count += 1
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

    # Command to send log file
    @Client.on_message(filters.command("log") & filters.private)
    async def send_log(self, client, message):
        try:
            if not os.path.exists(log_file):
                await message.reply_text("Log file not found.")
                return
            with open(log_file, "rb") as f:
                await message.reply_document(
                    document=f,
                    caption="Bot log file",
                    file_name="bot.log"
                )
            logger.info(f"Log file sent to user {message.from_user.id}")
        except Exception as e:
            logger.error(f"Failed to send log file to user {message.from_user.id}: {e}")
            await message.reply_text(f"Failed to send log file: {str(e)}")

async def run_bot_with_restart():
    max_retries = 5
    retry_delay = 60
    while True:
        bot = Bot()
        try:
            logger.info("Starting bot...")
            await bot.start()
            await asyncio.Event().wait()
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
        await asyncio.sleep(5)

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
