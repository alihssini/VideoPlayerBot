"""The only module that talks to PyTgCalls. The player depends on this small interface, not on the library."""

import asyncio
import logging
from typing import Awaitable, Callable
from pytgcalls import PyTgCalls, filters as call_filters
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import AudioQuality, ChatUpdate, GroupCallConfig, MediaStream, StreamEnded, VideoQuality
from core.errors import NoVoiceChat
from core.models import VIDEO

log = logging.getLogger("vpb.voice")
LEFT = ("KICKED", "LEFT_GROUP", "CLOSED_VOICE_CHAT", "DISCARDED_CALL", "BUSY_CALL")


class VoiceService:
    def __init__(self, client, video_quality: str):
        self.calls = PyTgCalls(client)
        self.quality = getattr(VideoQuality, video_quality)

    async def start(self) -> None:
        await self.calls.start()           # also starts the Telegram client

    def _stream(self, source: str, kind: str, start: int, volume: int) -> MediaStream:
        """start > 0 begins that many seconds in; volume (1-200) is applied by ffmpeg, because Telegram's
        participant volume has no effect on what the account itself sends."""
        params = []
        if start:
            params.append(f"-ss {int(start)}")
        if volume != 100:
            params.append(f"--audio ---mid -af volume={volume / 100:.2f}")
        extra = {"ffmpeg_parameters": " ".join(params)} if params else {}
        if kind == VIDEO:
            return MediaStream(source, audio_parameters=AudioQuality.HIGH, video_parameters=self.quality, **extra)
        return MediaStream(source, audio_parameters=AudioQuality.HIGH, video_flags=MediaStream.Flags.IGNORE, **extra)

    async def play(self, chat_id: int, source: str, kind: str, start: int = 0, volume: int = 100, timeout: int = 90) -> None:
        """Join the voice chat (or switch what is sent into it)."""
        try:
            await asyncio.wait_for(
                self.calls.play(chat_id, self._stream(source, kind, start, volume), config=GroupCallConfig(auto_start=False)),
                timeout,
            )
        except NoActiveGroupCall:
            raise NoVoiceChat()
        except asyncio.TimeoutError:
            raise TimeoutError(f"the voice chat did not answer within {timeout}s")

    async def pause(self, chat_id: int) -> bool:
        try:
            await self.calls.pause(chat_id)
            return True
        except NotInCallError:
            return False

    async def resume(self, chat_id: int) -> bool:
        try:
            await self.calls.resume(chat_id)
            return True
        except NotInCallError:
            return False

    async def leave(self, chat_id: int) -> None:
        try:
            await self.calls.leave_call(chat_id)
        except Exception as e:
            if not isinstance(e, NotInCallError):
                log.warning("could not leave the call of %s: %s: %s", chat_id, type(e).__name__, e)

    async def in_call(self, chat_id: int) -> bool | None:
        """True / False, or None when the engine cannot tell."""
        try:
            return chat_id in await self.calls.calls
        except Exception:
            return None

    # ---- events -----------------------------------------------------------------------------------------------

    def on_stream_end(self, callback: Callable[[int, set], Awaitable[None]]) -> None:
        """callback(chat_id, {"audio", "video"}) when the media of a call ran out."""
        @self.calls.on_update(call_filters.stream_end())
        async def _ended(_, update: StreamEnded):
            kinds = {k for k, t in (("audio", StreamEnded.Type.AUDIO), ("video", StreamEnded.Type.VIDEO)) if update.stream_type & t}
            await callback(update.chat_id, kinds)

    def on_call_left(self, callback: Callable[[int, str], Awaitable[None]]) -> None:
        """callback(chat_id, reason): kicked, voice chat closed, ... (cannot be rejoined)."""
        @self.calls.on_update(call_filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def _left(_, update: ChatUpdate):
            why = "|".join(n.lower() for n in LEFT if update.status & getattr(ChatUpdate.Status, n)) or "call ended"
            await callback(update.chat_id, why)

    def on_connection(self, callback: Callable[[int, str], Awaitable[None]]) -> None:
        """callback(chat_id, state) for connection changes; PyTgCalls drops failed calls silently otherwise."""
        original = getattr(self.calls, "_handle_connection_changed", None)
        if original is None:
            log.warning("this PyTgCalls has no connection hook, only the watchdog notices lost calls")
            return

        async def hooked(chat_id, net_state):
            name = getattr(getattr(net_state, "state", None), "name", None) or str(net_state)
            try:
                await callback(chat_id, name)
            except Exception:
                log.exception("connection callback failed")
            return await original(chat_id, net_state)

        self.calls._handle_connection_changed = hooked
