import os
import re
import time
import shutil
import asyncio
import logging
from datetime import datetime
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from plugins.antinsfw import check_anti_nsfw
from helper.utils import progress_for_pyrogram, humanbytes, convert
from helper.database import codeflixbots
from config import Config

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

renaming_operations = {}

# Per-user download/upload manager
class UserDownloadManager:
    def __init__(self):
        self.user_queues = {}
        self.user_semaphores = {}
        self.max_concurrent = 5
        logger.info("UserDownloadManager initialized")

    def get_queue(self, user_id):
        if user_id not in self.user_queues:
            self.user_queues[user_id] = asyncio.Queue()  # Removed loop parameter
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent)
            logger.info(f"Initialized queue and semaphore for user {user_id}")
        return self.user_queues[user_id]

    def get_semaphore(self, user_id):
        if user_id not in self.user_semaphores:
            self.user_queues[user_id] = asyncio.Queue()  # Removed loop parameter
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent)
            logger.info(f"Initialized semaphore for user {user_id}")
        return self.user_semaphores[user_id]

    async def add_task(self, user_id, task_data):
        queue = self.get_queue(user_id)
        await queue.put(task_data)
        logger.info(f"Added task for user {user_id}. Queue size: {queue.qsize()}")
        asyncio.create_task(self.process_queue(user_id))

    async def process_queue(self, user_id):
        queue = self.get_queue(user_id)
        semaphore = self.get_semaphore(user_id)

        while not queue.empty():
            async with semaphore:
                task_data = await queue.get()
                try:
                    await task_data['handler'](task_data['client'], task_data['message'])
                except Exception as e:
                    logger.error(f"Task processing error for user {user_id}: {e}")
                finally:
                    queue.task_done()
                    logger.info(f"Task completed for user {user_id}. Queue size: {queue.qsize()}")

# Initialize download manager
download_manager = UserDownloadManager()

# Patterns
SEASON_EPISODE_PATTERNS = [
    (re.compile(r'S(\d+)(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[\s-]*(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'Season\s*(\d+)\s*Episode\s*(\d+)', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'S(\d+)E(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[^\d]*(\d+)'), ('season', 'episode')),
    (re.compile(r'(?:E|EP|Episode)\s*(\d+)', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\b(\d+)\b'), (None, 'episode')),
    (re.compile(r'\[S-(\d+)\]\s*\[E-(\d+)\]'), ('season', 'episode')),
    (re.compile(r'\[S(\d+)\]\s*\[E(\d+)\]'), ('season', 'episode')),
    (re.compile(r'\[Season\s*(\d+)\]\s*\[Episode\s*(\d+)\]', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'\bS-(\d+)\b\s*\bE-(\d+)\b'), ('season', 'episode')),
    (re.compile(r'\b(?:Ep|EP|E|-E|E-)(\d+)\b', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\bEp-(\d+)\b', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\bEpisode-(\d+)\b', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\[S-(\d+)\]'), ('season', None)),
    (re.compile(r'\[Season\s*(\d+)\]', re.IGNORECASE), ('season', None)),
    (re.compile(r'\bS-(\d+)\b'), ('season', None)),
]

QUALITY_PATTERNS = [
    (re.compile(r'\b(\d{3,4}[pi])\b', re.IGNORECASE), lambda m: m.group(1).lower()),
    (re.compile(r'\[(\d{3,4}[pi])\]', re.IGNORECASE), lambda m: m.group(1).lower()),
    (re.compile(r'\b(4k|2160p)\b', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\[(4k|2160p)\]', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\b(2k|1440p)\b', re.IGNORECASE), lambda m: "2k"),
    (re.compile(r'\[(2k|1440p)\]', re.IGNORECASE), lambda m: "2k"),
    (re.compile(r'\b(360p)\b', re.IGNORECASE), lambda m: "360p"),
    (re.compile(r'\[360p\]', re.IGNORECASE), lambda m: "360p"),
    (re.compile(r'\bSD\b', re.IGNORECASE), lambda m: "480p"),
    (re.compile(r'\[SD\]', re.IGNORECASE), lambda m: "480p"),
    (re.compile(r'\bHD\b', re.IGNORECASE), lambda m: "720p"),
    (re.compile(r'\[HD\]', re.IGNORECASE), lambda m: "720p"),
    (re.compile(r'\b(UHD|4kX264|4kx265)\b', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\[(UHD|4kX264|4kx265)\]', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\b(HDRip|HDTV)\b', re.IGNORECASE), lambda m: "720p"),
    (re.compile(r'\b(X264|X265|HEVC)\b', re.IGNORECASE), lambda m: "1080p"),
    (re.compile(r'(\d{3,4}[pi])', re.IGNORECASE), lambda m: m.group(1).lower()),
]

def extract_season_episode(filename):
    for pattern, (season_group, episode_group) in SEASON_EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            season = match.group(1) if season_group else None
            episode = match.group(2) if episode_group else match.group(1) if episode_group else None
            return season, episode
    return None, None

def extract_quality(filename):
    for pattern, extractor in QUALITY_PATTERNS:
        match = pattern.search(filename)
        if match:
            return extractor(match)
    return "Unknown"

async def cleanup_files(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Error removing {path}: {e}")

async def process_thumbnail(thumb_path):
    if not thumb_path or not os.path.exists(thumb_path):
        return None
    try:
        with Image.open(thumb_path) as img:
            img = img.convert("RGB").resize((1280, 720))
            img.save(thumb_path, "JPEG")
        return thumb_path
    except Exception as e:
        logger.error(f"Thumbnail processing failed: {e}")
        await cleanup_files(thumb_path)
        return None

async def add_metadata(input_path, output_path, user_id):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        logger.error("FFmpeg not found in PATH, copying file without metadata")
        shutil.copy(input_path, output_path)
        return

    metadata = {
        'title': 'Default Title',
        'artist': 'Default Artist',
        'author': 'Default Author',
        'video_title': 'Default Video',
        'audio_title': 'Default Audio',
        'subtitle': 'Default Subtitle'
    }
    try:
        metadata['title'] = await codeflixbots.get_title(user_id) or metadata['title']
        metadata['artist'] = await codeflixbots.get_artist(user_id) or metadata['artist']
        metadata['author'] = await codeflixbots.get_author(user_id) or metadata['author']
        metadata['video_title'] = await codeflixbots.get_video(user_id) or metadata['video_title']
        metadata['audio_title'] = await codeflixbots.get_audio(user_id) or metadata['audio_title']
        metadata['subtitle'] = await codeflixbots.get_subtitle(user_id) or metadata['subtitle']
    except Exception as e:
        logger.error(f"Failed to fetch metadata for user {user_id}: {e}")

    cmd = [
        ffmpeg, '-i', input_path,
        '-metadata', f'title={metadata["title"]}',
        '-metadata', f'artist={metadata["artist"]}',
        '-metadata', f'author={metadata["author"]}',
        '-metadata:s:v', f'title={metadata["video_title"]}',
        '-metadata:s:a', f'title={metadata["audio_title"]}',
        '-metadata:s:s', f'title={metadata["subtitle"]}',
        '-map', '0', '-c', 'copy', '-loglevel', 'error', output_path
    ]

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"FFmpeg error: {stderr.decode()}, copying file without metadata")
        shutil.copy(input_path, output_path)

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    try:
        format_template = await codeflixbots.get_format_template(user_id)
        if not format_template:
            await message.reply_text("Please set a rename format using /autorename")
            return
    except Exception as e:
        logger.error(f"Error fetching format template for user {user_id}: {e}")
        await message.reply_text("Error accessing database. Please try again later.")
        return

    if message.document:
        file_id = message.document.file_id
    elif message.video:
        file_id = message.video.file_id
    elif message.audio:
        file_id = message.audio.file_id
    else:
        await message.reply_text("Unsupported file type")
        return

    # Check for NSFW content before queuing
    file_name = (message.document.file_name if message.document else
                 message.video.file_name if message.video else
                 message.audio.file_name if message.audio else "unknown")
    try:
        if await check_anti_nsfw(file_name, message):
            await message.reply_text("NSFW content detected")
            return
    except Exception as e:
        logger.error(f"NSFW check failed for user {user_id}: {e}")
        await message.reply_text("Error checking NSFW content, proceeding with processing")

    # Check for duplicate processing
    if file_id in renaming_operations:
        if (datetime.now() - renaming_operations[file_id]).seconds < 10:
            return
    renaming_operations[file_id] = datetime.now()

    # Add task to the user's queue
    try:
        await download_manager.add_task(user_id, {
            'client': client,
            'message': message,
            'handler': process_file
        })
    except Exception as e:
        logger.error(f"Error adding task for user {user_id}: {e}")
        await message.reply_text("Error queuing file for processing. Please try again.")

async def process_file(client, message):
    download_path = metadata_path = thumb_path = None
    user_id = message.from_user.id
    try:
        format_template = await codeflixbots.get_format_template(user_id)
    except Exception as e:
        logger.error(f"Error fetching format template in process_file for user {user_id}: {e}")
        await message.reply_text("Error accessing database. Please try again later.")
        return

    if message.document:
        file_id, file_name, file_size, media_type = message.document.file_id, message.document.file_name, message.document.file_size, "document"
    elif message.video:
        file_id, file_name, file_size, media_type = message.video.file_id, message.video.file_name or "video", message.video.file_size, "video"
    elif message.audio:
        file_id, file_name, file_size, media_type = message.audio.file_id, message.audio.file_name or "audio", message.audio.file_size, "audio"
    else:
        return

    try:
        season, episode = extract_season_episode(file_name)
        quality = extract_quality(file_name)

        for ph, val in {
            '{season}': season or 'XX', '{episode}': episode or 'XX',
            '{quality}': quality, 'Season': season or 'XX',
            'Episode': episode or 'XX', 'QUALITY': quality
        }.items():
            format_template = format_template.replace(ph, val)

        ext = os.path.splitext(file_name)[1] or ('.mp4' if media_type == 'video' else '.mp3')
        new_filename = f"{format_template}{ext}"
        download_path, metadata_path = f"downloads/{new_filename}", f"metadata/{new_filename}"
        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)

        msg = await message.reply_text("**Downloading...**")
        file_path = await client.download_media(
            message, file_name=download_path,
            progress=progress_for_pyrogram, progress_args=("Downloading...", msg, time.time())
        )

        await msg.edit("**Processing metadata...**")
        await add_metadata(file_path, metadata_path, user_id)
        file_path = metadata_path

        await msg.edit("**Preparing upload...**")
        try:
            caption = await codeflixbots.get_caption(message.chat.id) or f"**{new_filename}**"
        except Exception as e:
            logger.error(f"Error fetching caption for chat {message.chat.id}: {e}")
            caption = f"**{new_filename}**"

        try:
            thumb = await codeflixbots.get_thumbnail(message.chat.id)
        except Exception as e:
            logger.error(f"Error fetching thumbnail for chat {message.chat.id}: {e}")
            thumb = None

        if thumb:
            try:
                thumb_path = await client.download_media(thumb)
            except Exception as e:
                logger.error(f"Error downloading thumbnail: {e}")
                thumb_path = None
        elif media_type == "video" and message.video.thumbs:
            try:
                thumb_path = await client.download_media(message.video.thumbs[0].file_id)
            except Exception as e:
                logger.error(f"Error downloading video thumbnail: {e}")
                thumb_path = None

        thumb_path = await process_thumbnail(thumb_path)

        await msg.edit("**Uploading...**")
        upload_args = {
            'chat_id': message.chat.id,
            'caption': caption,
            'thumb': thumb_path,
            'progress': progress_for_pyrogram,
            'progress_args': ("Uploading...", msg, time.time())
        }

        try:
            if media_type == "video":
                await client.send_video(video=file_path, **upload_args)
            elif media_type == "audio":
                await client.send_audio(audio=file_path, **upload_args)
            else:
                await client.send_document(document=file_path, **upload_args)
        except Exception as e:
            logger.error(f"Error uploading file for user {user_id}: {e}")
            await msg.edit("Error uploading file. Please try again.")
            return

        # Increment rename count
        try:
            await codeflixbots.increment_rename_count(user_id)
        except Exception as e:
            logger.error(f"Rename count increment failed for {user_id}: {e}")

        # Dump Channel Logging
        try:
            file_type_label = "📹 Video" if media_type == "video" else "📄 Document" if media_type == "document" else "🎵 Audio"
            dump_caption = (
                f"{file_type_label}\n\n👤 User: {message.from_user.mention}\n🆔 ID: `{message.from_user.id}`\n📁 File: `{new_filename}`"
            )
            dump_args = {
                "chat_id": Config.DUMP_CHANNEL,
                "caption": dump_caption,
                "reply_markup": InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_{message.from_user.id}")]
                ])
            }
            if thumb_path and os.path.exists(thumb_path):
                dump_args["thumb"] = thumb_path

            if media_type == "video":
                await client.send_video(video=file_path, **dump_args)
            elif media_type == "audio":
                await client.send_audio(audio=file_path, **dump_args)
            else:
                await client.send_document(document=file_path, **dump_args)
        except Exception as dump_err:
            logger.warning(f"Failed to send to dump channel: {dump_err}")

        await msg.delete()

    except Exception as e:
        logger.error(f"❌ Processing error for user {user_id}: {e}")
        await message.reply_text(f"Error: {e}")

    finally:
        await cleanup_files(download_path, metadata_path, thumb_path)
        renaming_operations.pop(file_id, None)