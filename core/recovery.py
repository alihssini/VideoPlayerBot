"""Lost voice calls: PyTgCalls forgets a dead call silently, so the bot would believe it still plays.
Notices it (call-left events, connection changes, a watchdog over all active chats) and continues the same
media where it stopped, or gives up after too many drops."""

import time
import asyncio
import logging
from core.errors import NoVoiceChat
from core.player import Player, DISCONNECTED, fmt_time
from core.state import StateStore

log = logging.getLogger("vpb.recovery")
REJOIN_LIMIT, REJOIN_WINDOW = 2, 300      # a call that dies more often than this (per seconds) is given up on
WATCH_EVERY = 5


class Recovery:
    def __init__(self, player: Player, voice, store: StateStore):
        self.player, self.voice, self.store = player, voice, store
        self._misses: dict[int, int] = {}
        voice.on_call_left(self._left)
        voice.on_connection(self._connection)

    async def _left(self, chat_id: int, reason: str) -> None:
        log.info("call update in %s: %s", chat_id, reason)
        state = self.store.peek(chat_id)
        if state and state.active:
            self.player.spawn(self.handle(chat_id, reason, resume=False, noticed=time.monotonic()))

    async def _connection(self, chat_id: int, name: str) -> None:
        log.info("voice connection in %s: %s", chat_id, name)
        state = self.store.peek(chat_id)
        if name not in ("CONNECTING", "CONNECTED") and state and state.active:
            self.player.spawn(self.handle(chat_id, f"connection {name.lower()}", noticed=time.monotonic()))

    async def watchdog(self) -> None:
        """One task for all chats."""
        while True:
            await asyncio.sleep(WATCH_EVERY)
            for state in self.store.active():
                alive = await self.voice.in_call(state.chat_id)
                if alive is not False:
                    self._misses.pop(state.chat_id, None)
                    continue
                misses = self._misses.get(state.chat_id, 0) + 1
                self._misses[state.chat_id] = misses
                if misses >= 2:          # a single miss can be a stream switching over
                    self._misses[state.chat_id] = -3   # leave the recovery some time before looking again
                    self.player.spawn(self.handle(state.chat_id, "the voice engine no longer has the call",
                                                  verify=True, noticed=time.monotonic()))

    async def handle(self, chat_id: int, reason: str, resume: bool = True, verify: bool = False, noticed: float | None = None) -> None:
        noticed = time.monotonic() if noticed is None else noticed
        state = self.store.peek(chat_id)
        if not state:
            return
        async with state.lock:
            if not state.active or state.started_at > noticed:
                return  # stopped meanwhile or a newer stream already runs
            if verify and await self.voice.in_call(chat_id):
                return  # false alarm
            pb = state.playback
            at = int(pb.position())
            log.warning("lost the voice call in %s (%s) at %s", chat_id, reason, fmt_time(at))
            now = time.monotonic()
            state.drops = [t for t in state.drops if now - t < REJOIN_WINDOW]
            fatal = not resume
            if resume and len(state.drops) < REJOIN_LIMIT:
                state.drops.append(now)
                try:
                    await self.voice.leave(chat_id)   # drop the dead connection, else play() only swaps its source
                    await self.player.restart_locked(state, 0 if pb.item.live else at)
                    log.info("rejoined the voice chat of %s, went on from %s", chat_id, fmt_time(at))
                    return
                except NoVoiceChat:
                    fatal = True
                    log.warning("no voice chat is running in %s any more", chat_id)
                except Exception as e:
                    log.warning("could not rejoin the voice chat of %s: %s: %s", chat_id, type(e).__name__, e)
            elif resume:
                log.warning("the call of %s keeps dying, not rejoining again", chat_id)
            if fatal:
                await self.player.reset_locked(state, DISCONNECTED)
            else:
                await self.player.advance_locked(state, DISCONNECTED)
