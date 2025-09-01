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

# Patterns
SEASON_EPISODE_PATTERNS = [
    # Existing patterns
    (re.compile(r'S(\d+)(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[\s-]*(?:E|EP)(\d+)'), ('season', 'episode')),
    (re.compile(r'Season\s*(\d+)\s*Episode\s*(\d+)', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'S(\d+)E(\d+)'), ('season', 'episode')),
    (re.compile(r'S(\d+)[^\d]*(\d+)'), ('season', 'episode')),
    (re.compile(r'(?:E|EP|Episode)\s*(\d+)', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\b(\d+)\b'), (None, 'episode')),
    # New patterns for [S-04] [E-30] and similar formats
    (re.compile(r'\[S-(\d+)\]\s*\[E-(\d+)\]'), ('season', 'episode')),
    (re.compile(r'\[S(\d+)\]\s*\[E(\d+)\]'), ('season', 'episode')),
    (re.compile(r'\[Season\s*(\d+)\]\s*\[Episode\s*(\d+)\]', re.IGNORECASE), ('season', 'episode')),
    (re.compile(r'\bS-(\d+)\b\s*\bE-(\d+)\b'), ('season', 'episode')),
    # Additional episode patterns for Ep, Ep-, E-, etc.
    (re.compile(r'\b(?:Ep|EP|E|-E|E-)(\d+)\b', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\bEp-(\d+)\b', re.IGNORECASE), (None, 'episode')),
    (re.compile(r'\bEpisode-(\d+)\b', re.IGNORECASE), (None, 'episode')),
    # Season only patterns
    (re.compile(r'\[S-(\d+)\]'), ('season', None)),
    (re.compile(r'\[Season\s*(\d+)\]', re.IGNORECASE), ('season', None)),
    (re.compile(r'\bS-(\d+)\b'), ('season', None)),
]

QUALITY_PATTERNS = [
    # Existing patterns
    (re.compile(r'\b(\d{3,4}[pi])\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(4k|2160p)\b', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\b(2k|1440p)\b', re.IGNORECASE), lambda m: "2k"),
    (re.compile(r'\b(HDRip|HDTV)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(4kX264|4kx265)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'(\d{3,4}[pi])', re.IGNORECASE), lambda m: m.group(1)),
    # New patterns for [1080p], [720p], etc.
    (re.compile(r'\[(\d{3,4}[pi])\]', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\[(4k|2160p)\]', re.IGNORECASE), lambda m: "4k"),
    (re.compile(r'\[(2k|1440p)\]', re.IGNORECASE), lambda m: "2k"),
    # Additional quality patterns
    (re.compile(r'\b(UHD|HD|SD)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(HDR|DV|DolbyVision)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(X264|X265|HEVC)\b', re.IGNORECASE), lambda m: m.group(1)),
    (re.compile(r'\b(1080p|720p|480p)\b', re.IGNORECASE), lambda m: m.group(1)),
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
        raise RuntimeError("FFmpeg not found in PATH")

    metadata = {
        'title': await codeflixbots.get_title(user_id),
        'artist': await codeflixbots.get_artist(user_id),
        'author': await codeflixbots.get_author(user_id),
        'video_title': await codeflixbots.get_video(user_id),
        'audio_title': await codeflixbots.get_audio(user_id),
        'subtitle': await codeflixbots.get_subtitle(user_id)
    }

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
        raise RuntimeError(f"FFmpeg error: {stderr.decode()}")

@Client.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def auto_rename_files(client, message):
    download_path = metadata_path = thumb_path = None
    user_id = message.from_user.id
    format_template = await codeflixbots.get_format_template(user_id)

    if not format_template:
        return await message.reply_text("Please set a rename format using /autorename")

    if message.document:
        file_id, file_name, file_size, media_type = message.document.file_id, message.document.file_name, message.document.file_size, "document"
    elif message.video:
        file_id, file_name, file_size, media_type = message.video.file_id, message.video.file_name or "video", message.video.file_size, "video"
    elif message.audio:
        file_id, file_name, file_size, media_type = message.audio.file_id, message.audio.file_name or "audio", message.audio.file_size, "audio"
    else:
        return await message.reply_text("Unsupported file type")

    if await check_anti_nsfw(file_name, message):
        return await message.reply_text("NSFW content detected")

    if file_id in renaming_operations:
        if (datetime.now() - renaming_operations[file_id]).seconds < 10:
            return
    renaming_operations[file_id] = datetime.now()

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
        caption = await codeflixbots.get_caption(message.chat.id) or f"**{new_filename}**"
        thumb = await codeflixbots.get_thumbnail(message.chat.id)

        if thumb:
            thumb_path = await client.download_media(thumb)
        elif media_type == "video" and message.video.thumbs:
            thumb_path = await client.download_media(message.video.thumbs[0].file_id)

        thumb_path = await process_thumbnail(thumb_path)

        await msg.edit("**Uploading...**")
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

        # ✅ Increment rename count
        try:
            await codeflixbots.increment_rename_count(user_id)
        except Exception as e:
            logger.error(f"Rename count increment failed for {user_id}: {e}")

        # ✅ Dump Channel Logging
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
        logger.error(f"❌ Processing error: {e}")
        await message.reply_text(f"Error: {e}")

    finally:
        await cleanup_files(download_path, metadata_path, thumb_path)
        renaming_operations.pop(file_id, None)