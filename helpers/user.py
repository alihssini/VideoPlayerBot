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
