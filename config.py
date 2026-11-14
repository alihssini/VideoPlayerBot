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
from os import getenv
from dotenv import load_dotenv

load_dotenv()

admins = {}
OLD_PMS = {}
AUDIO_CALL = {}
VIDEO_CALL = {}


def _required(name: str) -> str:
    value = (getenv(name) or "").strip()
    if not value:
        raise SystemExit(
            f"[ERROR] - {name} is missing in .env (get API_ID / API_HASH from https://my.telegram.org)"
        )
    return value


# Telegram user-account login (no bot token needed)
API_ID = int(_required("API_ID"))
API_HASH = _required("API_HASH")
PHONE_NUMBER = (getenv("PHONE_NUMBER") or "").strip() or None  # optional, otherwise asked at login
SESSION_NAME = (getenv("SESSION_NAME") or "user").strip()
SESSION_DIR = (getenv("SESSION_DIR") or "sessions").strip()

# Besides the logged-in account itself, these user IDs may control playback
_sudo = (getenv("SUDO_USERS") or getenv("SUDOERS") or "").replace(",", " ")
SUDO_USERS = [int(x) for x in _sudo.split() if x.lstrip("-").isdigit()]

# Owners (plus the logged-in account itself) may manage the groups of the bot: list / join / leave
_owner = (getenv("OWNER_USERS") or getenv("OWNERS") or "").replace(",", " ")
OWNER_USERS = [int(x) for x in _owner.split() if x.lstrip("-").isdigit()]

# Prefixes accepted for commands, e.g. /play  !play  .play
COMMAND_PREFIXES = ["/", "!", "."]

# Optional text auto-reply to incoming private messages (disabled when empty)
REPLY_MESSAGE = (getenv("REPLY_MESSAGE") or "").strip() or None

# Max size (MB) of a single downloaded video/audio file; bigger ones are refused to protect the disk
DOWNLOAD_MAX_MB = int(getenv("DOWNLOAD_MAX_MB") or 1000)

# Video quality preset: SD_360p (default, light on CPU), SD_480p, HD_720p, FHD_1080p
VIDEO_QUALITY = (getenv("VIDEO_QUALITY") or "SD_360p").strip()
