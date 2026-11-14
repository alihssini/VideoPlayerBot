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
import re
import sys
import time
import asyncio
import traceback
from pyrogram import filters, enums
from pyrogram.types import LinkPreviewOptions, Message
from pytgcalls import filters as call_filters
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import AudioQuality, GroupCallConfig, MediaStream, StreamEnded, VideoQuality
from helpers.user import User, SENT
from helpers.voice import call_py
from config import COMMAND_PREFIXES, DOWNLOAD_MAX_MB, VIDEO_QUALITY
from helpers.ytdl import (
    YT_REGEX, get_audio_stream, get_video_stream, search_youtube,
    swap_tracked_file, release_file, remove_file, protect_file, unprotect_file, drop_file,
)
from helpers.download import download_with_progress, download_thumbnail, with_timeout
from helpers.media import probe, to_jpg, profile_photo, duration
from helpers.lyrics import find_lyrics, render_video, output_path, has_arabic_script, LYRICS_MAX_SECONDS
from helpers.decorators import authorized_users_only, sudo_users_only
from commandmapper import names, tag, mode_of
from translations import COMMANDS_LINE

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
QUALITY = getattr(VideoQuality, VIDEO_QUALITY, VideoQuality.SD_360p)
PLAIN_TEXT = enums.ParseMode.DISABLED
MAX_QUEUE = int(os.getenv("MAX_QUEUE") or 10)  # items that may wait in the queue of one chat

ACTIVE = {}   # chat_id -> "audio" | "video"
CARDS = {}    # chat_id -> now-playing card: {"msg", "photo", "kind", "title", "link", "chat"}
QUEUES = {}   # chat_id -> list of resolved items (see resolve_item) waiting to be played
LOCKS = {}    # chat_id -> asyncio.Lock, so starting / queueing / skipping never run at the same time
STARTED = {}  # chat_id -> time.monotonic() of the last stream start
LOOPS = {}    # chat_id -> True while the current media repeats (reset when another item starts)
VOLUMES = {}  # chat_id -> volume (1-200) chosen with the volume command, applied again for every new stream
PLAYING = {}  # chat_id -> running stream: {"source", "kind", "duration", "base" (second it started at), "since" (monotonic, None while paused)}
TICKERS = {}  # chat_id -> asyncio.Task that keeps the progress line of the card up to date
PROGRESS_EVERY = int(os.getenv("PROGRESS_EVERY") or 10)  # seconds between progress updates of the card
BAR_WIDTH = 14
UNITS = {"s": 1, "m": 60, "h": 3600}
SEEK_RE = re.compile(r"^([+-])?\s*(\d+(?:[.,]\d+)?)\s*([smh])?$", re.IGNORECASE)

USAGE = (
    "❗ __Send me a link (YouTube, live stream, radio, direct file) or reply to an audio / video file with__ " + tag("play") + "\n\n"
    + COMMANDS_LINE
)


def _lock(chat_id) -> asyncio.Lock:
    return LOCKS.setdefault(chat_id, asyncio.Lock())


def _clean(text) -> str:
    """Titles must not break the markdown of the card."""
    return "".join(" " if c in "`*_[]~|" else c for c in str(text)).strip()


def _name(item: dict) -> str:
    return _clean(item.get("title") or item.get("link") or "Untitled stream")


def card_text(card: dict, state: str) -> str:
    kind = "🎬 Video" if card["kind"] == "video" else "🎵 Audio"
    lines = [f"{state}{' 🔁' if card.get('loop') else ''} **{kind}** in {_clean(card['chat'])}"]
    if card.get("title"):
        name = _clean(card["title"])
        lines.append(f"[{name}]({card['link']})" if card.get("link") else f"**{name}**")
    lines += ["", progress_line(card, state)]
    return "\n".join(lines)


async def update_card(card, state: str):
    """Change the play state shown on the now-playing card (Playing / Paused / Stopped ...)."""
    if not card:
        return
    card["state"] = state
    text = card_text(card, state)
    try:
        if card["photo"]:
            await card["msg"].edit_caption(text)
        else:
            await card["msg"].edit_text(text, link_preview_options=NO_PREVIEW)
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            print(f"[WARN] - could not update the card: {type(e).__name__}: {e}")


def build_stream(source, kind: str, start: int = 0, volume: int = 100) -> MediaStream:
    """The stream to play; start > 0 begins that many seconds into the media (jump command),
    volume (1-200, 100 = unchanged) is applied to the audio by ffmpeg because Telegram's own
    participant volume has no effect on what the bot itself sends."""
    params = []
    if start:
        params.append(f"-ss {int(start)}")
    if volume != 100:
        params.append(f"--audio ---mid -af volume={volume / 100:.2f}")
    extra = {"ffmpeg_parameters": " ".join(params)} if params else {}
    if kind == "video":
        return MediaStream(source, audio_parameters=AudioQuality.HIGH, video_parameters=QUALITY, **extra)
    return MediaStream(source, audio_parameters=AudioQuality.HIGH, video_flags=MediaStream.Flags.IGNORE, **extra)


def fmt_time(seconds) -> str:
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def position(chat_id) -> float:
    """Seconds played of the current stream (seeks and pauses included)."""
    play = PLAYING.get(chat_id)
    if not play:
        return 0.0
    pos = play["base"] + (time.monotonic() - play["since"] if play["since"] is not None else 0.0)
    return min(pos, play["duration"]) if play["duration"] else pos


def mark_paused(chat_id):
    play = PLAYING.get(chat_id)
    if play and play["since"] is not None:
        play["base"] = position(chat_id)
        play["since"] = None


def mark_resumed(chat_id):
    play = PLAYING.get(chat_id)
    if play and play["since"] is None:
        play["since"] = time.monotonic()


def progress_line(card: dict, state: str = "") -> str:
    """e.g. `01:23 ━━━●────────── 04:56`; only the elapsed time when the length is unknown (live streams)."""
    dur, pos = card.get("dur"), card.get("pos") or 0
    if state.startswith("✅") and dur:
        pos = dur
    if not dur:
        return f"⏱ `{fmt_time(pos)}`"
    at = min(BAR_WIDTH - 1, int(min(pos, dur) / dur * (BAR_WIDTH - 1)))
    bar = "━" * at + "●" + "─" * (BAR_WIDTH - 1 - at)
    return f"`{fmt_time(pos)} {bar} {fmt_time(dur)}`"


async def refresh_card(chat_id, state: str):
    card = CARDS.get(chat_id)
    if card:
        card["pos"] = position(chat_id)
    await update_card(card, state)


async def _tick(chat_id, card: dict):
    try:
        while True:
            await asyncio.sleep(PROGRESS_EVERY)
            if CARDS.get(chat_id) is not card or not ACTIVE.get(chat_id):
                return
            if card.get("state") != "▶️ Playing":
                continue
            card["pos"] = position(chat_id)
            await update_card(card, "▶️ Playing")
    except asyncio.CancelledError:
        pass


def stop_ticker(chat_id):
    task = TICKERS.pop(chat_id, None)
    if task:
        task.cancel()


def start_ticker(chat_id, card: dict):
    stop_ticker(chat_id)
    TICKERS[chat_id] = asyncio.create_task(_tick(chat_id, card))


def forget(chat_id):
    """The stream of this chat is over: stop tracking its position."""
    stop_ticker(chat_id)
    PLAYING.pop(chat_id, None)
    LOOPS.pop(chat_id, None)


async def make_lyrics_video(source, title, length, cover, msg):
    """Look up synced lyrics for the song and render them into a video with its audio.
    Returns (video path, None) or (None, reason text shown to the user)."""
    if not title:
        return None, "there is no song title to search the lyrics for"
    if not length:
        return None, "the length of the media is unknown (live stream?)"
    if length > LYRICS_MAX_SECONDS:
        return None, f"it is longer than {LYRICS_MAX_SECONDS // 60} minutes"
    await msg.edit_text("🎤 `Looking for lyrics ...`")
    found = await find_lyrics(title, length)
    if not found:
        hint = f" (Persian names often only match in English letters, try {tag('lyrics')} `Artist - Song`)" if has_arabic_script(title) else ""
        return None, "no synced lyrics were found for it" + hint
    await msg.edit_text(f"🎞 `Rendering the lyrics video ...`\n`{_clean(found['artist'])} - {_clean(found['title'])}`")
    heading = f"{found['artist']} - {found['title']}" if found["artist"] else found["title"]
    own_cover = None
    if not cover:
        cover = own_cover = await to_jpg(source)  # cover art embedded in the audio file, if any
    try:
        return await render_video(found["lines"], length, source, cover, heading, output_path(source, title)), None
    except Exception as e:
        print(f"[WARN] - lyrics video failed: {type(e).__name__}: {e}")
        return None, "the lyrics video could not be made"
    finally:
        drop_file(own_cover)


async def add_lyrics(item: dict, msg: Message) -> dict:
    """Turn a resolved audio item into a lyrics video (in place). item["note"] tells why it stays as it is."""
    if item["kind"] != "audio":
        item["note"] = "🎤 **Lyrics are for songs**, this one plays as it is."
        return item
    video, why = await make_lyrics_video(item["source"], item.get("title"), await duration(item["source"]), item.get("thumb"), msg)
    if not video:
        item["note"] = f"🎤 **Playing the music only**, {why}."
        return item
    old, item["source"], item["kind"], item["lyrics"] = item["source"], video, "video", True
    drop_file(old)  # the audio file is inside the video now
    return item


async def announce(chat_id, text: str, photos, m: Message = None):
    """Send the card with the first picture that works (track artwork, then the profile picture).
    Replies to the command message m when there is one (queue advance has none)."""
    for photo in photos:
        if not photo:
            continue
        try:
            if m:
                return await m.reply_photo(photo=photo, caption=text), True
            return await User.send_photo(chat_id, photo=photo, caption=text), True
        except Exception as e:
            print(f"[WARN] - card picture rejected: {type(e).__name__}: {e}")
    if m:
        return await m.reply_text(text, link_preview_options=NO_PREVIEW), False
    return await User.send_message(chat_id, text, link_preview_options=NO_PREVIEW), False


async def start_stream(chat_id: int, item: dict, m: Message = None, msg: Message = None, old_state: str = "⏹ Replaced"):
    """Play a resolved item now (replacing whatever plays) and post its now-playing card."""
    source, kind, thumb = item["source"], item["kind"], item.get("thumb")
    swap_tracked_file(chat_id, source)  # deletes the previous stream's file
    if msg:
        await msg.edit_text("🔄 `Joining the voice chat ...`")
    print(f"[INFO] - starting {kind} stream in {chat_id}")

    stream = build_stream(source, kind, volume=VOLUMES.get(chat_id, 100))

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
    STARTED[chat_id] = time.monotonic()
    LOOPS.pop(chat_id, None)
    PLAYING[chat_id] = {"source": source, "kind": kind, "duration": await duration(source), "base": 0.0, "since": time.monotonic()}
    print(f"[INFO] - {kind} stream started in {chat_id}")
    if msg:
        await msg.delete()

    stop_ticker(chat_id)
    await update_card(CARDS.pop(chat_id, None), old_state)  # the previous card is outdated now
    card = {"kind": kind, "title": item.get("title"), "link": item.get("link"), "chat": item.get("chat") or "this chat",
            "state": "▶️ Playing", "pos": 0, "dur": PLAYING[chat_id]["duration"]}
    sent, has_photo = await announce(chat_id, card_text(card, "▶️ Playing"), [thumb, await profile_photo(User)], m)
    card.update(msg=sent, photo=has_photo)
    CARDS[chat_id] = card
    start_ticker(chat_id, card)
    if thumb:
        drop_file(thumb)  # the downloaded thumbnail is no longer needed


def clear_queue(chat_id) -> int:
    """Forget everything waiting in this chat and delete its files. Returns how many items were dropped."""
    items = QUEUES.pop(chat_id, [])
    for item in items:
        for path in (item["source"], item.get("thumb")):
            unprotect_file(path)
            drop_file(path)
    return len(items)


async def finish(chat_id, state: str):
    """Nothing more to play: leave the call and close the card."""
    ACTIVE.pop(chat_id, None)
    forget(chat_id)
    release_file(chat_id)
    try:
        await call_py.leave_call(chat_id)
    except Exception as e:
        print(f"[WARN] - could not leave the call of {chat_id}: {type(e).__name__}: {e}")
    await update_card(CARDS.pop(chat_id, None), state)


async def advance(chat_id, old_state: str):
    """Play the next queued item (items that fail to start are skipped).
    Returns the item now playing, or None when the queue ran out, in which case the call is left.
    The caller holds the chat lock."""
    queue = QUEUES.get(chat_id) or []
    while queue:
        item = queue.pop(0)
        unprotect_file(item["source"])
        unprotect_file(item.get("thumb"))
        try:
            await start_stream(chat_id, item, old_state=old_state)
            return item
        except Exception as e:
            print(f"[WARN] - could not play the queued item in {chat_id}: {type(e).__name__}: {e}")
            drop_file(item.get("thumb"))
            try:
                await User.send_message(chat_id, f"⚠️ **Could not play** `{_name(item)}` **, skipped!**\n\n`{e}`")
            except Exception:
                pass
    QUEUES.pop(chat_id, None)
    await finish(chat_id, old_state)
    return None


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


async def is_playing(chat_id) -> bool:
    """True while this chat really has a running stream (ACTIVE alone can be stale if the call was closed from outside)."""
    if not ACTIVE.get(chat_id):
        return False
    try:
        if chat_id in await call_py.calls:
            return True
    except Exception as e:
        print(f"[WARN] - could not read the call list: {type(e).__name__}: {e}")
        return True
    ACTIVE.pop(chat_id, None)  # the call is gone: nothing plays any more
    forget(chat_id)
    release_file(chat_id)
    clear_queue(chat_id)
    await update_card(CARDS.pop(chat_id, None), "⏹ Stopped")
    return False


async def resolve_item(client, m: Message, msg: Message, force=None, args=None, chat_title=None):
    """Turn the command into a ready-to-play item: {"source", "kind", "title", "link", "thumb", "chat"}.
    Returns None after it has told the user why nothing can be played."""
    # args / chat_title are set by the private-chat play command (plugins/dmplay.py): the target group is not m.chat there
    private_target = args is not None
    args = m.command[1:] if args is None else args
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
    if private_target and not query and media and not media_kind(media):
        # a replied text message with a link in it
        found_link = re.search(r"https?://\S+", media.text or media.caption or "")
        if found_link:
            query = found_link.group(0)

    if query:
        if not query.startswith("http"):
            kind = kind or "audio"  # a song name: music plays as audio unless video is asked for
            await msg.edit_text("🔎 `Searching ...`")
            found = await search_youtube(query)
            if not found:
                await msg.edit_text(f"❌ **Nothing found for** `{_clean(query)}` **!**")
                return None
            query = found["url"]
        link = query
        if YT_REGEX.match(query):
            kind = kind or "video"
            await msg.edit_text("🔄 `Preparing YouTube stream (downloading if it is a video) ...`")
            try:
                info = await (get_video_stream if kind == "video" else get_audio_stream)(query)
            except Exception as e:
                await msg.edit_text(f"❌ **YouTube Download Error !** \n\n`{e}`")
                return None
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
            await msg.edit_text(f"❌ **File is larger than {DOWNLOAD_MAX_MB} MB !**")
            return None
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
                    await msg.edit_text("❌ **That file has no playable audio or video !**")
                    return None
                kind = "video" if found["video"] else "audio"
            else:
                kind = mk
        if kind == "audio" and not thumb:
            thumb = await to_jpg(source)  # cover art embedded in the audio file

    else:
        await msg.edit_text(USAGE)
        return None

    return {"source": source, "kind": kind, "title": title, "link": link, "thumb": thumb, "chat": chat_title or m.chat.title or "this chat"}


async def handle_play(client, m: Message, force=None, lyrics=False, target=None, args=None):
    """target = {"id", "title"} of the group to play in when the command came from a private chat (plugins/dmplay.py)."""
    chat_id = target["id"] if target else m.chat.id
    msg = await m.reply_text("🔄 `Processing ...`")

    if await is_playing(chat_id) and len(QUEUES.get(chat_id, [])) >= MAX_QUEUE:
        return await msg.edit_text(f"❌ **The queue is full** ({MAX_QUEUE} items)! Wait for a track to finish or use `{COMMAND_PREFIXES[0]}{names('next')[0]}`.")

    item = None
    try:
        item = await resolve_item(client, m, msg, force, args=args, chat_title=target["title"] if target else None)
        if item is None:
            return
        note = None
        if lyrics:
            item = await add_lyrics(item, msg)
            note = item.pop("note", None)

        async with _lock(chat_id):
            if await is_playing(chat_id):
                queue = QUEUES.setdefault(chat_id, [])
                if len(queue) >= MAX_QUEUE:
                    drop_file(item["source"])
                    drop_file(item.get("thumb"))
                    return await msg.edit_text(f"❌ **The queue is full** ({MAX_QUEUE} items)!")
                queue.append(item)
                protect_file(item["source"])  # the sweeper and a finishing stream must not delete it
                protect_file(item.get("thumb"))
                item = None  # now owned by the queue
                return await msg.edit_text(
                    f"➕ **Added to the queue** (#{len(queue)})" + (f" of {_clean(target['title'])}" if target else "") + f"\n`{_name(queue[-1])}`\n\n"
                    f"Next: {tag('next')} · list: {tag('queue')}" + (f"\n\n{note}" if note else "")
                )
            await start_stream(chat_id, item, None if target else m, msg)  # no m: the card goes to the group, not to the private chat
            item = None
        if target:
            await m.reply_text(f"▶️ Started in {target['title']}", parse_mode=PLAIN_TEXT)
        if note:
            await m.reply_text(note)

    except Exception as e:
        traceback.print_exc()
        if item:  # resolved but never played or queued: do not leave its files behind
            drop_file(item["source"])
            drop_file(item.get("thumb"))
        await msg.edit_text(f"❌ **An Error Occoured !** \n\nError: `{e}`")


@User.on_message(filters.command(names("play"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def play(client, m: Message):
    await handle_play(client, m)


@User.on_message(filters.command(names("stream"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def stream(client, m: Message):
    await handle_play(client, m, "video")


@User.on_message(filters.command(names("next"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def next_media(_, m: Message):
    chat_id = m.chat.id
    if not await is_playing(chat_id):
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    if not QUEUES.get(chat_id):
        return await m.reply_text(f"❌ **The queue is empty**, there is nothing to skip to! Use {tag('end')} to stop.")
    async with _lock(chat_id):
        item = await advance(chat_id, "⏭ Skipped")
    if item is None:
        await m.reply_text("⏹️ **None of the queued items could be played, the stream was stopped.**")


@User.on_message(filters.command(names("queue"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def show_queue(_, m: Message):
    chat_id = m.chat.id
    playing = await is_playing(chat_id)
    queue = QUEUES.get(chat_id, [])
    if not playing and not queue:
        return await m.reply_text("📭 **Nothing is playing and the queue is empty.**")
    lines = ["📋 **Queue**", ""]
    card = CARDS.get(chat_id)
    if playing and card:
        lines.append(f"▶️ **Now:** `{_name(card)}`")
    if queue:
        lines.append("")
        lines += [f"{i}. {'🎬' if it['kind'] == 'video' else '🎵'} `{_name(it)}`" for i, it in enumerate(queue, 1)]
        lines += ["", f"{len(queue)}/{MAX_QUEUE} · skip with {tag('next')}"]
    else:
        lines += ["", "__Nothing queued after this, send__ " + tag("play") + " __to add more.__"]
    await m.reply_text("\n".join(lines), link_preview_options=NO_PREVIEW)


@User.on_message(filters.command(names("pause"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def pause(_, m: Message):
    kind = ACTIVE.get(m.chat.id)
    if not kind:
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    try:
        await call_py.pause(m.chat.id)
        mark_paused(m.chat.id)
        await m.reply_text(f"⏸ **Paused {kind.capitalize()} Streaming !**")
        await refresh_card(m.chat.id, "⏸ Paused")
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
        mark_resumed(m.chat.id)
        await m.reply_text(f"▶️ **Resumed {kind.capitalize()} Streaming !**")
        await refresh_card(m.chat.id, "▶️ Playing")
    except NotInCallError:
        ACTIVE.pop(m.chat.id, None)
        await m.reply_text("❌ **Nothing Is Streaming !**")


@User.on_message(filters.command(names("end"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def end_stream(_, m: Message):
    chat_id = m.chat.id
    async with _lock(chat_id):
        kind = ACTIVE.pop(chat_id, None)
        forget(chat_id)
        dropped = clear_queue(chat_id)
        release_file(chat_id)
        try:
            await call_py.leave_call(chat_id)
        except NotInCallError:
            return await m.reply_text("🤖 **Please Start A Stream First !**")
    extra = f" The queue ({dropped}) was cleared." if dropped else ""
    await m.reply_text(f"⏹️ **Stopped {(kind or 'stream').capitalize()} Streaming !**{extra}")
    await update_card(CARDS.pop(chat_id, None), "⏹ Stopped")


def parse_seek(text: str, default_sign: int):
    """"+30s" -> 30, "-10" -> -10, "+2m" -> 120, "1h" -> 3600 * default_sign. A written + / - beats the command's own direction.
    No unit means seconds. Returns None if the text is not a time."""
    found = SEEK_RE.match(text.strip())
    if not found:
        return None
    sign, number, unit = found.groups()
    seconds = int(round(float(number.replace(",", ".")) * UNITS[(unit or "s").lower()]))
    return seconds * (default_sign if not sign else 1 if sign == "+" else -1)


async def handle_seek(m: Message, default_sign: int):
    chat_id = m.chat.id
    example = f"{tag('jump')} `30` · {tag('jump')} `+5m` · {tag('jump')} `-10` · {tag('jump')} `-40s` · `h` = hours"
    if not await is_playing(chat_id):
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    delta = parse_seek("".join(m.command[1:]), default_sign)
    if not delta:
        return await m.reply_text(f"❗ __Tell me how far to jump, with s / m / h (seconds / minutes / hours, no unit = seconds):__\n\n{example}")

    async with _lock(chat_id):
        play = PLAYING.get(chat_id)
        if not play or not ACTIVE.get(chat_id):
            return await m.reply_text("❌ **Nothing Is Streaming !**")
        if not play["duration"]:
            return await m.reply_text("❌ **This is a live stream, it cannot be moved.**")
        target = max(0.0, position(chat_id) + delta)
        if target >= play["duration"] - 1:
            return await m.reply_text(f"❌ **That is past the end** ({fmt_time(play['duration'])}). Use {tag('next')} or {tag('end')}.")
        card = CARDS.get(chat_id)
        paused = bool(card) and card.get("state") == "⏸ Paused"
        try:
            await with_timeout(
                call_py.play(chat_id, build_stream(play["source"], play["kind"], int(target), VOLUMES.get(chat_id, 100)), config=GroupCallConfig(auto_start=False)),
                60,
                "jumping to the new position",
            )
            if paused:
                await call_py.pause(chat_id)
        except Exception as e:
            traceback.print_exc()
            return await m.reply_text(f"❌ **Could not jump !** \n\nError: `{e}`")
        STARTED[chat_id] = time.monotonic()  # the old stream's end event must not skip to the next item
        play["base"] = float(int(target))
        play["since"] = None if paused else time.monotonic()
        arrow = "⏩" if delta > 0 else "⏪"
        print(f"[INFO] - jumped {delta:+d}s in {chat_id}, now at {fmt_time(target)}")
    await m.reply_text(f"{arrow} **Jumped to** `{fmt_time(target)}` / `{fmt_time(play['duration'])}`")
    await refresh_card(chat_id, "⏸ Paused" if paused else "▶️ Playing")


@User.on_message(filters.command(names("jump"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def jump(_, m: Message):
    await handle_seek(m, 1)  # no sign = ahead, "-" = back


async def lyrics_current(m: Message):
    """/lyrics without a name: the song that plays now continues as a lyrics video from the same position."""
    chat_id = m.chat.id
    if not await is_playing(chat_id):
        return await m.reply_text(
            f"❗ __Send__ {tag('lyrics')} `<song name or link>` __to play a song with its lyrics, or send__ {tag('lyrics')} __while a song plays.__"
        )
    play, card = PLAYING.get(chat_id), CARDS.get(chat_id)
    if not play or not card:
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    if play.get("lyrics"):
        return await m.reply_text("🎤 **The lyrics are already showing.**")
    if play["kind"] == "video":
        return await m.reply_text("🎤 **Lyrics are for songs**, this is a video.")

    msg = await m.reply_text("🎤 `Looking for lyrics ...`")
    source = play["source"]
    video, why = await make_lyrics_video(source, card.get("title"), play["duration"], None, msg)
    if not video:
        return await msg.edit_text(f"🎤 **The song keeps playing as it is**, {why}.")

    try:
        async with _lock(chat_id):
            play = PLAYING.get(chat_id)
            if not play or play["source"] != source or not ACTIVE.get(chat_id):
                drop_file(video)
                return await msg.edit_text("🎤 **The song changed while the video was made**, nothing was changed.")
            card = CARDS.get(chat_id)
            paused = bool(card) and card.get("state") == "⏸ Paused"
            target = int(position(chat_id))
            await with_timeout(
                call_py.play(chat_id, build_stream(video, "video", target, VOLUMES.get(chat_id, 100)), config=GroupCallConfig(auto_start=False)),
                60,
                "starting the lyrics video",
            )
            if paused:
                await call_py.pause(chat_id)
            swap_tracked_file(chat_id, video)  # deletes the audio file that played before
            ACTIVE[chat_id] = "video"
            STARTED[chat_id] = time.monotonic()  # the old stream's end event must not skip to the next item
            play.update(source=video, kind="video", lyrics=True, base=float(target), since=None if paused else time.monotonic())
            if card:
                card["kind"] = "video"
    except Exception as e:
        traceback.print_exc()
        drop_file(video)
        return await msg.edit_text(f"❌ **Could not start the lyrics video !** \n\nError: `{e}`")
    await msg.delete()
    await refresh_card(chat_id, "⏸ Paused" if paused else "▶️ Playing")


@User.on_message(filters.command(names("lyrics"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def lyrics(client, m: Message):
    reply = m.reply_to_message
    if m.command[1:] or (reply and media_kind(reply)):
        return await handle_play(client, m, "audio", lyrics=True)
    await lyrics_current(m)


@User.on_message(filters.command(names("loop"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def loop(_, m: Message):
    chat_id = m.chat.id
    if not await is_playing(chat_id):
        return await m.reply_text("❌ **Nothing Is Streaming !**")
    play = PLAYING.get(chat_id)
    if not play or not play["duration"]:
        return await m.reply_text("❌ **A live stream cannot be repeated.**")
    arg = "".join(m.command[1:]).strip().lower()
    if arg in ("on", "1", "yes"):
        enable = True
    elif arg in ("off", "0", "no"):
        enable = False
    elif not arg:
        enable = not LOOPS.get(chat_id)
    else:
        return await m.reply_text(f"❗ __Use__ {tag('loop')} __to switch it on / off, or__ {tag('loop')} `on` / {tag('loop')} `off`")
    if enable:
        LOOPS[chat_id] = True
    else:
        LOOPS.pop(chat_id, None)
    card = CARDS.get(chat_id)
    if card:
        card["loop"] = enable
        card["pos"] = position(chat_id)
        await update_card(card, card.get("state") or "▶️ Playing")
    await m.reply_text("🔁 **Repeating the current media** until you send " + tag("loop") + " again." if enable else "➡️ **Repeat is off**, the queue continues after this media.")


@User.on_message(filters.command(names("vol"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def volume(_, m: Message):
    chat_id = m.chat.id
    arg = "".join(m.command[1:]).strip().rstrip("%")
    if not arg:
        return await m.reply_text(f"🔊 **Volume:** `{VOLUMES.get(chat_id, 100)}`  (1-200, 100 = normal)\n\n{tag('vol')} `<1-200>` to change it")
    if not arg.isdigit() or not 1 <= int(arg) <= 200:
        return await m.reply_text(f"❗ __The volume must be a whole number from 1 to 200 (100 = normal):__ {tag('vol')} `80`")
    level = int(arg)
    if not await is_playing(chat_id):
        VOLUMES[chat_id] = level
        return await m.reply_text(f"🔊 **Volume saved:** `{level}` (applied when something plays)")
    if level == VOLUMES.get(chat_id, 100):
        return await m.reply_text(f"🔊 **Volume is already** `{level}`")
    async with _lock(chat_id):
        play = PLAYING.get(chat_id)
        if not play or not ACTIVE.get(chat_id):
            return await m.reply_text("❌ **Nothing Is Streaming !**")
        card = CARDS.get(chat_id)
        paused = bool(card) and card.get("state") == "⏸ Paused"
        target = int(position(chat_id)) if play["duration"] else 0
        try:
            await with_timeout(
                call_py.play(chat_id, build_stream(play["source"], play["kind"], target, level), config=GroupCallConfig(auto_start=False)),
                60,
                "changing the volume",
            )
            if paused:
                await call_py.pause(chat_id)
        except Exception as e:
            traceback.print_exc()
            return await m.reply_text(f"❌ **Could not change the volume !** \n\nError: `{e}`")
        VOLUMES[chat_id] = level
        STARTED[chat_id] = time.monotonic()  # the old stream's end event must not skip to the next item
        if play["duration"]:
            play["base"] = float(target)
            play["since"] = None if paused else time.monotonic()
        else:  # live stream: no position to keep
            play["base"], play["since"] = 0.0, (None if paused else time.monotonic())
    await m.reply_text(f"🔊 **Volume set to** `{level}`")


@User.on_message(filters.command(names("delete"), prefixes=COMMAND_PREFIXES) & filters.group)
@authorized_users_only
async def delete_messages(client, m: Message):
    chat_id = m.chat.id
    target = m.reply_to_message
    if target:
        if not (target.from_user and target.from_user.is_self):
            return await m.reply_text("❌ **I can only delete my own messages.**")
        ids = [target.id]
    else:
        ids = list(SENT.get(chat_id, []))
    ids = [i for i in ids if i != m.id]
    if not ids:
        return await m.reply_text("📭 **I have no messages to delete here.**")
    deleted = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            await client.delete_messages(chat_id, chunk)
            deleted += len(chunk)
        except Exception as e:
            print(f"[WARN] - could not delete messages in {chat_id}: {type(e).__name__}: {e}")
    SENT[chat_id] = [i for i in SENT.get(chat_id, []) if i not in ids]
    card = CARDS.get(chat_id)
    if card and card["msg"].id in ids:  # the now-playing card is gone: stop updating it
        CARDS.pop(chat_id, None)
        stop_ticker(chat_id)
    try:
        await m.delete()  # the command itself (works for the account's own messages)
    except Exception:
        pass


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
    if time.monotonic() - STARTED.get(chat_id, 0) < 3:
        return  # late end event of the stream that was just replaced, not of the new one
    print(f"[INFO] - {kind} stream ended in {chat_id}")
    async with _lock(chat_id):
        if ACTIVE.get(chat_id) is None:  # /end ran while waiting for the lock
            return
        play = PLAYING.get(chat_id)
        if LOOPS.get(chat_id) and play:
            try:
                await with_timeout(
                    call_py.play(chat_id, build_stream(play["source"], play["kind"], 0, VOLUMES.get(chat_id, 100)), config=GroupCallConfig(auto_start=False)),
                    60,
                    "repeating the media",
                )
                STARTED[chat_id] = time.monotonic()
                play["base"], play["since"] = 0.0, time.monotonic()
                card = CARDS.get(chat_id)
                if card:
                    card["pos"] = 0
                print(f"[INFO] - looped the {kind} stream in {chat_id}")
                return
            except Exception:
                traceback.print_exc()
                LOOPS.pop(chat_id, None)
                if CARDS.get(chat_id):
                    CARDS[chat_id]["loop"] = False
        try:
            await advance(chat_id, "✅ Finished")
        except Exception:
            traceback.print_exc()
            await finish(chat_id, "✅ Finished")
