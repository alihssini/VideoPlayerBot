"""Now-playing card: picture (rendered by services/card_renderer) + caption, posted in the group, or only in the
private chat when the media was requested from there. One ticker task keeps the progress bar of all cards up to date."""

import asyncio
import logging
from dataclasses import dataclass, field
from pyrogram.errors import FloodWait
from core.models import ChatState, MediaItem, Requester, VIDEO
from core.player import PLAYING, FINISHED, fmt_time
from services.card_renderer import CardInfo, CardRenderer
from ui.replies import NO_PREVIEW, clean, is_gone

log = logging.getLogger("vpb.card")
BAR_WIDTH = 14
CAPTION_MAX = 1024


@dataclass
class CaptionData:
    label: str
    by: str | None
    kind: str
    lyrics: bool
    live: bool
    name: str
    link: str | None
    pos: float
    dur: float | None
    requester: str | None
    loop: bool
    volume: int
    next_name: str | None
    more: int
    where: str | None        # group title, shown on cards outside the group (private chat)


def progress_line(pos: float, dur: float | None, live: bool) -> str:
    if live or not dur:
        return f"🔴 **LIVE** · `{fmt_time(pos)}`" if live else f"⏱ `{fmt_time(pos)}`"
    at = min(BAR_WIDTH - 1, int(min(pos, dur) / dur * (BAR_WIDTH - 1)))
    return f"`{fmt_time(pos)} {'━' * at}●{'─' * (BAR_WIDTH - 1 - at)} {fmt_time(dur)}`"


def build_caption(d: CaptionData) -> str:
    """Pure function: the card text (Telegram markdown, ≤ 1024 characters)."""
    kind = "🎤 Lyrics" if d.lyrics else "🎬 Video" if d.kind == VIDEO else "🎵 Audio"
    head = f"{d.label}" + (f" by **{clean(d.by)}**" if d.by else "") + f" · {kind}" + (f" · {clean(d.where)}" if d.where else "")
    name = clean(d.name)
    lines = [head, f"[{name}]({d.link})" if d.link else f"**{name}**"]
    pos = d.dur if d.label.startswith(FINISHED) and d.dur else d.pos
    lines.append(progress_line(pos, d.dur, d.live))
    extras = []
    if d.requester:
        extras.append(f"👤 Requested by **{clean(d.requester)}**")
    if d.loop:
        extras.append("🔁 Loop")
    if d.volume != 100:
        extras.append(f"🔊 {d.volume}")
    if extras:
        lines.append(" · ".join(extras))
    if d.next_name:
        lines.append(f"⏭ Next: {clean(d.next_name)[:80]}" + (f" (+{d.more} more)" if d.more else ""))
    text = "\n".join(lines)
    return text if len(text) <= CAPTION_MAX else text[: CAPTION_MAX - 1] + "…"


@dataclass
class Card:
    item: MediaItem
    label: str = PLAYING
    by: str | None = None
    posts: list = field(default_factory=list)       # [(message, has_photo, where)]


class CardPresenter:
    """Implements core.events.PlayerEvents."""

    def __init__(self, client, files, renderer: CardRenderer, profile, progress_every: int):
        self.client, self.files, self.renderer, self.profile, self.every = client, files, renderer, profile, progress_every
        self.cards: dict[int, Card] = {}
        self.bot_name = ""

    # ---- PlayerEvents ----
    async def started(self, state: ChatState, item: MediaItem, replaced: str | None, by: Requester | None = None) -> None:
        old = self.cards.pop(state.chat_id, None)
        if old:
            await self._close(state, old, replaced or "⏹ Replaced", by)
        card = Card(item)
        self.cards[state.chat_id] = card
        photo = await self._picture(state, item)
        # started from a private chat: the card goes ONLY there (with the group name); else into the group
        targets = [(item.reply_chat, state.title)] if item.reply_chat and item.reply_chat != state.chat_id else [(state.chat_id, None)]
        for chat, where in targets:
            text = build_caption(self._data(state, card, where))
            card.posts.append(await self._send(chat, text, photo, where))

    async def changed(self, state: ChatState, label: str, by: Requester | None = None) -> None:
        card = self.cards.get(state.chat_id)
        if card:
            card.label, card.by = label, by.name if by else None
            await self._edit(state, card)

    async def finished(self, state: ChatState, label: str, by: Requester | None = None) -> None:
        card = self.cards.pop(state.chat_id, None)
        if card:
            await self._close(state, card, label, by)

    async def failed(self, state: ChatState, item: MediaItem, error: Exception) -> None:
        text = f"⚠️ **Could not play** `{clean(item.name)}` **, skipped!**\n\n`{clean(error)[:200]}`"
        for chat in [item.reply_chat or state.chat_id]:
            try:
                await self.client.send_message(chat, text, link_preview_options=NO_PREVIEW)
            except Exception:
                pass

    # ---- ticker: one task for all chats ----
    async def ticker(self, store) -> None:
        while True:
            await asyncio.sleep(self.every)
            for chat_id, card in list(self.cards.items()):
                state = store.peek(chat_id)
                if state and state.playback and card.label == PLAYING and card.posts:
                    try:
                        await self._edit(state, card)
                    except FloodWait as e:
                        log.warning("FloodWait %ss while updating cards", e.value)
                        await asyncio.sleep(e.value)

    async def repost(self, state: ChatState, chat_id: int, where: str | None) -> bool:
        """/now: post the card of the current media again in chat_id (the older post of that chat is not updated any more)."""
        card = self.cards.get(state.chat_id)
        if not card or not state.playback:
            return False
        card.posts = [p for p in card.posts if p[0].chat.id != chat_id]
        photo = await self._picture(state, card.item)
        card.posts.append(await self._send(chat_id, build_caption(self._data(state, card, where)), photo, where))
        return True

    def forget(self, chat_id: int, message_ids) -> None:
        """/delete removed some of our messages: stop editing those."""
        ids = set(message_ids)
        for card in self.cards.values():
            card.posts = [p for p in card.posts if not (p[0].chat.id == chat_id and p[0].id in ids)]

    # ---- internals ----
    def _data(self, state: ChatState, card: Card, where: str | None, label: str | None = None) -> CaptionData:
        item = card.item
        pb = state.playback if state.playback and state.playback.item is item else None
        nxt = state.queue[0] if state.queue and pb else None
        return CaptionData(
            label=label or card.label, by=card.by, kind=item.kind, lyrics=item.lyrics, live=item.live,
            name=item.name, link=item.link, pos=pb.position() if pb else card.__dict__.get("last_pos", 0.0),
            dur=item.duration, requester=item.requested_by.name if item.requested_by else None,
            loop=state.loop if pb else False, volume=state.volume, next_name=nxt.name if nxt else None,
            more=max(0, len(state.queue) - 1) if nxt else 0, where=where,
        )

    async def _picture(self, state: ChatState, item: MediaItem) -> str | None:
        cover = item.thumb or await self.profile.get()
        badge = "LIVE" if item.live else "LYRICS" if item.lyrics else "VIDEO" if item.kind == VIDEO else "AUDIO"
        info = CardInfo(title=item.title or item.name, artist=item.artist, badge=badge,
                        length=None if item.live else fmt_time(item.duration),
                        footer=" · ".join(x for x in (state.title, self.bot_name) if x))
        dest = self.files.path(state.chat_id, f"{item.key or 'media'}_card_{badge.lower()}", "jpg")
        rendered = await self.renderer.render(info, cover, dest)
        if rendered:
            rendered = self.files.acquire(rendered)
            item.files.append(rendered)
            return rendered
        return cover

    async def _send(self, chat_id: int, text: str, photo: str | None, where):
        if photo:
            try:
                return await self.client.send_photo(chat_id, photo=photo, caption=text), True, where
            except Exception as e:
                log.warning("card picture rejected: %s: %s", type(e).__name__, e)
        return await self.client.send_message(chat_id, text, link_preview_options=NO_PREVIEW), False, where

    async def _edit(self, state: ChatState, card: Card, label: str | None = None) -> None:
        if state.playback and state.playback.item is card.item:
            card.__dict__["last_pos"] = state.playback.position()
        alive = []
        for msg, has_photo, where in card.posts:
            text = build_caption(self._data(state, card, where, label))
            try:
                if has_photo:
                    await msg.edit_caption(text)
                else:
                    await msg.edit_text(text, link_preview_options=NO_PREVIEW)
            except FloodWait:
                raise
            except Exception as e:
                if is_gone(e):
                    log.info("a card message was removed in %s, the stream goes on without it", msg.chat.id)
                    continue
                if "MESSAGE_NOT_MODIFIED" not in str(e):
                    log.warning("could not update the card: %s: %s", type(e).__name__, e)
            alive.append((msg, has_photo, where))
        card.posts = alive

    async def _close(self, state: ChatState, card: Card, label: str, by: Requester | None) -> None:
        card.label, card.by = label, by.name if by else None
        try:
            await self._edit(state, card, label)
        except FloodWait:
            pass
