"""Sends the media that plays now as a file (the ⬇️ button): the local file when there is one (Telegram file,
downloaded video, lyrics video), else a fresh download of its YouTube link."""

import os
from core.errors import UserError
from core.files import FileStore
from core.models import VIDEO, MediaItem
from services.youtube import YouTube, is_youtube, video_id


class Delivery:
    def __init__(self, youtube: YouTube, files: FileStore):
        self.yt, self.files = youtube, files

    async def send(self, sender, chat_id: int, group_id: int, item: MediaItem) -> None:
        if item.live:
            raise UserError("Live streams can't be downloaded.")
        kind = "video" if item.kind == VIDEO else "audio"
        path = None
        if item.source and self.files.owns(item.source) and os.path.isfile(item.source):
            path = self.files.acquire(item.source)
        elif item.origin and is_youtube(item.origin.get("url", "")):
            url = item.origin["url"]
            dest = self.files.path(group_id, f"dl_{video_id(url) or item.key}_{kind}", "x")[:-2]
            async with self.files.lock(dest):
                info = await self.yt.download(url, kind, dest)
            path = self.files.acquire(info.path)
        else:
            raise UserError("This media can't be downloaded (only YouTube and Telegram files).")
        thumb = self.files.acquire(item.thumb) if item.thumb and os.path.isfile(item.thumb) else None
        try:
            caption = f"{'🎬' if kind == 'video' else '🎵'} **{''.join(' ' if c in '`*_[]~|' else c for c in item.name)}**"
            if kind == "audio" and not path.endswith(".mp4"):
                await sender.send_audio(chat_id, path, caption=caption, title=item.title, performer=item.artist,
                                        duration=int(item.duration or 0), thumb=thumb)
            else:
                await sender.send_video(chat_id, path, caption=caption, duration=int(item.duration or 0), thumb=thumb,
                                        supports_streaming=True)
        finally:
            self.files.release(path)
            self.files.release(thumb)
