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
import sys
import asyncio
import importlib
from pyrogram import idle
from helpers.user import User, SESSION_FILE
from helpers.voice import call_py
from helpers.media import profile_photo
from helpers.ytdl import wipe_downloads, sweeper

if not os.path.isfile(SESSION_FILE):
    sys.exit("[ERROR] - Not logged in yet. Run `.venv/bin/python login.py` once to log in with your Telegram account.")

# registers all command handlers on the user client
for _plugin in ("nopm", "private", "stream", "download"):
    importlib.import_module(f"plugins.{_plugin}")

if not os.path.isdir("./downloads"):
    os.makedirs("./downloads")
wipe_downloads()  # nothing is playing at startup, so leftovers are stale


async def main():
    try:
        await call_py.start()  # also starts the Telegram client
    except EOFError:
        sys.exit("[ERROR] - Session is no longer valid and needs a new login. Run `.venv/bin/python login.py`.")

    me = await User.get_me()
    print(f"\n[INFO] - STARTED VIDEO PLAYER as {me.first_name} (id {me.id}) !")

    photo = await profile_photo(User)
    print(f"[INFO] - fallback picture for the now-playing card: {photo or "none (text-only)"}")

    asyncio.create_task(sweeper())  # periodic cleanup of stale files in ./downloads
    await idle()
    await User.stop()
    print("\n[INFO] - STOPPED VIDEO PLAYER !")


asyncio.get_event_loop().run_until_complete(main())
