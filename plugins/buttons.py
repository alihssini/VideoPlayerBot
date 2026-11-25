"""Presses on the card buttons (callback queries of the real bot account). Same permission as the command."""

import re
import logging
from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler
from core.acl import Role
from core.errors import UserError
from core.models import Requester
from core.player import fmt_time
from ui.buttons import PREFIX

log = logging.getLogger("vpb.buttons")


def _plain(text: str) -> str:
    return re.sub(r"[*_`]", "", str(text)).strip()[:190]


def register(app) -> None:
    if not app.bot:
        return
    player = app.player

    async def pressed(_, cq):
        try:
            _prefix, action, chat = cq.data.split(":")
            chat_id = int(chat)
        except ValueError:
            return await cq.answer()
        uid = cq.from_user.id if cq.from_user else None
        role = app.acl.role(uid, chat_id)
        if role is None or role < Role.SUDO:
            return await cq.answer("You are not allowed to control this player.", show_alert=True)
        by = Requester.of(cq.from_user)
        state = app.store.peek(chat_id)
        try:
            if action == "pp":
                if state and state.playback and state.playback.paused:
                    await player.resume(chat_id, by)
                    text = "▶️ Resumed"
                else:
                    await player.pause(chat_id, by)
                    text = "⏸ Paused"
            elif action == "n":
                item = await player.skip(chat_id, by)
                text = f"⏭ Now: {item.name}"
            elif action == "s":
                await player.stop(chat_id, by)
                text = "⏹ Stopped"
            elif action == "l":
                text = "🔁 Repeat on" if await player.set_loop(chat_id, None, by) else "➡️ Repeat off"
            elif action in ("vd", "vu"):
                current = state.volume if state else 100
                level = max(1, min(200, current + (20 if action == "vu" else -20)))
                await player.set_volume(chat_id, level, by)
                text = f"🔊 Volume {level}"
            elif action == "vi":
                text = f"🔊 Volume {state.volume if state else 100} (1-200)"
            elif action == "q":
                if not state or not state.playback:
                    raise UserError("Nothing is streaming!")
                lines = [f"▶️ {state.playback.item.name} · {fmt_time(state.playback.position())}"]
                lines += [f"{i}. {it.name}" for i, it in enumerate(state.queue[:8], 1)]
                if len(state.queue) > 8:
                    lines.append(f"… +{len(state.queue) - 8} more")
                return await cq.answer("\n".join(lines)[:190] if len(lines) > 1 else lines[0][:190] + "\n(queue empty)", show_alert=True)
            else:
                return await cq.answer()
            await cq.answer(text[:190])
        except UserError as e:
            await cq.answer(_plain(e), show_alert=True)
        except Exception as e:
            log.exception("button %s failed", action)
            await cq.answer(f"Error: {type(e).__name__}", show_alert=True)

    app.bot.add_handler(CallbackQueryHandler(pressed, filters.regex(rf"^{PREFIX}:")))
