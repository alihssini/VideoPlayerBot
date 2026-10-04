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

import functools
from typing import Callable
from pyrogram import Client
from config import SUDO_USERS
from pyrogram.types import Message


def _is_authorized(message: Message) -> bool:
    """The logged-in account itself and the SUDO_USERS may run commands."""
    if message.outgoing:
        return True
    user = message.from_user
    return bool(user and (user.is_self or user.id in SUDO_USERS))


def errors(func: Callable) -> Callable:
    @functools.wraps(func)
    async def decorator(client: Client, message: Message):
        try:
            return await func(client, message)
        except Exception as e:
            await message.reply_text(f"{type(e).__name__}: {e}")

    return decorator


def authorized_users_only(func: Callable) -> Callable:
    @functools.wraps(func)
    async def decorator(client: Client, message: Message):
        if _is_authorized(message):
            return await func(client, message)

    return decorator


def sudo_users_only(func: Callable) -> Callable:
    @functools.wraps(func)
    async def decorator(client: Client, message: Message):
        if _is_authorized(message):
            return await func(client, message)

    return decorator
