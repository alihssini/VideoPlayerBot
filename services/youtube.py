"""yt-dlp: search, stream URLs, downloads. Blocking yt-dlp work runs in a shared, bounded thread pool."""

import os
import re
import sys
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from yt_dlp import YoutubeDL

# yt-dlp needs a JS runtime (deno) for YouTube; it lives in this venv's bin dir
_bin = os.path.dirname(sys.executable)
if _bin not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")

YT_REGEX = re.compile(r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/.+")
POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ytdlp")   # shared by all chats
_BASE = {"quiet": True, "no_warnings": True, "geo_bypass": True, "nocheckcertificate": True, "noplaylist": True, "noprogress": True}


@dataclass
class Found:
    url: str
    title: str | None


@dataclass
class Info:
    id: str
    title: str | None
    artist: str | None
    thumb: str | None
    duration: float | None
    live: bool
    url: str | None = None      # direct stream URL (audio / live)
    path: str | None = None     # downloaded file
    width: int | None = None
    height: int | None = None


def is_youtube(text: str) -> bool:
    return bool(YT_REGEX.match(text))


def _artist(info: dict):
    name = info.get("artist") or info.get("creator") or info.get("uploader") or info.get("channel")
    return name[: -len(" - Topic")] if name and name.endswith(" - Topic") else name


def _info(raw: dict, **extra) -> Info:
    return Info(
        id=raw.get("id") or "", title=raw.get("track") or raw.get("title"), artist=_artist(raw),
        thumb=raw.get("thumbnail"), duration=raw.get("duration"), live=bool(raw.get("is_live")), **extra,
    )


def video_format(height: int) -> str:
    """Best video up to `height` (the stream quality of .env), h264 first because it plays everywhere."""
    return f"bv*[height<={height}][vcodec^=avc1]+ba/bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b"


class YouTube:
    def __init__(self, max_bytes: int, search_max_seconds: int, video_height: int):
        self.max_bytes, self.search_max, self.height = max_bytes, search_max_seconds, video_height

    async def _run(self, func, *args):
        return await asyncio.get_running_loop().run_in_executor(POOL, func, *args)

    # ---- search ----
    def _search(self, query: str) -> Found | None:
        with YoutubeDL({**_BASE, "extract_flat": True, "skip_download": True}) as ydl:
            result = ydl.extract_info(f"ytsearch8:{query}", download=False)
        entries = [e for e in (result or {}).get("entries") or [] if e and e.get("id")]
        entries = [e for e in entries if not e.get("is_live") and e.get("live_status") not in ("is_live", "is_upcoming")]
        fitting = [e for e in entries if 0 < (e.get("duration") or 0) <= self.search_max]
        pick = (fitting or entries or [None])[0]
        return Found(f"https://www.youtube.com/watch?v={pick['id']}", pick.get("title")) if pick else None

    async def search(self, query: str) -> Found | None:
        return await self._run(self._search, query)

    # ---- metadata only (cheap, used when queueing) ----
    def _meta(self, url: str) -> Info:
        with YoutubeDL({**_BASE, "skip_download": True}) as ydl:
            return _info(ydl.extract_info(url, download=False, process=False))

    async def meta(self, url: str) -> Info:
        return await self._run(self._meta, url)

    # ---- audio: direct stream URL (expires after a few hours: resolve right before playing) ----
    def _audio(self, url: str) -> Info:
        with YoutubeDL({**_BASE, "format": "bestaudio[protocol^=http]/bestaudio/best"}) as ydl:
            raw = ydl.extract_info(url, download=False)
        return _info(raw, url=raw["url"])

    async def audio(self, url: str) -> Info:
        return await self._run(self._audio, url)

    # ---- video: live = HLS URL, VOD = download + merge (one extract_info, then process the same result) ----
    def _video(self, url: str, dest_noext: str) -> Info:
        opts = {**_BASE, "format": video_format(self.height), "merge_output_format": "mp4",
                "max_filesize": self.max_bytes, "outtmpl": dest_noext + ".%(ext)s"}
        with YoutubeDL(opts) as ydl:
            raw = ydl.extract_info(url, download=False)
            if raw.get("is_live"):
                with YoutubeDL({**_BASE, "format": "best/b"}) as live_ydl:   # one muxed HLS stream
                    live = live_ydl.extract_info(url, download=False)
                return _info(raw, url=live["url"])
            done = ydl.process_ie_result(raw, download=True)
        files = done.get("requested_downloads") or []
        path = files[0].get("filepath") if files else None
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"the video is larger than {self.max_bytes // 1048576} MB")
        os.utime(path, None)
        return _info(done, path=os.path.abspath(path), width=done.get("width"), height=done.get("height"))

    async def video(self, url: str, dest_noext: str) -> Info:
        return await self._run(self._video, url, dest_noext)

    # ---- /download: file to send (mp3 or mp4) ----
    def _download(self, url: str, kind: str, dest_noext: str) -> Info:
        opts = {**_BASE, "max_filesize": self.max_bytes, "outtmpl": dest_noext + ".%(ext)s"}
        if kind == "audio":
            opts.update(format="bestaudio/best", postprocessors=[
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}, {"key": "FFmpegMetadata"}])
        else:
            opts.update(format=video_format(720), merge_output_format="mp4")
        with YoutubeDL(opts) as ydl:
            raw = ydl.extract_info(url, download=False)
            if raw.get("is_live"):
                raise RuntimeError("live streams can't be downloaded")
            size = raw.get("filesize") or raw.get("filesize_approx") or 0
            if size > self.max_bytes:
                raise RuntimeError(f"it is larger than {self.max_bytes // 1048576} MB")
            done = ydl.process_ie_result(raw, download=True)
        files = done.get("requested_downloads") or []
        path = files[0].get("filepath") if files else None
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"nothing was downloaded (larger than {self.max_bytes // 1048576} MB?)")
        return _info(done, path=os.path.abspath(path), width=done.get("width"), height=done.get("height"))

    async def download(self, url: str, kind: str, dest_noext: str) -> Info:
        return await self._run(self._download, url, kind, dest_noext)


def video_id(url: str) -> str | None:
    found = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([\w-]{11})", url)
    return found.group(1) if found else None


def age(item_prepared_at: float) -> float:
    return time.monotonic() - item_prepared_at
