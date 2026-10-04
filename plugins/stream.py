"""
VideoPlayerBot, Telegram Video Chat Bot
Copyright (c) 2021  Asm Safone <https://github.com/AsmSafone>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>
"""

import os
import sys
import asyncio
import traceback
from pyrogram import filters
from pyrogram.types import Message
from pytgcalls import filters as call_filters
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import AudioQuality, GroupCallConfig, MediaStream, StreamEnded, VideoQuality
from helpers.user import User
from helpers.voice import call_py
from config import COMMAND_PREFIXES, DOWNLOAD_MAX_MB, VIDEO_QUALITY
from helpers.ytdl import YT_REGEX, get_audio_stream, get_video_stream, search_youtube, swap_tracked_file, release_file, remove_file
from helpers.download import download_with_progress, download_thumbnail, with_timeout
from helpers.media import probe, to_jpg, profile_photo
from helpers.decorators import authorized_users_only, sudo_users_only
from commandmapper import names, tag, mode_of
from translations import COMMANDS_LINE

QUALITY = getattr(VideoQuality, VIDEO_QUALITY, VideoQuality.SD_360p)

ACTIVE = {}  # chat_id -> "audio" | "video"
CARDS = {}   # chat_id -> now-playing card: {"msg", "photo", "kind", "title", "link", "chat"}

USAGE = (
    "❗ __Send me a link (YouTube, live stream, radio, direct file) or reply to an audio / video file with__ " + tag("play") + "\n\n"
    + COMMANDS_LINE
)


def _clean(text) -> str:
    """Titles must not break the markdown of the card."""
    return "".join(" " if c in "`*_[]~|" else c for c in str(text)).strip()


def card_text(card: dict, state: str) -> str:
    kind = "🎬 Video" if card["kind"] == "video" else "🎵 Audio"
    lines = [f"{state} **{kind}** in {_clean(card['chat'])}"]
    if card.get("title"):
        name = _clean(card["title"])
        lines.append(f"[{name}]({card['link']})" if card.get("link") else f"**{name}**")
    lines += ["", COMMANDS_LINE]
    return "\n".join(lines)


async def update_card(card, state: str):
    """Change the play state shown on the now-playing card (Playing / Paused / Stopped ...)."""
    if not card:
        return
    text = card_text(card, state)
    try:
        if card["photo"]:
            await card["msg"].edit_caption(text)
        else:
            await card["msg"].edit_text(text, disable_web_page_preview=True)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            print(f"[WARN] - could not update the card: {type(e).__name__}: {e}")


async def announce(m: Message, text: str, photos):
    """Send the card with the first picture that works (track artwork, then the profile picture)."""
    for photo in photos:
        if not photo:
            continue
        try:
            return await m.reply_photo(photo=photo, caption=text), True
        except Exception as e:
            print(f"[WARN] - card picture rejected: {type(e).__name__}: {e}")
    return await m.reply_text(text, disable_web_page_preview=True), False


async def start_stream(m: Message, msg: Message, source: str, kind: str, title=None, link=None, thumb=None):
    chat_id = m.chat.id
    swap_tracked_file(chat_id, source)  # deletes the previous stream's file
    await msg.edit_text("🔄 `Joining the voice chat ...`")
    print(f"[INFO] - starting {kind} stream in {chat_id}")

    if kind == "video":
        stream = MediaStream(source, audio_parameters=AudioQuality.HIGH, video_parameters=QUALITY)
    else:
        stream = MediaStream(source, audio_parameters=AudioQuality.HIGH, video_flags=MediaStream.Flags.IGNORE)

    try:
        await with_timeout(
            call_py.play(chat_id, stream, config=GroupCallConfig(auto_start=False)),
            90,
            f"starting the {kind} stream",
        )
    except NoActiveGroupCall:
        release_file(chat_id)
        raise RuntimeError("There is no active voice chat in this group, start one first!")
    except Exception:
        release_file(chat_id)
        raise

    ACTIVE[chat_id] = kind
    print(f"[INFO] - {kind} stream started in {chat_id}")
    await msg.delete()

    await update_card(CARDS.pop(chat_id, None), "⏹ Replaced")  # the previous card is outdated now
    card = {"kind": kind, "title": title, "link": link, "chat": m.chat.title or "this chat"}
    sent, has_photo = await announce(m, card_text(card, "▶️ Playing"), [thumb, await profile_photo(User)])
    card.update(msg=sent, photo=has_photo)
    CARDS[chat_id] = card
    if thumb:
        remove_file(thumb)  # the downloaded thumbnail is no longer needed


def media_kind(media: Message):
    """"video" / "audio" for a replied message, "unknown" for a generic file, None if it carries no media."""
    if media.video or media.video_note or media.animation:
        return "video"
    if media.audio or media.voice:
        return "audio"
    if media.document:
        mime = media.document.mime_type or ""
        return "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else "unknown"
    return None


def media_title(media: Message):
    if media.audio:
        parts = [p for p in (media.audio.performer, media.audio.title) if p]
        if parts:
            return " - ".join(parts)
    file = media.video or media.audio or media.document
    name = getattr(file, "file_name", None)
    return os.path.splitext(name)[0] if name else None


async def handle_play(client, m: Message, force=None):
    msg = await m.reply_text("🔄 `Processing ...`")
    args = m.command[1:]
    if args and mode_of(args[0]):
        force, args = mode_of(args[0]), args[1:]
    query = " ".join(args).strip()
    media = m.reply_to_message
    if media:
        # file references of older messages expire (FILE_REFERENCE_EXPIRED): fetch the message again for a fresh one
        try:
            media = await client.get_messages(m.chat.id, media.id)
        except Exception as e:
            print(f"[WARN] - could not refresh the replied message: {type(e).__name__}: {e}")
    kind, title, link, thumb = force, None, None, None

    try:
        if query:
            if not query.startswith("http"):
                kind = kind or "audio"  # a song name: music plays as audio unless video is asked for
                await msg.edit_text("🔎 `Searching ...`")
                found = await search_youtube(query)
                if not found:
                    return await msg.edit_text(f"❌ **Nothing found for** `{_clean(query)}` **!**")
                query = found["url"]
            link = query
            if YT_REGEX.match(query):
                kind = kind or "video"
                await msg.edit_text("🔄 `Preparing YouTube stream (downloading if it is a video) ...`")
                try:
                    info = await (get_video_stream if kind == "video" else get_audio_stream)(query)
                except Exception as e:
                    return await msg.edit_text(f"❌ **YouTube Download Error !** \n\n`{e}`")
                source, title = info["source"], info.get("title")
                thumb = await to_jpg(info["thumb"]) if info.get("thumb") else None
            else:
                source = query
                if kind is None:
                    await msg.edit_text("🔄 `Checking the stream ...`")
                    found = await probe(query)
                    kind = "video" if found and found["video"] else "audio"

        elif media and media_kind(media):
            mk = media_kind(media)
            file = media.video or media.video_note or media.animation or media.audio or media.voice or media.document
            if (file.file_size or 0) > DOWNLOAD_MAX_MB * 1024 * 1024:
                return await msg.edit_text(f"❌ **File is larger than {DOWNLOAD_MAX_MB} MB !**")
            title = media_title(media)
            thumbs = getattr(file, "thumbs", None)
            if thumbs:
                thumb = await download_thumbnail(client, thumbs[0].file_id)
            source = await download_with_progress(client, media, msg)
            if kind is None:
                if mk == "unknown":
                    found = await probe(source)
                    if not found or not (found["video"] or found["audio"]):
                        remove_file(source)
                        return await msg.edit_text("❌ **That file has no playable audio or video !**")
                    kind = "video" if found["video"] else "audio"
                else:
                    kind = mk
            if kind == "audio" and not thumb:
                thumb = await to_jpg(source)  # cover art embedded in the audio file

        else:
            return await msg.edit_text(USAGE)

        await start_stream(m, msg, source, kind, title, link, thumb)

    except Exception as e:
        traceback.print_exc()
        await msg.edit_text(f"❌ **An Error Occoured !** \n\nError: `{e}`")


@User.on_message(filters.command(names("play"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def play(client, m: Message):
    await handle_play(client, m)


@User.on_message(filters.command(names("stream"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def stream(client, m: Message):
    await handle_play(client, m, "video")


@User.on_message(filters.command(names("pause"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def pause(_, m: Message):
    kind = ACTIVE.get(m.chat.id)
    if not kind:
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    try:
        await call_py.pause(m.chat.id)
        await m.reply_text(f"⏸ **Paused {kind.capitalize()} Streaming !**")
        await update_card(CARDS.get(m.chat.id), "⏸ Paused")
    except NotInCallError:
        ACTIVE.pop(m.chat.id, None)
        await m.reply_text("❌ **Nothing Is Streaming !**")


@User.on_message(filters.command(names("resume"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def resume(_, m: Message):
    kind = ACTIVE.get(m.chat.id)
    if not kind:
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    try:
        await call_py.resume(m.chat.id)
        await m.reply_text(f"▶️ **Resumed {kind.capitalize()} Streaming !**")
        await update_card(CARDS.get(m.chat.id), "▶️ Playing")
    except NotInCallError:
        ACTIVE.pop(m.chat.id, None)
        await m.reply_text("❌ **Nothing Is Streaming !**")


@User.on_message(filters.command(names("end"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def end_stream(_, m: Message):
    chat_id = m.chat.id
    kind = ACTIVE.pop(chat_id, None)
    release_file(chat_id)
    try:
        await call_py.leave_call(chat_id)
    except NotInCallError:
        return await m.reply_text("🤖 **Please Start A Stream First !**")
    await m.reply_text(f"⏹️ **Stopped {(kind or 'stream').capitalize()} Streaming !**")
    await update_card(CARDS.pop(chat_id, None), "⏹ Stopped")


@User.on_message(filters.command(names("restart"), prefixes=COMMAND_PREFIXES))
@sudo_users_only
async def restart(_, m: Message):
    await m.reply_text("🔄 `Restarting ...`")
    await asyncio.sleep(3)
    os.execl(sys.executable, sys.executable, *sys.argv)


@call_py.on_update(call_filters.stream_end())
async def stream_ended(_, update: StreamEnded):
    chat_id = update.chat_id
    kind = ACTIVE.get(chat_id)
    if kind is None:
        return
    expected = StreamEnded.Type.VIDEO if kind == "video" else StreamEnded.Type.AUDIO
    if not (update.stream_type & expected):
        return
    ACTIVE.pop(chat_id, None)
    release_file(chat_id)
    try:
        await call_py.leave_call(chat_id)
    except Exception as e:
        print(f"[WARN] - could not leave the call of {chat_id}: {type(e).__name__}: {e}")
    print(f"[INFO] - {kind} stream ended in {chat_id}")
    await update_card(CARDS.pop(chat_id, None), "✅ Finished")
