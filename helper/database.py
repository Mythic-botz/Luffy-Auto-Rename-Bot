import motor.motor_asyncio
import datetime
import pytz
import logging
from config import Config
from .utils import send_log
import asyncio

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, uri, database_name):
        try:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            self._client.server_info()  # Test connection
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e
        self.codeflixbots = self._client[database_name]
        self.users = self.codeflixbots.users  # Collection for user data
        self.chats = self.codeflixbots.chats  # Collection for chat data

    def new_user(self, id, name=None, mention=None):
        return dict(
            _id=int(id),
            name=name or "User",
            mention=mention or f"[User](tg://user?id={id})",
            join_date=datetime.datetime.now(pytz.UTC).isoformat(),
            file_id=None,  # Thumbnail file ID
            caption=None,
            metadata=True,
            metadata_code="Telegram: @Otaku_Hindi_Hub",
            format_template=None,
            rename_count=0,
            enhance_quality=False,  # New field for video quality enhancement
            title="Encoded by @codeflixbots",
            artist="@codeflixbots",
            author="@codeflixbots",
            video="Encoded by @codeflixbots",
            audio="By @codeflixbots",
            subtitle="By @codeflixbots",
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.datetime.max.isoformat(),
                ban_reason=''
            )
        )

    def new_chat(self, chat_id):
        return dict(
            _id=int(chat_id),
            caption=None,
            thumbnail=None
        )

    async def add_user(self, b, m):
        u = m.from_user
        if not await self.is_user_exist(u.id):
            name = u.first_name
            if u.last_name:
                name += f" {u.last_name}"
            mention = u.mention or f"[User](tg://user?id={u.id})"
            user = self.new_user(u.id, name, mention)
            try:
                await self.users.insert_one(user)
                await send_log(b, u)
                logger.info(f"Added new user {u.id}")
            except Exception as e:
                logger.error(f"Error adding user {u.id}: {e}")

    async def add_chat(self, chat_id):
        if not await self.is_chat_exist(chat_id):
            chat = self.new_chat(chat_id)
            try:
                await self.chats.insert_one(chat)
                logger.info(f"Added new chat {chat_id}")
            except Exception as e:
                logger.error(f"Error adding chat {chat_id}: {e}")

    async def is_user_exist(self, id):
        try:
            user = await self.users.find_one({"_id": int(id)})
            return bool(user)
        except Exception as e:
            logger.error(f"Error checking if user {id} exists: {e}")
            return False

    async def is_chat_exist(self, chat_id):
        try:
            chat = await self.chats.find_one({"_id": int(chat_id)})
            return bool(chat)
        except Exception as e:
            logger.error(f"Error checking if chat {chat_id} exists: {e}")
            return False

    async def total_users_count(self):
        try:
            return await self.users.count_documents({})
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            return 0

    async def get_all_users(self):
        try:
            return self.users.find({})
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return None

    async def delete_user(self, user_id):
        try:
            await self.users.delete_many({"_id": int(user_id)})
            logger.info(f"Deleted user {user_id}")
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")

    async def set_thumbnail(self, id, file_id):
        try:
            await self.chats.update_one({"_id": int(id)}, {"$set": {"thumbnail": file_id}}, upsert=True)
            logger.info(f"Set thumbnail for chat {id}")
        except Exception as e:
            logger.error(f"Error setting thumbnail for chat {id}: {e}")

    async def get_thumbnail(self, id):
        try:
            chat = await self.chats.find_one({"_id": int(id)})
            return chat.get("thumbnail", None) if chat else None
        except Exception as e:
            logger.error(f"Error getting thumbnail for chat {id}: {e}")
            return None

    async def set_caption(self, id, caption):
        try:
            await self.chats.update_one({"_id": int(id)}, {"$set": {"caption": caption}}, upsert=True)
            logger.info(f"Set caption for chat {id}")
        except Exception as e:
            logger.error(f"Error setting caption for chat {id}: {e}")

    async def get_caption(self, id):
        try:
            chat = await self.chats.find_one({"_id": int(id)})
            return chat.get("caption", None) if chat else None
        except Exception as e:
            logger.error(f"Error getting caption for chat {id}: {e}")
            return None

    async def set_format_template(self, id, format_template):
        try:
            await self.users.update_one({"_id": int(id)}, {"$set": {"format_template": format_template}}, upsert=True)
            logger.info(f"Set format template for user {id}")
        except Exception as e:
            logger.error(f"Error setting format template for user {id}: {e}")

    async def get_format_template(self, id):
        try:
            user = await self.users.find_one({"_id": int(id)})
            return user.get("format_template", None) if user else None
        except Exception as e:
            logger.error(f"Error getting format template for user {id}: {e}")
            return None

    async def set_enhance_quality(self, id, state):
        try:
            await self.users.update_one({"_id": int(id)}, {"$set": {"enhance_quality": bool(state)}}, upsert=True)
            logger.info(f"Set enhance_quality to {state} for user {id}")
        except Exception as e:
            logger.error(f"Error setting enhance_quality for user {id}: {e}")

    async def get_enhance_quality(self, id):
        try:
            user = await self.users.find_one({"_id": int(id)})
            return user.get("enhance_quality", False) if user else False
        except Exception as e:
            logger.error(f"Error getting enhance_quality for user {id}: {e}")
            return False

    async def set_media_preference(self, id, media_type):
        try:
            await self.users.update_one({"_id": int(id)}, {"$set": {"media_type": media_type}}, upsert=True)
            logger.info(f"Set media preference for user {id}")
        except Exception as e:
            logger.error(f"Error setting media preference for user {id}: {e}")

    async def get_media_preference(self, id):
        try:
            user = await self.users.find_one({"_id": int(id)})
            return user.get("media_type", None) if user else None
        except Exception as e:
            logger.error(f"Error getting media preference for user {id}: {e}")
            return None

    async def get_metadata(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("metadata", True) if user else True
        except Exception as e:
            logger.error(f"Error getting metadata for user {user_id}: {e}")
            return True

    async def set_metadata(self, user_id, metadata):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"metadata": metadata}}, upsert=True)
            logger.info(f"Set metadata to {metadata} for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting metadata for user {user_id}: {e}")

    async def get_title(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("title", "Encoded by @codeflixbots") if user else "Encoded by @codeflixbots"
        except Exception as e:
            logger.error(f"Error getting title for user {user_id}: {e}")
            return "Encoded by @codeflixbots"

    async def set_title(self, user_id, title):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"title": title}}, upsert=True)
            logger.info(f"Set title for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting title for user {user_id}: {e}")

    async def get_author(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("author", "@codeflixbots") if user else "@codeflixbots"
        except Exception as e:
            logger.error(f"Error getting author for user {user_id}: {e}")
            return "@codeflixbots"

    async def set_author(self, user_id, author):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"author": author}}, upsert=True)
            logger.info(f"Set author for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting author for user {user_id}: {e}")

    async def get_artist(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("artist", "@codeflixbots") if user else "@codeflixbots"
        except Exception as e:
            logger.error(f"Error getting artist for user {user_id}: {e}")
            return "@codeflixbots"

    async def set_artist(self, user_id, artist):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"artist": artist}}, upsert=True)
            logger.info(f"Set artist for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting artist for user {user_id}: {e}")

    async def get_audio(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("audio", "By @codeflixbots") if user else "By @codeflixbots"
        except Exception as e:
            logger.error(f"Error getting audio for user {user_id}: {e}")
            return "By @codeflixbots"

    async def set_audio(self, user_id, audio):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"audio": audio}}, upsert=True)
            logger.info(f"Set audio for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting audio for user {user_id}: {e}")

    async def get_subtitle(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("subtitle", "By @codeflixbots") if user else "By @codeflixbots"
        except Exception as e:
            logger.error(f"Error getting subtitle for user {user_id}: {e}")
            return "By @codeflixbots"

    async def set_subtitle(self, user_id, subtitle):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"subtitle": subtitle}}, upsert=True)
            logger.info(f"Set subtitle for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting subtitle for user {user_id}: {e}")

    async def get_video(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("video", "Encoded by @codeflixbots") if user else "Encoded by @codeflixbots"
        except Exception as e:
            logger.error(f"Error getting video for user {user_id}: {e}")
            return "Encoded by @codeflixbots"

    async def set_video(self, user_id, video):
        try:
            await self.users.update_one({"_id": int(user_id)}, {"$set": {"video": video}}, upsert=True)
            logger.info(f"Set video for user {user_id}")
        except Exception as e:
            logger.error(f"Error setting video for user {user_id}: {e}")

    async def increment_rename_count(self, user_id):
        try:
            await self.users.update_one(
                {"_id": int(user_id)},
                {"$inc": {"rename_count": 1}},
                upsert=True
            )
            logger.info(f"Incremented rename count for user {user_id}")
        except Exception as e:
            logger.error(f"Error incrementing rename count for user {user_id}: {e}")

    async def get_rename_count(self, user_id):
        try:
            user = await self.users.find_one({"_id": int(user_id)})
            return user.get("rename_count", 0) if user else 0
        except Exception as e:
            logger.error(f"Error getting rename count for user {user_id}: {e}")
            return 0

    async def get_top_renamers(self, limit=10):
        try:
            cursor = self.users.find({"rename_count": {"$gt": 0}}).sort("rename_count", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error getting top renamers: {e}")
            return []

    async def reset_leaderboard(self):
        try:
            await self.users.update_many({}, {"$set": {"rename_count": 0}})
            logger.info("Leaderboard cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing leaderboard: {e}")

    async def retry_operation(self, operation, *args, max_retries=3, delay=1):
        """Retry a MongoDB operation with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return await operation(*args)
            except Exception as e:
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {operation.__name__}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Operation {operation.__name__} failed after {max_retries} retries: {e}")
                    raise e
                await asyncio.sleep(delay * (2 ** attempt))

# Instantiate
codeflixbots = Database(Config.DB_URL, Config.DB_NAME)