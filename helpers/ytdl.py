"""yt-dlp helpers. Blocking yt-dlp calls run in a thread so the bot's event loop stays responsive."""

import os
import re
import sys
import time
import asyncio
from yt_dlp import YoutubeDL
from config import DOWNLOAD_MAX_MB

# yt-dlp needs a JS runtime (deno) for YouTube; it is installed into this venv's bin dir
_bin = os.path.dirname(sys.executable)
if _bin not in os.environ.get("PATH", "").split(os.pathsep):
    os.environ["PATH"] = _bin + os.pathsep + os.environ.get("PATH", "")

YT_REGEX = re.compile(r"^(https?\:\/\/)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)\/.+")
DOWNLOAD_DIR = "downloads"

VIDEO_FORMAT = "bv*[height<=720][vcodec^=avc1]+ba/bv*[height<=720]+ba/b[height<=720]/bv*+ba/b"  # max 720p, h264 first (plays everywhere)

_BASE = {
    "quiet": True,
    "no_warnings": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "noplaylist": True,
    "noprogress": True,
}


FILES = {}  # chat_id -> local file (inside DOWNLOAD_DIR) used by the running stream
SWEEP_EVERY = 30 * 60   # run the sweeper every 30 minutes
MAX_AGE = 6 * 3600      # unused files older than 6 hours are deleted


def _in_downloads(path) -> bool:
    base = os.path.abspath(DOWNLOAD_DIR)
    try:
        return os.path.commonpath([os.path.abspath(path), base]) == base
    except ValueError:
        return False


PROTECTED = set()  # files of queued items: nothing may delete them until they are played or dropped


def _abs(path):
    return os.path.abspath(path) if path and _in_downloads(path) else None


def protect_file(path) -> None:
    p = _abs(path)
    if p:
        PROTECTED.add(p)


def unprotect_file(path) -> None:
    p = _abs(path)
    if p:
        PROTECTED.discard(p)


def remove_file(path) -> None:
    p = _abs(path)
    if p and p not in PROTECTED:
        try:
            os.remove(p)
        except OSError:
            pass


def drop_file(path) -> None:
    """Delete a file nobody needs, unless a running stream or a queued item still uses it."""
    p = _abs(path)
    if p and p not in set(FILES.values()):
        remove_file(p)


def swap_tracked_file(chat_id, new_path) -> None:
    """Remember the file the stream of this chat plays; delete the one it played before."""
    new_path = os.path.abspath(new_path) if new_path and _in_downloads(new_path) else None
    old = FILES.pop(chat_id, None)
    if old and old != new_path:
        remove_file(old)
    if new_path:
        FILES[chat_id] = new_path


def release_file(chat_id) -> None:
    """The stream of this chat ended: delete its file."""
    remove_file(FILES.pop(chat_id, None))


def wipe_downloads() -> None:
    """Delete everything left over (used at startup, nothing is playing then)."""
    if os.path.isdir(DOWNLOAD_DIR):
        for name in os.listdir(DOWNLOAD_DIR):
            remove_file(os.path.join(DOWNLOAD_DIR, name))


def sweep_downloads() -> None:
    """Delete stale files (old thumbnails, aborted *.part/*.temp downloads) that no stream uses."""
    if not os.path.isdir(DOWNLOAD_DIR):
        return
    in_use = set(FILES.values()) | PROTECTED
    cutoff = time.time() - MAX_AGE
    for name in os.listdir(DOWNLOAD_DIR):
        path = os.path.abspath(os.path.join(DOWNLOAD_DIR, name))
        try:
            if path not in in_use and os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


async def sweeper() -> None:
    while True:
        await asyncio.sleep(SWEEP_EVERY)
        sweep_downloads()


def _audio(query: str) -> dict:
    with YoutubeDL({**_BASE, "format": "bestaudio[protocol^=http]/bestaudio/best"}) as ydl:
        info = ydl.extract_info(query, download=False)
    return {"source": info["url"], "title": info.get("title"), "thumb": info.get("thumbnail")}


def _video(query: str) -> dict:
    # YouTube only serves separate video/audio streams, so VODs are downloaded + merged
    # (max 720p) and live streams are played straight from their HLS URL.
    with YoutubeDL({**_BASE, "format": "bv*+ba/b"}) as ydl:
        info = ydl.extract_info(query, download=False)
    title, thumb = info.get("title"), info.get("thumbnail")

    if info.get("is_live"):
        with YoutubeDL({**_BASE, "format": "best/b"}) as ydl:
            live = ydl.extract_info(query, download=False)
        return {"source": live["url"], "title": title, "thumb": thumb}

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    opts = {
        **_BASE,
        "format": VIDEO_FORMAT,
        "merge_output_format": "mp4",
        "max_filesize": DOWNLOAD_MAX_MB * 1024 * 1024,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    }
    with YoutubeDL(opts) as ydl:
        done = ydl.extract_info(query, download=True)
        if not done.get("requested_downloads"):
            raise RuntimeError(f"Video is larger than {DOWNLOAD_MAX_MB} MB")
        path = done["requested_downloads"][0]["filepath"]
    return {"source": path, "title": title, "thumb": thumb}


SEARCH_MAX_SECONDS = int(os.getenv("SEARCH_MAX_MINUTES") or 15) * 60  # skip long loops / mixes


def _search(query: str):
    with YoutubeDL({**_BASE, "extract_flat": True, "skip_download": True}) as ydl:
        result = ydl.extract_info(f"ytsearch8:{query}", download=False)
    entries = [e for e in (result or {}).get("entries") or [] if e and e.get("id")]
    entries = [e for e in entries if not e.get("is_live") and e.get("live_status") not in ("is_live", "is_upcoming")]
    fitting = [e for e in entries if 0 < (e.get("duration") or 0) <= SEARCH_MAX_SECONDS]
    pick = (fitting or entries or [None])[0]
    if not pick:
        return None
    return {"url": f"https://www.youtube.com/watch?v={pick['id']}", "title": pick.get("title")}


async def search_youtube(query: str):
    """Find the best match for a song name: first non-live result that is not longer than SEARCH_MAX_MINUTES."""
    try:
        return await asyncio.get_running_loop().run_in_executor(None, _search, query)
    except Exception as e:
        print(f"[WARN] - search failed: {type(e).__name__}: {e}")
        return None


def _download(url: str, kind: str) -> dict:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    opts = {
        **_BASE,
        "max_filesize": DOWNLOAD_MAX_MB * 1024 * 1024,
        # "dl_" keeps these apart from the files a running stream uses
        "outtmpl": os.path.join(DOWNLOAD_DIR, "dl_%(id)s.%(ext)s"),
    }
    if kind == "audio":
        opts.update(
            format="bestaudio/best",
            postprocessors=[
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                {"key": "FFmpegMetadata"},
            ],
        )
    else:
        opts.update(format=VIDEO_FORMAT, merge_output_format="mp4")
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("is_live"):
            raise RuntimeError("Live streams can't be downloaded")
        done = ydl.process_ie_result(info, download=True)
    files = done.get("requested_downloads") or []
    path = files[0]["filepath"] if files else None
    if not path or not os.path.isfile(path):
        raise RuntimeError(f"Nothing was downloaded (larger than {DOWNLOAD_MAX_MB} MB?)")
    return {
        "path": os.path.abspath(path),
        "size": os.path.getsize(path),
        "title": done.get("track") or done.get("title") or "Unknown",
        "artist": done.get("artist") or done.get("uploader") or done.get("channel"),
        "duration": done.get("duration"),
        "thumb": done.get("thumbnail"),
        "width": done.get("width"),
        "height": done.get("height"),
    }


async def download_file(url: str, kind: str) -> dict:
    """Download a link to ./downloads/dl_*: kind "audio" -> mp3, "video" -> mp4 (max 720p)."""
    return await asyncio.get_running_loop().run_in_executor(None, _download, url, kind)


async def get_audio_stream(query: str) -> dict:
    return await asyncio.get_running_loop().run_in_executor(None, _audio, query)


async def get_video_stream(query: str) -> dict:
    return await asyncio.get_running_loop().run_in_executor(None, _video, query)
