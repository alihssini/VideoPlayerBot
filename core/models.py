"""Plain data of the player. No Telegram or voice-engine code in here."""

from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

AUDIO, VIDEO = "audio", "video"


@dataclass(frozen=True)
class Requester:
    id: int
    name: str

    @classmethod
    def of(cls, user) -> "Requester | None":
        if user is None:
            return None
        name = " ".join(x for x in (user.first_name, user.last_name) if x) or (user.username or str(user.id))
        return cls(user.id, name)


@dataclass
class MediaItem:
    kind: str                                  # AUDIO | VIDEO
    key: str = ""                              # stable id of the media (file names, card cache)
    source: str | None = None                  # local file or URL for the voice engine; None until prepared
    title: str | None = None
    artist: str | None = None
    link: str | None = None                    # shown as a link on the card
    thumb: str | None = None                   # local jpg (artwork)
    duration: float | None = None              # None = live / unknown
    requested_by: Requester | None = None
    reply_chat: int | None = None              # private chat it was requested from (gets its own card)
    lyrics: bool = False
    origin: dict | None = None                 # how to get it again after a restart: {"url"} or {"chat", "msg"}
    files: list[str] = field(default_factory=list)   # files held by this item (reference counted)
    prepare: Callable[["MediaItem"], Awaitable[None]] | None = None  # lazy resolve (download / fresh URL)
    prepared_at: float = 0.0
    prep_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    @property
    def name(self) -> str:
        if self.artist and self.title and self.artist.lower() not in self.title.lower():
            return f"{self.artist} - {self.title}"
        return self.title or self.link or "Untitled stream"

    @property
    def live(self) -> bool:
        return not self.duration


@dataclass
class Playback:
    """What plays right now and where it is."""
    item: MediaItem
    base: float = 0.0                          # position (s) at `since`
    since: float | None = field(default_factory=time.monotonic)   # None while paused

    @property
    def paused(self) -> bool:
        return self.since is None

    def position(self) -> float:
        pos = self.base + (time.monotonic() - self.since if self.since is not None else 0.0)
        return min(pos, self.item.duration) if self.item.duration else pos

    def pause(self) -> None:
        if self.since is not None:
            self.base, self.since = self.position(), None

    def resume(self) -> None:
        if self.since is None:
            self.since = time.monotonic()

    def moved_to(self, seconds: float, paused: bool) -> None:
        self.base, self.since = float(seconds), (None if paused else time.monotonic())


@dataclass
class ChatState:
    chat_id: int
    title: str = "this chat"
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    queue: list[MediaItem] = field(default_factory=list)
    playback: Playback | None = None
    loop: bool = False
    volume: int = 100
    started_at: float = 0.0                    # monotonic time of the last (re)start of the stream
    drops: list[float] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.playback is not None
