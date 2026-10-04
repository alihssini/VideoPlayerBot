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

import time
import traceback
from pyrogram import filters
from pyrogram.types import Message
from commandmapper import names, mode_of, mode_label, tag
from config import COMMAND_PREFIXES, DOWNLOAD_MAX_MB
from helpers.user import User
from helpers.decorators import authorized_users_only
from helpers.ytdl import search_youtube, download_file, remove_file
from helpers.media import to_jpg
from helpers.download import with_timeout

USAGE = (
    f"❗ __Send__ {tag('download')} `<song name or link>` __to get the audio file, or__ "
    f"{tag('download')} `{mode_label('video')} <name or link>` __to get the video.__"
)


def _clean(text) -> str:
    return "".join(" " if c in "`*_[]~|" else c for c in str(text)).strip()


def _upload_progress(msg: Message):
    state = {"last": 0.0}

    async def progress(current, total):
        now = time.monotonic()
        if now - state["last"] >= 5:
            state["last"] = now
            pct = f"{current * 100 / total:.0f}%" if total else ""
            try:
                await msg.edit_text(f"📤 `Uploading ... {pct}`")
            except Exception:
                pass

    return progress


@User.on_message(filters.command(names("download"), prefixes=COMMAND_PREFIXES))
@authorized_users_only
async def download(client, m: Message):
    args = m.command[1:]
    kind = "audio"  # a song name gives the audio file unless video is asked for
    if args and mode_of(args[0]):
        kind, args = mode_of(args[0]), args[1:]
    query = " ".join(args).strip()
    if not query:
        return await m.reply_text(USAGE)

    msg = await m.reply_text("🔄 `Processing ...`")
    path = thumb = None
    try:
        if not query.startswith("http"):
            await msg.edit_text("🔎 `Searching ...`")
            found = await search_youtube(query)
            if not found:
                return await msg.edit_text(f"❌ **Nothing found for** `{_clean(query)}` **!**")
            query = found["url"]

        await msg.edit_text(f"🔄 `Downloading the {kind} ...`")
        info = await with_timeout(download_file(query, kind), 900, "the download")
        path = info["path"]
        if info["size"] > DOWNLOAD_MAX_MB * 1024 * 1024:
            return await msg.edit_text(f"❌ **File is larger than {DOWNLOAD_MAX_MB} MB !**")
        thumb = await to_jpg(info["thumb"], width=320) if info.get("thumb") else None

        await msg.edit_text("📤 `Uploading ...`")
        caption = f"{'🎬' if kind == 'video' else '🎵'} **{_clean(info['title'])}**"
        duration = int(info.get("duration") or 0)
        if kind == "audio":
            await m.reply_audio(
                path, caption=caption, title=info["title"], performer=info.get("artist"),
                duration=duration, thumb=thumb, progress=_upload_progress(msg),
            )
        else:
            await m.reply_video(
                path, caption=caption, duration=duration, width=info.get("width") or 0,
                height=info.get("height") or 0, thumb=thumb, supports_streaming=True,
                progress=_upload_progress(msg),
            )
        await msg.delete()
        print(f"[INFO] - sent {kind} '{info['title']}' to {m.chat.id}")
    except Exception as e:
        traceback.print_exc()
        await msg.edit_text(f"❌ **Download Failed !** \n\nError: `{e}`")
    finally:
        remove_file(path)
        remove_file(thumb)
