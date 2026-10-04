"""Media helpers: detect audio/video with ffprobe, make JPEG thumbnails, fetch the account's profile picture."""

import os
import json
import asyncio
import hashlib

_profile_path = None


async def _run(*cmd, timeout):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out


async def probe(source, timeout=25):
    """Return {"video": bool, "audio": bool} for a file or URL, or None if it can't be read.
    Cover art embedded in audio files does not count as video."""
    try:
        rc, out = await _run(
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type:stream_disposition=attached_pic",
            "-of", "json", str(source),
            timeout=timeout,
        )
        if rc != 0:
            return None
        streams = json.loads(out or b"{}").get("streams", [])
    except Exception as e:
        print(f"[WARN] - probe failed: {type(e).__name__}: {e}")
        return None
    return {
        "video": any(
            s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
            for s in streams
        ),
        "audio": any(s.get("codec_type") == "audio" for s in streams),
    }


async def to_jpg(source, timeout=25, width=640):
    """First picture of a file or URL (embedded cover art, a video frame, a .webp/.png thumbnail)
    as a JPEG in ./downloads. Returns the path or None."""
    os.makedirs("downloads", exist_ok=True)
    name = "thumb_" + hashlib.md5(f"{source}|{width}".encode()).hexdigest()[:12] + ".jpg"
    dest = os.path.abspath(os.path.join("downloads", name))
    try:
        rc, _ = await _run(
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-an", "-frames:v", "1", "-vf", f"scale={width}:{width}:force_original_aspect_ratio=decrease", dest,
            timeout=timeout,
        )
    except Exception as e:
        print(f"[WARN] - thumbnail skipped: {type(e).__name__}: {e}")
        return None
    return dest if rc == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 0 else None


async def profile_photo(client):
    """The logged-in account's profile picture (cached in ./assets/profile.jpg), or None."""
    global _profile_path
    if _profile_path and os.path.isfile(_profile_path):
        return _profile_path
    try:
        me = await client.get_me()
        if not me.photo:
            return None
        dest = os.path.abspath(os.path.join("assets", "profile.jpg"))
        path = await asyncio.wait_for(client.download_media(me.photo.big_file_id, file_name=dest), 30)
        _profile_path = path
        return path
    except Exception as e:
        print(f"[WARN] - profile picture unavailable: {type(e).__name__}: {e}")
        return None
