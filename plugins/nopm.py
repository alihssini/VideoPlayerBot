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
from config import REPLY_MESSAGE, OLD_PMS


@User.on_message(filters.private & filters.incoming & ~filters.bot & ~filters.service & ~filters.me & ~filters.chat([777000, 454000]))
async def nopm(client, message):
    # text-only auto reply to private messages, only active when REPLY_MESSAGE is set in .env
    if REPLY_MESSAGE is None:
        return
    try:
        reply = await message.reply_text(REPLY_MESSAGE, quote=False)
        old = OLD_PMS.get(message.chat.id)
        if old:
            await client.delete_messages(message.chat.id, old)
        OLD_PMS[message.chat.id] = reply.id
    except Exception as e:
        print(f"[WARN] - PM auto reply failed: {e}")
