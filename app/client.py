"""The single Telegram user-account client, plus a record of the messages it sent (for /delete)."""

import os
from pyrogram import Client
from app.config import settings

os.makedirs(settings.session_dir, mode=0o700, exist_ok=True)
SESSION_FILE = os.path.join(settings.session_dir, f"{settings.session_name}.session")


class SentMessages:
    """chat_id -> ids of messages the account itself sent (newest last, max per chat)."""

    def __init__(self, keep: int = 300):
        self.keep, self.ids = keep, {}

    def remember(self, msg):
        for item in msg if isinstance(msg, (list, tuple)) else [msg]:
            chat, mid = getattr(getattr(item, "chat", None), "id", None), getattr(item, "id", None)
            if chat is not None and mid is not None:
                ids = self.ids.setdefault(chat, [])
                ids.append(mid)
                del ids[:-self.keep]
        return msg

    def forget(self, chat_id: int, removed) -> None:
        removed = set(removed)
        self.ids[chat_id] = [i for i in self.ids.get(chat_id, []) if i not in removed]


def _track(client: Client, sent: SentMessages) -> None:
    for name in ("send_message", "send_photo", "send_audio", "send_video", "send_document", "send_voice", "send_animation"):
        original = getattr(client, name)

        async def wrapper(*args, _original=original, **kwargs):
            return sent.remember(await _original(*args, **kwargs))

        setattr(client, name, wrapper)   # reply_text / reply_photo / ... of a Message end up in these


def make_bot() -> tuple[Client | None, SentMessages]:
    """The optional real bot (BOT_TOKEN): only posts cards with buttons and answers button presses."""
    sent = SentMessages()
    if not settings.bot_token:
        return None, sent
    bot = Client("bot", api_id=settings.api_id, api_hash=settings.api_hash, bot_token=settings.bot_token,
                 workdir=settings.session_dir, no_updates=False)
    _track(bot, sent)
    return bot, sent


def make_client() -> tuple[Client, SentMessages]:
    client = Client(settings.session_name, api_id=settings.api_id, api_hash=settings.api_hash,
                    phone_number=settings.phone, workdir=settings.session_dir)
    sent = SentMessages()
    _track(client, sent)
    return client, sent
