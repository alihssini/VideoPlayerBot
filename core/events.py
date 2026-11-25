"""What the player tells the user interface. The player knows only this interface (Dependency Inversion)."""

from typing import Protocol
from core.models import ChatState, MediaItem, Requester


class PlayerEvents(Protocol):
    async def started(self, state: ChatState, item: MediaItem, replaced: str | None, by: Requester | None = None) -> None:
        """A new media plays; `replaced` = final label for the card of the media before it (None = there was none),
        `by` = who caused the change (skip)."""

    async def changed(self, state: ChatState, label: str, by: Requester | None = None) -> None:
        """Same media, new state (paused, resumed, jumped, volume, loop, lyrics on)."""

    async def finished(self, state: ChatState, label: str, by: Requester | None = None) -> None:
        """Nothing plays any more in this chat."""

    async def failed(self, state: ChatState, item: MediaItem, error: Exception) -> None:
        """A queued media could not be started and was skipped."""
