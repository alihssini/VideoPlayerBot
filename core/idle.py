"""Leave a voice chat when nobody else listened for AUTO_LEAVE_MINUTES (one task for all chats)."""

import time
import asyncio
import logging

log = logging.getLogger("vpb.idle")
CHECK_EVERY = 60
LABEL = "⏹ Stopped (nobody was listening)"


class IdleWatcher:
    def __init__(self, player, voice, store, minutes: int, me_id):
        self.player, self.voice, self.store, self.limit, self.me_id = player, voice, store, minutes * 60, me_id
        self._empty_since: dict[int, float] = {}

    async def run(self) -> None:
        if not self.limit:
            return
        while True:
            await asyncio.sleep(CHECK_EVERY)
            now = time.monotonic()
            active = {s.chat_id: s for s in self.store.active()}
            for chat_id in list(self._empty_since):
                if chat_id not in active:
                    self._empty_since.pop(chat_id)
            for chat_id, state in active.items():
                people = await self.voice.listeners(chat_id, self.me_id())
                if people is None or people > 0:
                    self._empty_since.pop(chat_id, None)
                    continue
                since = self._empty_since.setdefault(chat_id, now)
                if now - since >= self.limit:
                    self._empty_since.pop(chat_id, None)
                    log.info("nobody listens in %s since %d min, leaving", chat_id, self.limit // 60)
                    async with state.lock:
                        if state.active:
                            await self.player.reset_locked(state, LABEL)
