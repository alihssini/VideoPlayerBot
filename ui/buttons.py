"""Inline buttons under the now-playing card (only on cards the real bot account sent)."""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from core.models import ChatState

PREFIX = "vpb"


def keyboard(state: ChatState) -> InlineKeyboardMarkup | None:
    pb = state.playback
    if not pb:
        return None
    c = state.chat_id
    b = lambda text, action: InlineKeyboardButton(text, callback_data=f"{PREFIX}:{action}:{c}")  # noqa: E731
    rows = [
        [b("▶️" if pb.paused else "⏸", "pp"), b("⏭", "n"), b("⏹", "s"), b("🔁 on" if state.loop else "🔁", "l")],
        [b("🔉 −20", "vd"), b(f"🔊 {state.volume}", "vi"), b("🔊 +20", "vu"), b("📋", "q")],
    ]
    if pb.item.live:
        rows[0] = [r for r in rows[0] if not r.callback_data.startswith(f"{PREFIX}:l:")]
    return InlineKeyboardMarkup(rows)
