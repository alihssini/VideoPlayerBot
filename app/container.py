"""Builds every object once and hands them to the plugins (simple dependency injection, no import side effects)."""

import time
import asyncio
import logging
from dataclasses import dataclass, field
from app.client import SentMessages, make_client
from app.config import Settings, settings
from core.acl import AclService
from core.files import FileStore
from core.player import Player
from core.recovery import Recovery
from core.state import StateStore
from services import probe
from services.card_renderer import CardRenderer
from services.groups import GroupDirectory
from services.lyrics import LyricsMaker
from services.resolver import MediaResolver
from services.voice import VoiceService
from services.youtube import YouTube
from ui.card import CardPresenter

log = logging.getLogger("vpb.app")


@dataclass
class App:
    settings: Settings
    client: object
    sent: SentMessages
    files: FileStore
    store: StateStore
    voice: VoiceService
    acl: AclService
    cards: CardPresenter
    player: Player
    recovery: Recovery
    youtube: YouTube
    resolver: MediaResolver
    lyrics: LyricsMaker
    groups: GroupDirectory
    me_id: int = 0
    _notified: dict = field(default_factory=dict)

    def notify_owners(self, text: str) -> None:
        """Tell the root owners about a problem (an ACL file with a JSON error), at most once per hour per text."""
        log.warning("%s", text)
        if time.monotonic() - self._notified.get(text, -1e9) < 3600:
            return
        self._notified[text] = time.monotonic()

        async def send():
            for uid in self.acl.root - {self.me_id}:
                try:
                    await self.client.send_message(uid, f"⚠️ **Role file problem**\n\n`{text}`")
                except Exception:
                    pass
        try:
            asyncio.get_running_loop().create_task(send())
        except RuntimeError:
            pass


def build() -> App:
    from plugins import download, groups, info, nopm, playback, roles

    client, sent = make_client()
    files = FileStore(settings.download_dir)
    store = StateStore()
    voice = VoiceService(client, settings.video_quality)
    holder: dict = {}
    acl = AclService(settings.data_dir, settings.root_owners, on_error=lambda text: holder["app"].notify_owners(text))
    cards = CardPresenter(client, files, CardRenderer(), probe.ProfilePhoto(client, "assets/profile.jpg"), settings.progress_every)
    player = Player(voice, store, files, cards, settings.max_queue)
    voice.on_stream_end(player.on_stream_end)
    youtube = YouTube(settings.max_bytes, settings.search_max_seconds, settings.video_height)
    app = App(
        settings=settings, client=client, sent=sent, files=files, store=store, voice=voice, acl=acl, cards=cards,
        player=player, recovery=Recovery(player, voice, store), youtube=youtube,
        resolver=MediaResolver(client, youtube, files, settings.max_bytes), lyrics=LyricsMaker(files, probe.to_jpg),
        groups=GroupDirectory(client, acl),
    )
    holder["app"] = app
    for plugin in (roles, groups, info, playback, download, nopm):
        plugin.register(app)
    return app
