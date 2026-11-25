"""Media inside Telegram messages: what it is, its title, downloading it with live progress and stall detection."""

import os
import time
import asyncio
import logging
import mimetypes

log = logging.getLogger("vpb.tgmedia")
MB = 1024 * 1024


def file_of(media):
    return media.video or media.video_note or media.animation or media.audio or media.voice or media.document


def kind_of(media) -> str | None:
    """"video" / "audio", "unknown" for a generic file, None if the message carries no media."""
    if media.video or media.video_note or media.animation:
        return "video"
    if media.audio or media.voice:
        return "audio"
    if media.document:
        mime = media.document.mime_type or ""
        return "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else "unknown"
    return None


def title_of(media) -> tuple[str | None, str | None]:
    """(title, artist) of an audio / video message."""
    if media.audio and (media.audio.title or media.audio.performer):
        return media.audio.title, media.audio.performer
    name = getattr(file_of(media), "file_name", None)
    return (os.path.splitext(name)[0] if name else None), None


def extension_of(media) -> str:
    file = file_of(media)
    name = getattr(file, "file_name", None) or ""
    ext = os.path.splitext(name)[1].lstrip(".")
    if not ext:
        ext = (mimetypes.guess_extension(getattr(file, "mime_type", None) or "") or "").lstrip(".")
    if not ext:
        ext = "ogg" if media.voice else "mp4" if kind_of(media) == "video" else "bin"
    return ext


async def thumbnail(client, file_id: str, dest: str) -> str | None:
    """Thumbnails are optional: never let them block or break a stream."""
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest
    try:
        return await asyncio.wait_for(client.download_media(file_id, file_name=dest), 30)
    except Exception as e:
        log.warning("thumbnail download skipped: %s: %s", type(e).__name__, e)
        return None


async def download(client, media, dest: str, status, stall_timeout: int = 90) -> str:
    """Download to dest (re-used when complete already), show progress in status, abort when nothing arrives for
    stall_timeout seconds."""
    expected = getattr(file_of(media), "file_size", 0) or 0
    if os.path.isfile(dest) and (not expected or os.path.getsize(dest) == expected):
        return dest
    started = time.monotonic()
    state = {"cur": 0, "total": expected, "last_bytes": started, "last_edit": 0.0}
    await status.update("🔄 `Downloading ...`")

    async def progress(current, total):
        now = time.monotonic()
        state.update(cur=current, total=total, last_bytes=now)
        if now - state["last_edit"] >= 5:
            state["last_edit"] = now
            pct = f"{current * 100 / total:.0f}%" if total else ""
            await status.update(f"🔄 `Downloading ... {pct} ({current / MB:.0f}/{total / MB:.0f} MB)`")

    task = asyncio.ensure_future(client.download_media(media, file_name=dest, progress=progress))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=5)
            if done:
                path = task.result()
                log.info("download finished in %.0fs: %s", time.monotonic() - started, path)
                return path
            if time.monotonic() - state["last_bytes"] > stall_timeout:
                task.cancel()
                raise TimeoutError(f"download stalled at {state['cur'] / MB:.0f}/{state['total'] / MB:.0f} MB (no data for {stall_timeout}s)")
    except asyncio.CancelledError:
        task.cancel()
        raise
