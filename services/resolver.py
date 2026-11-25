"""Turns a /play request (song name, link, replied audio / video / link) into a MediaItem.

YouTube audio is a direct URL that expires: it is resolved now and again right before playing when it got old.
YouTube videos are downloaded now when they play at once, else lazily when they reach the head of the queue
(the player pre-fetches the next one), so a long queue does not fill the disk."""

import os
import re
import time
import hashlib
import logging
from core.errors import UserError
from core.files import FileStore
from core.models import AUDIO, VIDEO, MediaItem, Requester
from services import probe, telegram_media as tgm
from services.youtube import YouTube, is_youtube
from ui.replies import clean

log = logging.getLogger("vpb.resolver")
URL_MAX_AGE = 3600          # re-resolve YouTube audio URLs older than this before playing


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


class NullStatus:
    """Status sink when nobody waits for an answer (restore after restart)."""

    async def update(self, text: str) -> None:
        pass


def is_playlist(url: str) -> bool:
    return "youtube.com/playlist" in url or ("list=" in url and "v=" not in url and "youtu.be/" not in url)


class MediaResolver:
    def __init__(self, client, youtube: YouTube, files: FileStore, max_bytes: int, video_mode: str = "stream"):
        self.client, self.yt, self.files, self.max_bytes = client, youtube, files, max_bytes
        self.stream_video = video_mode == "stream"

    async def resolve(self, m, chat_id: int, query: str, kind: str | None, status, requester: Requester | None,
                      eager: bool) -> MediaItem:
        """kind None = detect. eager = it plays right away (prepare now, show progress)."""
        media = m.reply_to_message
        if media:   # file references of older messages expire: fetch the message again for a fresh one
            try:
                media = await self.client.get_messages(m.chat.id, media.id)
            except Exception as e:
                log.warning("could not refresh the replied message: %s: %s", type(e).__name__, e)
        if not query and media and not tgm.kind_of(media):
            found = re.search(r"https?://\S+", media.text or media.caption or "")
            if found:
                query = found.group(0)

        if query:
            item = await self._from_query(chat_id, query, kind, status, eager)
        elif media and tgm.kind_of(media):
            item = await self._from_telegram(chat_id, media, kind, status)
        else:
            raise UserError("__Send a song name or a link, or reply to an audio / video file.__")
        item.requested_by = requester
        return item

    # ------------------------------------------------------------------------------------------ queries

    async def _from_query(self, chat_id, query, kind, status, eager) -> MediaItem:
        searched = False
        if not query.startswith("http"):
            await status.update("🔎 `Searching ...`")
            found = await self.yt.search(query)
            if not found:
                raise UserError(f"**Nothing found for** `{clean(query)}`**!**")
            query, searched, kind = found.url, True, kind or AUDIO   # a song name plays as audio unless video is asked
        if is_youtube(query):
            return await self._from_youtube(chat_id, query, kind or VIDEO, searched, status, eager)
        if kind is None:
            await status.update("🔄 `Checking the stream ...`")
        info = await probe.inspect(query)
        kind = kind or (VIDEO if info and info["video"] else AUDIO)
        return MediaItem(kind=kind, key="url_" + _hash(query), source=query, link=query, origin={"url": query, "kind": kind},
                         duration=info["duration"] if info else None, prepared_at=time.monotonic())

    async def _from_youtube(self, chat_id, url, kind, searched, status, eager) -> MediaItem:
        await status.update("🔄 `Preparing the YouTube stream ...`")
        try:
            info = await (self.yt.audio(url) if kind == AUDIO or not eager else self.yt.meta(url))
        except Exception as e:
            raise UserError(f"**YouTube error!**\n\n`{clean(e)[:300]}`")
        item = MediaItem(kind=kind, key=f"yt_{info.id}_{'a' if kind == AUDIO else 'v' + str(self.yt.height)}",
                         title=info.title, artist=info.artist, duration=None if info.live else info.duration,
                         link=None if searched else url, origin={"url": url, "kind": kind, "searched": searched})
        if kind == AUDIO:
            item.source, item.prepared_at = info.url, time.monotonic()
        item.prepare = self._youtube_preparer(chat_id, url)
        if info.thumb:
            thumb = await probe.to_jpg(info.thumb, self.files.path(chat_id, f"yt_{info.id}_thumb", "jpg"))
            item.thumb = self.files.acquire(thumb)
            if item.thumb:
                item.files.append(item.thumb)
        if eager and kind == VIDEO:
            await status.update("🔄 `Preparing the video stream ...`" if self.stream_video else "📥 `Downloading the video ...`")
            await item.prepare(item)
        return item

    def _youtube_preparer(self, chat_id: int, url: str):
        async def download(item: MediaItem) -> None:
            item.source = item.audio_source = None
            await prepare(item, force_download=True)

        async def prepare(item: MediaItem, force_download: bool = False) -> None:
            fresh = item.source and time.monotonic() - item.prepared_at < URL_MAX_AGE
            if item.kind == AUDIO:
                if fresh:
                    return
                info = await self.yt.audio(url)
                item.source, item.prepared_at = info.url, time.monotonic()
                return
            if item.source and (self.files.owns(item.source) or (fresh and not force_download)):
                return
            if self.stream_video and not force_download and not item.fell_back:
                info = await self.yt.video_streams(url)
                item.source, item.audio_source, item.prepared_at = info.url, info.audio_url, time.monotonic()
                if info.live:
                    item.duration = None
                else:
                    item.fallback = download
                return
            dest = self.files.path(chat_id, item.key, "mp4")
            async with self.files.lock(dest):
                if os.path.isfile(dest) and os.path.getsize(dest) > 0:       # same video queued before: re-use
                    item.source = self.files.acquire(dest)
                    item.files.append(item.source)
                    item.prepared_at = time.monotonic()
                    return
                info = await self.yt.video(url, dest[:-4])
            if info.live:
                item.source, item.duration = info.url, None
            else:
                item.source = self.files.acquire(info.path)
                item.files.append(item.source)
                item.duration = info.duration or item.duration
            item.prepared_at = time.monotonic()
        return prepare

    # ------------------------------------------------------------------------------------------- playlists

    async def playlist(self, chat_id: int, url: str, kind: str | None, status, requester, limit: int) -> list[MediaItem]:
        """The first `limit` videos of a YouTube playlist as lazy items (each is resolved when it is about to play)."""
        await status.update("📃 `Reading the playlist ...`")
        entries = await self.yt.playlist(url, limit)
        if not entries:
            raise UserError("**That playlist is empty or private.**")
        kind = kind or AUDIO
        items = []
        for entry in entries:
            item = MediaItem(kind=kind, key=f"yt_{entry.id}_{'a' if kind == AUDIO else 'v' + str(self.yt.height)}",
                             title=entry.title, duration=entry.duration, link=entry.url, requested_by=requester,
                             origin={"url": entry.url, "kind": kind})
            item.prepare = self._youtube_preparer(chat_id, entry.url)
            items.append(item)
        return items

    # --------------------------------------------------------------------------------------------- restore

    async def restore(self, chat_id: int, origin: dict, eager: bool) -> MediaItem:
        """The same media again after a restart (downloads/ is wiped at start, files are fetched again)."""
        status = NullStatus()
        kind = origin.get("kind")
        if "url" in origin:
            if is_youtube(origin["url"]):
                return await self._from_youtube(chat_id, origin["url"], kind or VIDEO, bool(origin.get("searched")), status, eager)
            return await self._from_query(chat_id, origin["url"], kind, status, eager)
        media = await self.client.get_messages(origin["chat"], origin["msg"])
        if not media or not tgm.kind_of(media):
            raise UserError("the file is not there any more")
        return await self._from_telegram(chat_id, media, kind, status)

    # --------------------------------------------------------------------------------------- telegram files

    async def _from_telegram(self, chat_id, media, kind, status) -> MediaItem:
        file = tgm.file_of(media)
        if (file.file_size or 0) > self.max_bytes:
            raise UserError(f"**The file is larger than {self.max_bytes // 1048576} MB!**")
        key = "tg_" + (getattr(file, "file_unique_id", None) or _hash(str(file.file_id)))
        dest = self.files.path(chat_id, key, tgm.extension_of(media))
        async with self.files.lock(dest):
            source = await tgm.download(self.client, media, dest, status)
        item = MediaItem(kind=VIDEO, key=key, origin={"chat": media.chat.id, "msg": media.id})
        item.source = self.files.acquire(source)
        item.files.append(item.source)
        item.title, item.artist = tgm.title_of(media)
        try:
            info = await probe.inspect(source)
            mk = tgm.kind_of(media)
            if mk == "unknown":
                if not info or not (info["video"] or info["audio"]):
                    raise UserError("**That file has no playable audio or video!**")
                mk = VIDEO if info["video"] else AUDIO
            item.kind = kind or mk
            item.origin["kind"] = item.kind
            item.duration = info["duration"] if info else None
            thumb_dest = self.files.path(chat_id, f"{key}_thumb", "jpg")
            thumbs = getattr(file, "thumbs", None)
            thumb = await tgm.thumbnail(self.client, thumbs[0].file_id, thumb_dest) if thumbs else None
            if not thumb and item.kind == AUDIO:
                thumb = await probe.to_jpg(source, thumb_dest)    # cover art embedded in the audio file
            if thumb:
                item.thumb = self.files.acquire(thumb)
                item.files.append(item.thumb)
        except Exception:
            for path in item.files:
                self.files.release(path)
            raise
        item.prepared_at = time.monotonic()
        return item
