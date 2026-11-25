"""Inline buttons under the now-playing card (only on cards the real bot account sent)."""

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from core.models import ChatState

PREFIX = "vpb"
SEEKS = (-60, -30, 30, 60)


def keyboard(state: ChatState) -> InlineKeyboardMarkup | None:
    pb = state.playback
    if not pb:
        return None
    c = state.chat_id
    b = lambda text, action: InlineKeyboardButton(text, callback_data=f"{PREFIX}:{action}:{c}")  # noqa: E731
    rows = [[b("▶️" if pb.paused else "⏸", "pp"), b("⏭", "n"), b("⏹", "s")]]
    if not pb.item.live:
        rows[0].append(b("🔁 on" if state.loop else "🔁", "l"))
        rows.append([b(f"{'⏪' if s < 0 else '⏩'} {abs(s)}", f"j{s:+d}") for s in SEEKS])
    rows.append([b("🔉 −20", "vd"), b("🔊 +20", "vu"), b("📋", "q")]
                + ([] if pb.item.live else [b("⬇️", "dl")]))
    return InlineKeyboardMarkup(rows)
