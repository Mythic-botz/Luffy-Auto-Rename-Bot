import motor.motor_asyncio, datetime, pytz
from config import Config
import logging
from .utils import send_log


class Database:
    def __init__(self, uri, database_name):
        try:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            self._client.server_info()
            logging.info("Successfully connected to MongoDB")
        except Exception as e:
            logging.error(f"Failed to connect to MongoDB: {e}")
            raise e
        self.codeflixbots = self._client[database_name]
        self.col = self.codeflixbots.user

    def new_user(self, id, name=None, mention=None):
        return dict(
            _id=int(id),
            name=name or "User",
            mention=mention or f"[User](tg://user?id={id})",
            join_date=datetime.date.today().isoformat(),
            file_id=None,
            caption=None,
            metadata=True,
            metadata_code="Telegram : @codeflixbots",
            format_template=None,
            rename_count=0,
            ban_status=dict(
                is_banned=False,
                ban_duration=0,
                banned_on=datetime.date.max.isoformat(),
                ban_reason=''
            )
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
                await self.col.insert_one(user)
                await send_log(b, u)
            except Exception as e:
                logging.error(f"Error adding user {u.id}: {e}")

    async def is_user_exist(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return bool(user)
        except Exception as e:
            logging.error(f"Error checking if user {id} exists: {e}")
            return False

    async def total_users_count(self):
        try:
            return await self.col.count_documents({})
        except Exception as e:
            logging.error(f"Error counting users: {e}")
            return 0

    async def get_all_users(self):
        try:
            return self.col.find({})
        except Exception as e:
            logging.error(f"Error getting all users: {e}")
            return None

    async def delete_user(self, user_id):
        try:
            await self.col.delete_many({"_id": int(user_id)})
        except Exception as e:
            logging.error(f"Error deleting user {user_id}: {e}")

    async def set_thumbnail(self, id, file_id):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"file_id": file_id}})
        except Exception as e:
            logging.error(f"Error setting thumbnail for user {id}: {e}")

    async def get_thumbnail(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("file_id", None) if user else None
        except Exception as e:
            logging.error(f"Error getting thumbnail for user {id}: {e}")
            return None

    async def set_caption(self, id, caption):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"caption": caption}})
        except Exception as e:
            logging.error(f"Error setting caption for user {id}: {e}")

    async def get_caption(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("caption", None) if user else None
        except Exception as e:
            logging.error(f"Error getting caption for user {id}: {e}")
            return None

    async def set_format_template(self, id, format_template):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"format_template": format_template}})
        except Exception as e:
            logging.error(f"Error setting format template for user {id}: {e}")

    async def get_format_template(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("format_template", None) if user else None
        except Exception as e:
            logging.error(f"Error getting format template for user {id}: {e}")
            return None

    async def set_media_preference(self, id, media_type):
        try:
            await self.col.update_one({"_id": int(id)}, {"$set": {"media_type": media_type}})
        except Exception as e:
            logging.error(f"Error setting media preference for user {id}: {e}")

    async def get_media_preference(self, id):
        try:
            user = await self.col.find_one({"_id": int(id)})
            return user.get("media_type", None) if user else None
        except Exception as e:
            logging.error(f"Error getting media preference for user {id}: {e}")
            return None

    async def get_metadata(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('metadata', "Off")

    async def set_metadata(self, user_id, metadata):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'metadata': metadata}})

    async def get_title(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('title', 'Encoded by @Animes_Cruise')

    async def set_title(self, user_id, title):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'title': title}})

    async def get_author(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('author', '@Animes_Cruise')

    async def set_author(self, user_id, author):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'author': author}})

    async def get_artist(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('artist', '@Animes_Cruise')

    async def set_artist(self, user_id, artist):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'artist': artist}})

    async def get_audio(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('audio', 'By @Animes_Cruise')

    async def set_audio(self, user_id, audio):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'audio': audio}})

    async def get_subtitle(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('subtitle', "By @Animes_Cruise")

    async def set_subtitle(self, user_id, subtitle):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'subtitle': subtitle}})

    async def get_video(self, user_id):
        user = await self.col.find_one({'_id': int(user_id)})
        return user.get('video', 'Encoded By @Otaku_Hindi_Hub')

    async def set_video(self, user_id, video):
        await self.col.update_one({'_id': int(user_id)}, {'$set': {'video': video}})

    # ✅ Leaderboard Functions
    async def increment_rename_count(self, user_id):
        try:
            await self.col.update_one(
                {"_id": int(user_id)},
                {"$inc": {"rename_count": 1}}
            )
        except Exception as e:
            logging.error(f"Error incrementing rename count for user {user_id}: {e}")

    async def get_rename_count(self, user_id):
        try:
            user = await self.col.find_one({"_id": int(user_id)})
            return user.get("rename_count", 0) if user else 0
        except Exception as e:
            logging.error(f"Error getting rename count for user {user_id}: {e}")
            return 0

    async def get_top_renamers(self, limit=10):
        try:
            cursor = self.col.find({"rename_count": {"$gt": 0}}).sort("rename_count", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logging.error(f"Error getting top users: {e}")
            return []

    async def reset_leaderboard(self):
        try:
            await self.col.update_many({}, {"$set": {"rename_count": 0}})
            logging.info("Leaderboard cleared successfully.")
        except Exception as e:
            logging.error(f"Error clearing leaderboard: {e}")


# Instantiate
codeflixbots = Database(Config.DB_URL, Config.DB_NAME)