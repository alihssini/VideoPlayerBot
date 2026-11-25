"""Playback logic of all chats: start, queue, pause / resume, seek, volume, loop, skip, stop, end of media.

Every method that changes a chat holds that chat's lock, so commands, stream ends and the recovery never
run at the same time for one chat. One code path (_restart) moves the running media to a new position /
volume / source; seek, volume, loop, lyrics and the recovery all use it.
"""

import time
import random
import asyncio
import logging
from core.errors import UserError
from core.events import PlayerEvents
from core.files import FileStore
from core.models import ChatState, MediaItem, Playback, Requester
from core.state import StateStore

log = logging.getLogger("vpb.player")

PLAYING, PAUSED = "▶️ Playing", "⏸ Paused"
FINISHED, STOPPED, SKIPPED, REPLACED, DISCONNECTED = "✅ Finished", "⏹ Stopped", "⏭ Skipped", "⏹ Replaced", "⚠️ Disconnected"
NOTHING = "**Nothing is streaming!**"


class Player:
    def __init__(self, voice, store: StateStore, files: FileStore, events: PlayerEvents, max_queue: int):
        self.voice, self.store, self.files, self.events, self.max_queue = voice, store, files, events, max_queue
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------------------------------- helpers

    def spawn(self, coro) -> None:
        async def guarded():
            try:
                await coro
            except Exception:
                log.exception("background task failed")
        task = asyncio.create_task(guarded())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def discard(self, item: MediaItem) -> None:
        """The item will never play (again): give its files back."""
        for path in item.files:
            self.files.release(path)
        item.files.clear()

    async def prepare(self, item: MediaItem) -> None:
        if item.prepare:
            async with item.prep_lock:
                await item.prepare(item)

    def _prefetch(self, state: ChatState) -> None:
        if state.queue and state.queue[0].prepare:
            self.spawn(self.prepare(state.queue[0]))

    async def is_playing(self, chat_id: int) -> bool:
        """True while the chat really has a running stream (cleans up when the call was closed from outside)."""
        state = self.store.peek(chat_id)
        if not state or not state.active:
            return False
        if await self.voice.in_call(chat_id) is False:
            async with state.lock:
                if state.active:
                    await self.reset_locked(state, STOPPED)
            return False
        return True

    async def _playing_state(self, chat_id: int) -> ChatState:
        if not await self.is_playing(chat_id):
            raise UserError(NOTHING)
        return self.store.get(chat_id)

    # ------------------------------------------------------------------------- locked building blocks

    async def start_locked(self, state: ChatState, item: MediaItem, replaced: str | None = REPLACED,
                           by: Requester | None = None) -> None:
        await self.prepare(item)
        await self.voice.play(state.chat_id, item.source, item.kind, 0, state.volume)
        old, state.playback = state.playback, Playback(item)
        state.loop, state.started_at = False, time.monotonic()
        if old:
            self.discard(old.item)
        log.info("%s stream started in %s: %s", item.kind, state.chat_id, item.name)
        await self.events.started(state, item, replaced if old else None, by)
        self._prefetch(state)

    async def restart_locked(self, state: ChatState, position: float, *, volume: int | None = None,
                             source: str | None = None, kind: str | None = None) -> None:
        """Same media again from `position`, keeping pause state."""
        pb = state.playback
        paused = pb.paused
        await self.voice.play(state.chat_id, source or pb.item.source, kind or pb.item.kind, int(position),
                              volume if volume is not None else state.volume, timeout=60)
        if paused:
            await self.voice.pause(state.chat_id)
        state.started_at = time.monotonic()      # the old stream's end event must not skip to the next item
        pb.moved_to(int(position), paused)

    async def advance_locked(self, state: ChatState, label: str, by: Requester | None = None) -> MediaItem | None:
        """Next queued item (items that fail are skipped); None = queue empty, the call was left."""
        while state.queue:
            item = state.queue.pop(0)
            try:
                await self.start_locked(state, item, label, by)
                return item
            except Exception as e:
                log.warning("could not play the queued item in %s: %s: %s", state.chat_id, type(e).__name__, e)
                self.discard(item)
                await self.events.failed(state, item, e)
        await self.finish_locked(state, label, by)
        return None

    async def finish_locked(self, state: ChatState, label: str, by: Requester | None = None) -> None:
        pb, state.playback, state.loop = state.playback, None, False
        await self.voice.leave(state.chat_id)
        if pb:
            self.discard(pb.item)
        await self.events.finished(state, label, by)

    async def reset_locked(self, state: ChatState, label: str) -> int:
        """Drop the queue and stop; returns how many queued items were dropped."""
        dropped = len(state.queue)
        for item in state.queue:
            self.discard(item)
        state.queue.clear()
        await self.finish_locked(state, label)
        return dropped

    # ------------------------------------------------------------------------------------------ commands

    async def enqueue(self, chat_id: int, title: str, item: MediaItem) -> int:
        """Play now (returns 0) or add to the queue (returns the position). Raises UserError when full."""
        state = self.store.get(chat_id)
        state.title = title or state.title
        playing = await self.is_playing(chat_id)
        async with state.lock:
            if playing and state.active:
                if len(state.queue) >= self.max_queue:
                    raise UserError(f"**The queue is full** ({self.max_queue} items)!")
                state.queue.append(item)
                if len(state.queue) == 1:
                    self._prefetch(state)
                return len(state.queue)
            await self.start_locked(state, item)
            return 0

    def queue_full(self, chat_id: int) -> bool:
        state = self.store.peek(chat_id)
        return bool(state and state.active and len(state.queue) >= self.max_queue)

    async def pause(self, chat_id: int, by: Requester | None) -> None:
        state = await self._playing_state(chat_id)
        async with state.lock:
            pb = state.playback
            if not pb:
                raise UserError(NOTHING)
            if pb.paused:
                raise UserError("**It is paused already.**")
            if not await self.voice.pause(chat_id):
                await self.reset_locked(state, STOPPED)
                raise UserError(NOTHING)
            pb.pause()
            await self.events.changed(state, PAUSED, by)

    async def resume(self, chat_id: int, by: Requester | None) -> None:
        state = await self._playing_state(chat_id)
        async with state.lock:
            pb = state.playback
            if not pb:
                raise UserError(NOTHING)
            if not pb.paused:
                raise UserError("**It is playing already.**")
            if not await self.voice.resume(chat_id):
                await self.reset_locked(state, STOPPED)
                raise UserError(NOTHING)
            pb.resume()
            await self.events.changed(state, PLAYING, by)

    async def skip(self, chat_id: int, by: Requester | None) -> MediaItem:
        state = await self._playing_state(chat_id)
        async with state.lock:
            if not state.active:
                raise UserError(NOTHING)
            if not state.queue:
                raise UserError("**The queue is empty**, there is nothing to skip to!")
            item = await self.advance_locked(state, SKIPPED, by)
        if item is None:
            raise UserError("**None of the queued items could be played**, the stream was stopped.")
        return item

    async def stop(self, chat_id: int, by: Requester | None) -> tuple[str | None, int]:
        """(kind that played, dropped queue items)."""
        state = self.store.get(chat_id)
        async with state.lock:
            if not state.active:
                await self.voice.leave(chat_id)
                raise UserError("**Please start a stream first!**")
            kind = state.playback.item.kind
            dropped = len(state.queue)
            for item in state.queue:
                self.discard(item)
            state.queue.clear()
            await self.finish_locked(state, STOPPED, by)
            return kind, dropped

    async def seek(self, chat_id: int, *, delta: float | None = None, to: float | None = None) -> tuple[float, float]:
        """Move in the media; returns (new position, length)."""
        state = await self._playing_state(chat_id)
        async with state.lock:
            pb = state.playback
            if not pb:
                raise UserError(NOTHING)
            if pb.item.live:
                raise UserError("**This is a live stream, it cannot be moved.**")
            target = max(0.0, (pb.position() + delta) if to is None else to)
            if target >= pb.item.duration - 1:
                raise UserError(f"**That is past the end** ({_fmt(pb.item.duration)}).")
            await self.restart_locked(state, target)
            await self.events.changed(state, PAUSED if pb.paused else PLAYING)
            return float(int(target)), pb.item.duration

    async def set_volume(self, chat_id: int, level: int, by: Requester | None) -> bool:
        """True = applied now, False = saved for the next stream."""
        state = self.store.get(chat_id)
        if not await self.is_playing(chat_id):
            state.volume = level
            return False
        async with state.lock:
            pb = state.playback
            if pb and level != state.volume:
                await self.restart_locked(state, 0 if pb.item.live else pb.position(), volume=level)
            state.volume = level
            if pb:
                await self.events.changed(state, PAUSED if pb.paused else PLAYING, by)
            return bool(pb)

    async def set_loop(self, chat_id: int, enable: bool | None, by: Requester | None) -> bool:
        state = await self._playing_state(chat_id)
        if state.playback.item.live:
            raise UserError("**A live stream cannot be repeated.**")
        state.loop = (not state.loop) if enable is None else enable
        await self.events.changed(state, PAUSED if state.playback.paused else PLAYING, by)
        return state.loop

    async def switch_source(self, chat_id: int, expected_source: str, new_source: str, kind: str) -> None:
        """Same song, new media from the same position (lyrics video). new_source must be acquired already."""
        state = await self._playing_state(chat_id)
        async with state.lock:
            pb = state.playback
            if not pb or pb.item.source != expected_source:
                self.files.release(new_source)
                raise UserError("**The song changed while the video was made**, nothing was changed.")
            await self.restart_locked(state, pb.position(), source=new_source, kind=kind)
            self.discard(pb.item)
            pb.item.files.append(new_source)
            pb.item.source, pb.item.kind, pb.item.lyrics, pb.item.prepare = new_source, kind, True, None
            await self.events.changed(state, PAUSED if pb.paused else PLAYING)

    # ---- queue management -------------------------------------------------------------------------------

    def _queued(self, chat_id: int) -> ChatState:
        state = self.store.peek(chat_id)
        if not state or not state.queue:
            raise UserError("**The queue is empty.**")
        return state

    @staticmethod
    def _index(state: ChatState, number: int) -> int:
        if not 1 <= number <= len(state.queue):
            raise UserError(f"**There is no item {number}** in the queue (1-{len(state.queue)}).")
        return number - 1

    async def _refresh(self, state: ChatState) -> None:
        self._prefetch(state)
        if state.playback:
            await self.events.changed(state, PAUSED if state.playback.paused else PLAYING)

    async def queue_remove(self, chat_id: int, number: int) -> MediaItem:
        state = self._queued(chat_id)
        async with state.lock:
            item = state.queue.pop(self._index(state, number))
            self.discard(item)
            await self._refresh(state)
            return item

    async def queue_move(self, chat_id: int, src: int, dst: int) -> MediaItem:
        state = self._queued(chat_id)
        async with state.lock:
            item = state.queue.pop(self._index(state, src))
            state.queue.insert(max(0, min(dst - 1, len(state.queue))), item)
            await self._refresh(state)
            return item

    async def queue_shuffle(self, chat_id: int) -> int:
        state = self._queued(chat_id)
        async with state.lock:
            random.shuffle(state.queue)
            await self._refresh(state)
            return len(state.queue)

    async def queue_clear(self, chat_id: int) -> int:
        state = self._queued(chat_id)
        async with state.lock:
            dropped = len(state.queue)
            for item in state.queue:
                self.discard(item)
            state.queue.clear()
            await self._refresh(state)
            return dropped

    async def on_stream_end(self, chat_id: int, kinds: set) -> None:
        state = self.store.peek(chat_id)
        if not state or not state.active or state.playback.item.kind not in kinds:
            return
        pb = state.playback
        if time.monotonic() - state.started_at < 3 and (pb.item.duration or 99) > 5:
            return  # late end event of the stream that was just replaced (a really short media still ends)
        log.info("%s stream ended in %s", pb.item.kind, chat_id)
        async with state.lock:
            if state.playback is not pb:
                return
            if state.loop:
                try:
                    await self.restart_locked(state, 0)
                    await self.events.changed(state, PLAYING)
                    return
                except Exception:
                    log.exception("repeating failed in %s", chat_id)
                    state.loop = False
            await self.advance_locked(state, FINISHED)

    async def shutdown(self, label: str = "⏹ Stopped (restart)") -> None:
        """Leave every voice chat and close the cards (systemctl stop / restart)."""
        for state in self.store.active():
            try:
                async with state.lock:
                    await self.reset_locked(state, label)
            except Exception:
                log.exception("shutdown of %s failed", state.chat_id)


def _fmt(seconds) -> str:
    seconds = max(0, int(seconds or 0))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


fmt_time = _fmt
