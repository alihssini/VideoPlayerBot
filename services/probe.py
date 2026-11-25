"""ffprobe / ffmpeg helpers: kind and length of a media, JPEG thumbnails."""

import os
import json
import asyncio
import logging

log = logging.getLogger("vpb.probe")


async def _run(*cmd, timeout: int):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out


async def inspect(source, timeout: int = 25) -> dict | None:
    """{"video": bool, "audio": bool, "duration": float | None} in ONE ffprobe call, or None if unreadable.
    Cover art inside audio files does not count as video."""
    try:
        rc, out = await _run(
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type:stream_disposition=attached_pic:format=duration",
            "-of", "json", str(source), timeout=timeout,
        )
        if rc != 0:
            return None
        data = json.loads(out or b"{}")
    except Exception as e:
        log.warning("probe failed: %s: %s", type(e).__name__, e)
        return None
    streams = data.get("streams", [])
    try:
        duration = float(data.get("format", {}).get("duration") or 0) or None
    except ValueError:
        duration = None
    return {
        "video": any(s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic") for s in streams),
        "audio": any(s.get("codec_type") == "audio" for s in streams),
        "duration": duration,
    }


async def to_jpg(source, dest: str, width: int = 640, timeout: int = 25) -> str | None:
    """First picture of a file or URL (cover art, video frame, webp/png thumbnail) as JPEG at dest.
    Re-uses dest when it exists already (same media key = same picture)."""
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest
    try:
        rc, _ = await _run(
            "ffmpeg", "-y", "-v", "error", "-i", str(source), "-an", "-frames:v", "1",
            "-vf", f"scale={width}:{width}:force_original_aspect_ratio=decrease", dest, timeout=timeout,
        )
    except Exception as e:
        log.warning("thumbnail skipped: %s: %s", type(e).__name__, e)
        return None
    return dest if rc == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0 else None


class ProfilePhoto:
    """The account's profile picture, downloaded once to assets/profile.jpg."""

    def __init__(self, client, path: str):
        self.client, self.path, self._done = client, os.path.abspath(path), False

    async def get(self) -> str | None:
        if self._done:
            return self.path if os.path.isfile(self.path) else None
        self._done = True
        try:
            me = await self.client.get_me()
            if not me.photo:
                return None
            return await asyncio.wait_for(self.client.download_media(me.photo.big_file_id, file_name=self.path), 30)
        except Exception as e:
            log.warning("profile picture unavailable: %s: %s", type(e).__name__, e)
            return None
