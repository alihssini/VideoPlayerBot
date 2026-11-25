"""Start again what played before the restart (from core/session.py)."""

import logging
from core.models import Requester

log = logging.getLogger("vpb.restore")


async def restore(app, chats: list[dict]) -> None:
    for chat in chats:
        chat_id = chat["chat"]
        state = app.store.get(chat_id)
        state.volume, state.title = chat.get("volume", 100), chat.get("title") or state.title
        records = chat.get("items") or []
        started = False
        for number, record in enumerate(records):
            try:
                item = await app.resolver.restore(chat_id, record["origin"], eager=not started)
                by = record.get("requested_by")
                item.requested_by = Requester(by["id"], by["name"]) if by else None
                item.reply_chat = record.get("reply_chat")
                if record["origin"].get("lyrics"):
                    await app.lyrics.apply(item, chat_id, _Null(), app.player.prepare)
                position = await app.player.enqueue(chat_id, state.title, item)
                if position == 0:
                    started = True
                    if number == 0 and chat.get("position", 0) > 5 and not item.live:
                        await app.player.seek(chat_id, to=chat["position"])
                    if number == 0 and chat.get("loop"):
                        state.loop = True
                    if number == 0 and chat.get("paused"):
                        await app.player.pause(chat_id, None)
            except Exception as e:
                log.warning("could not restore an item in %s: %s: %s", chat_id, type(e).__name__, e)
        if records:
            log.info("restored %s in %s (%d items)", "playback" if started else "nothing", chat_id, len(records))


class _Null:
    async def update(self, text: str) -> None:
        pass
