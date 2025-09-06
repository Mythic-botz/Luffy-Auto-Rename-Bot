import aiohttp, asyncio, warnings, pytz
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
                            print("Ping successful")
                        else:
                            print("Ping failed with status:", response.status)
            except Exception as e:
                print("Error while pinging:", e)

            await asyncio.sleep(300)

    async def start(self):
        await super().start()
        me = await self.get_me()
        self.mention = me.mention
        self.username = me.username  
        self.uptime = Config.BOT_UPTIME  

        if Config.WEBHOOK:
            app = web.AppRunner(await web_server())
            await app.setup()       
            await web.TCPSite(app, "0.0.0.0", 8080).start()     

        print(f"{me.first_name} Is Started.....✨️")
        print("✅ Bot started.")

        # Send log message
        try:
            await self.send_message(Config.LOG_CHANNEL, "✅ Bot is online!")
        except Exception as e:
            print(f"Failed to send bot online message: {e}")

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
                        [[
                            InlineKeyboardButton("ᴜᴘᴅᴀᴛᴇs", url="https://t.me/MythicBots")
                        ]]
                    )
                )
            except Exception as e:
                print(f"Failed to send message in chat {chat_id}: {e}")

        asyncio.create_task(self.ping_service())

    async def stop(self, *args):
        print("🛑 Bot stopped.")
        return await super().stop()


if __name__ == "__main__":
    Bot().run()