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

from pyrogram import filters
from helpers.user import User
from commandmapper import names
from config import COMMAND_PREFIXES
from helpers.decorators import authorized_users_only
from translations import START_TEXT, HELP_TEXT, ABOUT_TEXT


@User.on_message(filters.command(names("start"), prefixes=COMMAND_PREFIXES))
@authorized_users_only
async def start(client, message):
    await message.reply_text(START_TEXT)


@User.on_message(filters.command(names("help"), prefixes=COMMAND_PREFIXES))
@authorized_users_only
async def help_(client, message):
    await message.reply_text(HELP_TEXT)


@User.on_message(filters.command(names("about"), prefixes=COMMAND_PREFIXES))
@authorized_users_only
async def about(client, message):
    await message.reply_text(ABOUT_TEXT)


# Open to everyone, but only in private chat: tells the sender their own Telegram number.
# group=-1 so it always runs, also when the PM auto reply (nopm) matches the same message.
@User.on_message(filters.private & filters.command(names("id"), prefixes=COMMAND_PREFIXES), group=-1)
async def my_id(client, message):
    user = message.from_user
    if not user:
        return
    try:
        await message.reply_text(f"🆔 Your Telegram ID: `{user.id}`")
    except Exception as e:
        print(f"[WARN] - /id reply failed: {e}")
