import os
import re
import time
import shutil
import asyncio
import logging
import json
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
    def __init__(self, loop=None):
        self.user_queues = {}
        self.user_semaphores = {}
        self.user_queue_messages = {}
        self.max_concurrent = 5
        self.loop = loop or asyncio.get_event_loop()  # Use provided or default loop
        logger.info("UserDownloadManager initialized")

    def get_queue(self, user_id):
        if user_id not in self.user_queues:
            self.user_queues[user_id] = asyncio.Queue(loop=self.loop)
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent, loop=self.loop)
            self.user_queue_messages[user_id] = None
            logger.info(f"Initialized queue and semaphore for user {user_id}")
        return self.user_queues[user_id]

    def get_semaphore(self, user_id):
        if user_id not in self.user_semaphores:
            self.user_queues[user_id] = asyncio.Queue(loop=self.loop)
            self.user_semaphores[user_id] = asyncio.Semaphore(self.max_concurrent, loop=self.loop)
            self.user_queue_messages[user_id] = None
            logger.info(f"Initialized semaphore for user {user_id}")
        return self.user_semaphores[user_id]

    async def safe_send_message(self, client, chat_id, text, reply_markup=None):
        for attempt in range(3):
            try:
                return await client.send_message(chat_id, text, reply_markup=reply_markup)
            except Exception as e:
                if "TooManyRequests" in str(e):
                    wait = int(str(e).split("retry after ")[1].split(" ")[0]) + 1 if "retry after" in str(e) else 1
                    logger.warning(f"Rate limit hit, retrying after {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Failed to send message: {e}")
                    raise e
        raise Exception("Max retries reached for send_message")

    async def safe_edit_message(self, client, chat_id, message_id, text):
        for attempt in range(3):
            try:
                return await client.edit_message_text(chat_id, message_id, text)
            except Exception as e:
                if "TooManyRequests" in str(e):
                    wait = int(str(e).split("retry after ")[1].split(" ")[0]) + 1 if "retry after" in str(e) else 1
                    logger.warning(f"Rate limit hit, retrying after {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Failed to edit message: {e}")
                    raise e
        raise Exception("Max retries reached for edit_message_text")

    async def add_task(self, user_id, task_data, client, message):
        queue = self.get_queue(user_id)
        await queue.put(task_data)
        logger.info(f"Added task for user {user_id}. Queue size: {queue.qsize()}")

        if queue.qsize() > self.max_concurrent:
            try:
                queue_message = f"Added to Queue ({queue.qsize()} files pending). Use /queue to check status."
                if self.user_queue_messages.get(user_id):
                    await self.safe_edit_message(
                        client,
                        chat_id=message.chat.id,
                        message_id=self.user_queue_messages[user_id],
                        text=queue_message
                    )
                else:
                    msg = await self.safe_send_message(
                        client,
                        chat_id=message.chat.id,
                        text=queue_message
                    )
                    self.user_queue_messages[user_id] = msg.id
            except Exception as e:
                logger.error(f"Failed to send/update queue message for user {user_id}: {e}")

        asyncio.ensure_future(self.process_queue(user_id, client), loop=self.loop)

    async def process_queue(self, user_id, client):
        queue = self.get_queue(user_id)
        semaphore = self.get_semaphore(user_id)

        while not queue.empty():
            async with semaphore:
                task_data = await queue.get()
                try:
                    if self.user_queue_messages.get(user_id):
                        try:
                            if queue.qsize() > 0:
                                await self.safe_edit_message(
                                    client,
                                    chat_id=task_data['message'].chat.id,
                                    message_id=self.user_queue_messages[user_id],
                                    text=f"Processing task. {queue.qsize()} files remaining in queue."
                                )
                            else:
                                await client.delete_messages(
                                    chat_id=task_data['message'].chat.id,
                                    message_ids=self.user_queue_messages[user_id]
                                )
                                self.user_queue_messages[user_id] = None
                        except Exception as e:
                            logger.error(f"Failed to update/delete queue message for user {user_id}: {e}")

                    await task_data['handler'](task_data['client'], task_data['message'])
                except Exception as e:
                    logger.error(f"Task processing error for user {user_id}: {e}")
                finally:
                    queue.task_done()
                    logger.info(f"Task completed for user {user_id}. Queue size: {queue.qsize()}")

    def get_queue_info(self, user_id):
        queue = self.get_queue(user_id)
        tasks = []
        temp_queue = asyncio.Queue(loop=self.loop)
        while not queue.empty():
            task = queue.get_nowait()
            tasks.append(task)
            temp_queue.put_nowait(task)
        while not temp_queue.empty():
            queue.put_nowait(temp_queue.get_nowait())
        return tasks

# Initialize download manager with the default event loop
download_manager = UserDownloadManager(loop=asyncio.get_event_loop())

# Patterns (unchanged)
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

async def get_file_duration(file_path):
    """Get the duration of a media file using ffprobe."""
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        logger.error("ffprobe not found in PATH")
        return None
    cmd = [
        ffprobe, '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'json', file_path
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"ffprobe error: {stderr.decode()}")
            return None
        data = json.loads(stdout.decode())
        duration = float(data.get('format', {}).get('duration', 0))
        return duration
    except Exception as e:
        logger.error(f"Failed to get duration for {file_path}: {e}")
        return None

async def get_video_resolution(file_path):
    """Get the video resolution using ffprobe."""
    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        logger.error("ffprobe not found in PATH")
        return None
    cmd = [
        ffprobe, '-v', 'error', '-show_entries', 'stream=width,height',
        '-of', 'json', file_path
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            logger.error(f"ffprobe error for resolution: {stderr.decode()}")
            return None
        data = json.loads(stdout.decode())
        for stream in data.get('streams', []):
            if stream.get('width') and stream.get('height'):
                return stream['width'], stream['height']
        return None
    except Exception as e:
        logger.error(f"Failed to get resolution for {file_path}: {e}")
        return None

async def add_metadata(input_path, output_path, user_id, media_type):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        logger.error("FFmpeg not found in PATH, copying file without metadata")
        shutil.copy(input_path, output_path)
        return False

    input_duration = await get_file_duration(input_path)
    input_resolution = await get_video_resolution(input_path) if media_type == "video" else None
    if input_duration is None:
        logger.warning("Could not determine input file duration, proceeding with re-encoding")
        reencode_audio = True
    else:
        reencode_audio = False

    enhance_quality = await codeflixbots.get_enhance_quality(user_id) or False
    target_resolution = None
    if enhance_quality and media_type == "video" and input_resolution:
        width, height = input_resolution
        if height <= 480:
            target_resolution = "1280:720"
        elif height <= 720:
            target_resolution = "1920:1080"

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
        '-map', '0'
    ]

    if media_type == "video" and enhance_quality:
        cmd.extend(['-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-b:v', '3000k'])
        if target_resolution:
            cmd.extend(['-vf', f'scale={target_resolution}:force_original_aspect_ratio=decrease,pad={target_resolution}:(ow-iw)/2:(oh-ih)/2'])
    else:
        cmd.extend(['-c:v', 'copy'])

    if reencode_audio or enhance_quality:
        cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
    else:
        cmd.extend(['-c:a', 'copy', '-bsf:a', 'null'])

    cmd.extend(['-loglevel', 'error', output_path])

    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        logger.error(f"FFmpeg error: {stderr.decode()}, attempting fallback")
        cmd = [
            ffmpeg, '-i', input_path,
            '-metadata', f'title={metadata["title"]}',
            '-metadata', f'artist={metadata["artist"]}',
            '-metadata', f'author={metadata["author"]}',
            '-metadata:s:v', f'title={metadata["video_title"]}',
            '-metadata:s:a', f'title={metadata["audio_title"]}',
            '-metadata:s:s', f'title={metadata["subtitle"]}',
            '-map', '0', '-c:v', 'libx264', '-crf', '18', '-preset', 'medium', '-b:v', '3000k',
            '-c:a', 'aac', '-b:a', '192k', '-loglevel', 'error', output_path
        ]
        if target_resolution:
            cmd.extend(['-vf', f'scale={target_resolution}:force_original_aspect_ratio=decrease,pad={target_resolution}:(ow-iw)/2:(oh-ih)/2'])

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"FFmpeg re-encoding failed: {stderr.decode()}, copying file without metadata")
            shutil.copy(input_path, output_path)
            return False

    output_duration = await get_file_duration(output_path)
    if input_duration and output_duration and abs(input_duration - output_duration) > 5:
        logger.warning(f"Duration mismatch: input {input_duration}s, output {output_duration}s")
        return False

    return True

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    user_id = message.from_user.id
    format_template = await codeflixbots.get_format_template(user_id)

    if not format_template:
        try:
            await download_manager.safe_send_message(
                client,
                message.chat.id,
                "Please set a rename format using /autorename"
            )
        except Exception as e:
            logger.error(f"Failed to send reply to user {user_id}: {e}")
        return

    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_size = message.document.file_size
        media_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video"
        file_size = message.video.file_size
        media_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio"
        file_size = message.audio.file_size
        media_type = "audio"
    else:
        try:
            await download_manager.safe_send_message(
                client,
                message.chat.id,
                "Unsupported file type"
            )
        except Exception as e:
            logger.error(f"Failed to send reply to user {user_id}: {e}")
        return

    try:
        if await check_anti_nsfw(file_name, message):
            await download_manager.safe_send_message(client, message.chat.id, "NSFW content detected")
            return
    except Exception as e:
        logger.error(f"NSFW check failed for user {user_id}: {e}")
        await download_manager.safe_send_message(
            client, message.chat.id, "Error checking NSFW content, proceeding with processing"
        )

    if file_id in renaming_operations:
        if (datetime.now() - renaming_operations[file_id]).seconds < 10:
            return
    renaming_operations[file_id] = datetime.now()

    await download_manager.add_task(user_id, {
        'client': client,
        'message': message,
        'handler': process_file,
        'filename': file_name
    }, client, message)

@Client.on_message(filters.command("queue") & filters.private)
async def queue_command(client, message):
    user_id = message.from_user.id
    tasks = download_manager.get_queue_info(user_id)
    queue_size = len(tasks)

    if queue_size == 0:
        await download_manager.safe_send_message(client, message.chat.id, "Your queue is empty.")
        return

    response = f"**Queue Status**\n\nPending files: {queue_size}\n\n"
    for i, task in enumerate(tasks, 1):
        filename = task.get('filename', 'Unknown')
        response += f"{i}. {filename}\n"

    await download_manager.safe_send_message(client, message.chat.id, response)

async def process_file(client, message):
    download_path = metadata_path = thumb_path = None
    user_id = message.from_user.id
    format_template = await codeflixbots.get_format_template(user_id)

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

        ext = os.path.splitext(file_name)[1] or ('.mp4' if media_type == "video" else '.mp3')
        new_filename = f"{format_template}{ext}"
        download_path, metadata_path = f"downloads/{new_filename}", f"metadata/{new_filename}"
        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)

        msg = await download_manager.safe_send_message(client, message.chat.id, "**Downloading...**")
        file_path = await client.download_media(
            message, file_name=download_path,
            progress=progress_for_pyrogram, progress_args=("Downloading...", msg, time.time())
        )

        await download_manager.safe_edit_message(client, message.chat.id, msg.id, "**Processing metadata and enhancing quality...**")
        success = await add_metadata(file_path, metadata_path, user_id, media_type)
        file_path = metadata_path

        if not success:
            await download_manager.safe_edit_message(client, message.chat.id, msg.id, "**Metadata or quality processing failed, using original file...**")
            file_path = download_path

        await download_manager.safe_edit_message(client, message.chat.id, msg.id, "**Preparing upload...**")
        caption = await codeflixbots.get_caption(message.chat.id) or f"**{new_filename}**"
        thumb = await codeflixbots.get_thumbnail(message.chat.id)

        if thumb:
            thumb_path = await client.download_media(thumb)
        elif media_type == "video" and message.video.thumbs:
            thumb_path = await client.download_media(message.video.thumbs[0].file_id)

        thumb_path = await process_thumbnail(thumb_path)

        await download_manager.safe_edit_message(client, message.chat.id, msg.id, "**Uploading...**")
        upload_args = {
            'chat_id': message.chat.id,
            'caption': caption,
            'thumb': thumb_path,
            'progress': progress_for_pyrogram,
            'progress_args': ("Uploading...", msg, time.time())
        }

        if media_type == "video":
            await client.send_video(video=file_path, **upload_args)
        elif media_type == "audio":
            await client.send_audio(audio=file_path, **upload_args)
        else:
            await client.send_document(document=file_path, **upload_args)

        try:
            await codeflixbots.increment_rename_count(user_id)
        except Exception as e:
            logger.error(f"Rename count increment failed for {user_id}: {e}")

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

        await client.delete_messages(message.chat.id, msg.id)

    except Exception as e:
        logger.error(f"❌ Processing error for user {user_id}: {e}")
        await download_manager.safe_send_message(client, message.chat.id, f"Error: {e}")

    finally:
        await cleanup_files(download_path, metadata_path, thumb_path)
        renaming_operations.pop(file_id, None)

@Client.on_message(filters.command("autorename") & filters.private)
async def set_autorename(client, message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        await download_manager.safe_send_message(
            client, message.chat.id,
            "Usage: /autorename <format>\nExample: /autorename S{season}E{episode}_{quality}"
        )
        return
    template = " ".join(message.command[1:])
    try:
        await codeflixbots.set_format_template(user_id, template)
        await download_manager.safe_send_message(
            client, message.chat.id, f"Auto-rename format set to: {template}"
        )
    except Exception as e:
        logger.error(f"Failed to set format template for user {user_id}: {e}")
        await download_manager.safe_send_message(client, message.chat.id, f"Error setting format: {e}")

@Client.on_message(filters.command("enhance_quality") & filters.private)
async def set_enhance_quality(client, message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        await download_manager.safe_send_message(
            client, message.chat.id, "Usage: /enhance_quality on|off"
        )
        return
    state = message.command[1].lower()
    if state not in ["on", "off"]:
        await download_manager.safe_send_message(
            client, message.chat.id, "Invalid state. Use 'on' or 'off'."
        )
        return
    try:
        await codeflixbots.set_enhance_quality(user_id, state == "on")
        await download_manager.safe_send_message(
            client, message.chat.id, f"Video quality enhancement {'enabled' if state == 'on' else 'disabled'}"
        )
    except Exception as e:
        logger.error(f"Failed to set enhance_quality for user {user_id}: {e}")
        await download_manager.safe_send_message(client, message.chat.id, f"Error: {e}")