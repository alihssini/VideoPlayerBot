"""Telegram downloads with live progress, stall detection and timeouts, so nothing can hang silently."""

import os
import time
import asyncio

MB = 1024 * 1024


def _download_dir() -> str:
    """Absolute ./downloads/ (with trailing slash). A relative path would be resolved against the
    Telegram client's workdir (./sessions) instead, where the cleanup would never look."""
    path = os.path.abspath("downloads")
    os.makedirs(path, exist_ok=True)
    return path + os.sep


async def with_timeout(coro, seconds: int, what: str):
    try:
        return await asyncio.wait_for(coro, seconds)
    except asyncio.TimeoutError:
        raise TimeoutError(f"{what} timed out after {seconds}s")


async def download_thumbnail(client, file_id):
    """Thumbnails are optional: never let them block or break a stream."""
    try:
        return await asyncio.wait_for(client.download_media(file_id, file_name=_download_dir()), 30)
    except Exception as e:
        print(f"[WARN] - thumbnail download skipped: {type(e).__name__}: {e}")
        return None


async def download_with_progress(client, media, msg, label="Downloading", stall_timeout=90):
    """Download `media`, show progress in `msg`, abort if no bytes arrive for `stall_timeout` seconds."""
    started = time.monotonic()
    state = {"cur": 0, "total": 0, "last_bytes": started, "last_edit": 0.0}
    print(f"[INFO] - download started ({label})")
    await msg.edit_text(f"🔄 `{label} ...`")

    async def progress(current, total):
        now = time.monotonic()
        state["cur"], state["total"], state["last_bytes"] = current, total, now
        if now - state["last_edit"] >= 5:
            state["last_edit"] = now
            pct = f"{current * 100 / total:.0f}%" if total else ""
            try:
                await msg.edit_text(f"🔄 `{label} ... {pct} ({current / MB:.0f}/{total / MB:.0f} MB)`")
            except Exception:
                pass

    task = asyncio.ensure_future(client.download_media(media, file_name=_download_dir(), progress=progress))
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=5)
            if done:
                path = task.result()
                print(f"[INFO] - download finished in {time.monotonic() - started:.0f}s: {path}")
                return path
            if time.monotonic() - state["last_bytes"] > stall_timeout:
                task.cancel()
                raise TimeoutError(
                    f"download stalled at {state['cur'] / MB:.0f}/{state['total'] / MB:.0f} MB "
                    f"(no data for {stall_timeout}s)"
                )
    except asyncio.CancelledError:
        task.cancel()
        raise
