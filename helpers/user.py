"""The single Telegram user-account client used by the whole app."""

import os
from pyrogram import Client
from config import API_ID, API_HASH, PHONE_NUMBER, SESSION_NAME, SESSION_DIR

os.makedirs(SESSION_DIR, exist_ok=True)
SESSION_FILE = os.path.join(SESSION_DIR, f"{SESSION_NAME}.session")

User = Client(
    SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE_NUMBER,
    workdir=SESSION_DIR,
)

SENT = {}  # chat_id -> ids of the messages the bot itself sent (for the delete command), newest last
SENT_MAX = 300


def _remember(msg):
    items = msg if isinstance(msg, (list, tuple)) else [msg]
    for item in items:
        chat, mid = getattr(getattr(item, "chat", None), "id", None), getattr(item, "id", None)
        if chat is not None and mid is not None:
            ids = SENT.setdefault(chat, [])
            ids.append(mid)
            del ids[:-SENT_MAX]
    return msg


def _tracked(name):
    original = getattr(User, name)

    async def wrapper(*args, **kwargs):
        return _remember(await original(*args, **kwargs))

    setattr(User, name, wrapper)


for _name in ("send_message", "send_photo", "send_audio", "send_video", "send_document", "send_voice", "send_animation"):
    _tracked(_name)  # reply_text / reply_photo / ... of a Message end up in these
