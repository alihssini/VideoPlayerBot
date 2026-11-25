"""/download <song name or link>: the audio (mp3) or video (mp4) as a file in the chat."""

import time
from pyrogram.handlers import MessageHandler
from commandmapper import mode_label, mode_of, tag
from core.errors import Silent, UserError
from plugins.common import cmd, in_group, sender_id, anonymous
from services.youtube import video_id
from ui.replies import Status, clean, command

USAGE = (f"__Send__ {tag('download')} `<song name or link>` __to get the audio file, or__ "
         f"{tag('download')} `{mode_label('video')} <name or link>` __to get the video.__")


def _progress(status):
    state = {"last": 0.0}

    async def progress(current, total):
        now = time.monotonic()
        if now - state["last"] >= 5:
            state["last"] = now
            await status.update(f"📤 `Uploading ... {current * 100 / total:.0f}%`" if total else "📤 `Uploading ...`")
    return progress


def register(app) -> None:
    files, yt = app.files, app.youtube

    @command
    async def download(_, m):
        anonymous(m)
        uid = sender_id(app, m)
        allowed = app.acl.role(uid, m.chat.id) if in_group(m) else app.acl.has_any_role(uid)
        if not allowed:
            raise Silent()
        args, kind = list(m.command[1:]), "audio"
        if args and mode_of(args[0]):
            kind, args = mode_of(args[0]), args[1:]
        query = " ".join(args).strip()
        if not query:
            raise UserError(USAGE)
        async with app.limiter.slot(uid, exempt=app.acl.is_bot_owner(uid)), Status(m) as status:
            if not query.startswith("http"):
                await status.update("🔎 `Searching ...`")
                found = await yt.search(query)
                if not found:
                    raise UserError(f"**Nothing found for** `{clean(query)}`**!**")
                query = found.url
            await status.update(f"🔄 `Downloading the {kind} ...`")
            key = f"dl_{video_id(query) or abs(hash(query))}_{kind}"
            dest = files.path(m.chat.id, key, "x")[:-2]
            async with files.lock(dest):
                info = await yt.download(query, kind, dest)
            path = files.acquire(info.path)
            thumb = None
            try:
                if info.thumb:
                    from services.probe import to_jpg
                    thumb = files.acquire(await to_jpg(info.thumb, files.path(m.chat.id, f"{key}_thumb", "jpg"), width=320))
                await status.update("📤 `Uploading ...`")
                caption = f"{'🎬' if kind == 'video' else '🎵'} **{clean(info.title or 'Unknown')}**"
                if kind == "audio":
                    await m.reply_audio(path, caption=caption, title=info.title, performer=info.artist,
                                        duration=int(info.duration or 0), thumb=thumb, progress=_progress(status))
                else:
                    await m.reply_video(path, caption=caption, duration=int(info.duration or 0), width=info.width or 0,
                                        height=info.height or 0, thumb=thumb, supports_streaming=True, progress=_progress(status))
                await status.done(None)
            finally:
                files.release(path)
                files.release(thumb)

    app.client.add_handler(MessageHandler(download, cmd("download")))
