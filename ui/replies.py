"""Safe message helpers and the one error wrapper every command uses."""

import logging
import functools
from pyrogram.types import LinkPreviewOptions
from core.errors import UserError, Silent

log = logging.getLogger("vpb.commands")
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
GONE = ("MESSAGE_ID_INVALID", "MessageIdInvalid", "MESSAGE_DELETE_FORBIDDEN", "CHAT_WRITE_FORBIDDEN")


def clean(text) -> str:
    """Remove the markdown characters, so names and titles cannot break a message."""
    return "".join(" " if c in "`*_[]~|" else c for c in str(text)).strip()


def is_gone(error: Exception) -> bool:
    return any(g in f"{type(error).__name__} {error}" for g in GONE)


async def say(m, text: str, **kwargs):
    """Reply to m; returns the message or None (never raises)."""
    kwargs.setdefault("link_preview_options", NO_PREVIEW)
    try:
        return await m.reply_text(text, **kwargs)
    except Exception as e:
        log.warning("reply failed in %s: %s: %s", getattr(m.chat, "id", "?"), type(e).__name__, e)
        return None


async def edit(msg, text: str, **kwargs) -> bool:
    """Edit a status message; False when it is gone (deleted by someone else). Never raises."""
    if msg is None:
        return False
    kwargs.setdefault("link_preview_options", NO_PREVIEW)
    try:
        await msg.edit_text(text, **kwargs)
        return True
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" in str(e):
            return True
        if not is_gone(e):
            log.warning("edit failed: %s: %s", type(e).__name__, e)
        return False


class Status:
    """A 'Processing ...' message that keeps working when someone deletes it (then a new one is sent once)."""

    def __init__(self, m, text: str = "🔄 `Processing ...`"):
        self.m, self.first, self.msg = m, text, None

    async def __aenter__(self):
        self.msg = await say(self.m, self.first)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """An error inside the block is shown IN the status message (no second message)."""
        if exc is None or isinstance(exc, Silent):
            return isinstance(exc, Silent)
        if isinstance(exc, UserError):
            await self.done(f"❌ {exc}")
        else:
            log.error("command failed", exc_info=(exc_type, exc, tb))
            await self.done(f"❌ **Something went wrong.**\n\n`{type(exc).__name__}: {clean(exc)[:300]}`")
        return True

    async def update(self, text: str) -> None:
        if not await edit(self.msg, text):
            self.msg = None

    async def done(self, text: str | None = None) -> None:
        """Replace the status with a final text, or delete it when text is None."""
        if text is None:
            if self.msg:
                try:
                    await self.msg.delete()
                except Exception:
                    pass
            return
        if not await edit(self.msg, text):
            await say(self.m, text)


def command(func):
    """Every handler: UserError -> '❌ text', Silent -> nothing, anything else -> logged + short error."""
    @functools.wraps(func)
    async def wrapper(client, m):
        try:
            return await func(client, m)
        except Silent:
            return None
        except UserError as e:
            await say(m, f"❌ {e}")
        except Exception as e:
            log.exception("command %s failed", func.__name__)
            await say(m, f"❌ **Something went wrong.**\n\n`{type(e).__name__}: {clean(e)[:300]}`")
    return wrapper
