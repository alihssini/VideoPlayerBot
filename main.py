"""
VideoPlayerBot, Telegram Video Chat Bot
Copyright (c) 2021  Asm Safone <https://github.com/AsmSafone>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>
"""

import os
import re
import sys
import time
import shutil
import signal
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] - %(name)s: %(message)s")
for noisy in ("pyrogram", "httpx"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("vpb")

from app.client import SESSION_FILE  # noqa: E402
from app.config import settings      # noqa: E402

if not os.path.isfile(SESSION_FILE):
    sys.exit("[ERROR] - Not logged in yet. Run `.venv/bin/python login.py` once to log in with your Telegram account.")


def drop_legacy_sudo_from_env() -> None:
    """SUDO_USERS now live in data/acl/global_sudo.json: remove them from .env (backup in ~/backups first)."""
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(env):
        return
    with open(env, encoding="utf-8") as f:
        lines = f.read().splitlines()
    kept = [line for line in lines if not re.match(r"\s*(SUDO_USERS|SUDOERS)\s*=", line)]
    if kept == lines:
        return
    backups = os.path.expanduser("~/backups")
    os.makedirs(backups, exist_ok=True)
    backup = os.path.join(backups, f".env.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    shutil.copy2(env, backup)
    os.chmod(backup, 0o600)
    with open(env, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")
    os.chmod(env, 0o600)


async def main() -> None:
    from app.container import build
    app = build()
    try:
        await app.voice.start()           # also starts the Telegram client
    except EOFError:
        sys.exit("[ERROR] - Session is no longer valid and needs a new login. Run `.venv/bin/python login.py`.")

    if app.bot:
        try:
            await app.bot.start()
            bot_me = await app.bot.get_me()
            app.cards.bot = app.bot
            log.info("card buttons by the bot @%s (add it to the groups; private-chat cards need /start in the bot)", bot_me.username)
        except Exception as e:
            log.warning("BOT_TOKEN did not work (%s: %s), cards have no buttons", type(e).__name__, e)
            app.bot = None

    me = await app.client.get_me()
    app.me_id = me.id
    app.acl.add_root(me.id)
    app.cards.bot_name = me.first_name or ""
    migrated = app.acl.migrate_legacy_sudo(settings.legacy_sudo)
    if migrated:
        log.info("moved %d SUDO_USERS from .env to data/acl/global_sudo.json", migrated)
    if app.acl.global_sudo.file.exists:
        drop_legacy_sudo_from_env()
    app.files.wipe()                      # nothing plays at startup, leftovers are stale
    log.info("STARTED VIDEO PLAYER as %s (id %s)", me.first_name, me.id)

    background = [asyncio.create_task(c) for c in (app.cards.ticker(app.store), app.recovery.watchdog(), app.files.sweeper(), app.idle.run())]
    from app.restore import restore
    saved = app.session.take()
    if saved:
        background.append(asyncio.create_task(restore(app, saved)))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("stopping: leaving the voice chats ...")
    await app.stop_all()                 # remember what plays, leave every voice chat, close the cards
    for task in background:
        task.cancel()
    if app.bot:
        try:
            await app.bot.stop()
        except Exception:
            pass
    await app.client.stop()
    log.info("STOPPED VIDEO PLAYER")


if __name__ == "__main__":
    # pyrogram binds its event loop at import time: run main() on that loop
    asyncio.get_event_loop().run_until_complete(main())
