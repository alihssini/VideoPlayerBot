"""/start /help /about /id /restart."""

import os
import sys
import asyncio
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from core.acl import Role
from core.errors import Silent
from plugins.common import cmd, in_group, require_any, sender_id
from ui.replies import command, say
from ui.texts import ABOUT, START, help_text


def register(app) -> None:
    client, acl = app.client, app.acl

    def best_role(uid: int, m) -> Role | None:
        if in_group(m):
            return acl.role(uid, m.chat.id)
        if acl.is_bot_owner(uid):
            return Role.BOT_OWNER
        roles = acl.group_roles(uid).values()
        return max(roles, default=Role.SUDO if uid in acl.global_sudo.ids() else None)

    @command
    async def start(_, m):
        uid = await require_any(app, m)
        if in_group(m) and acl.role(uid, m.chat.id) is None:
            raise Silent()
        await say(m, START)

    @command
    async def help_(_, m):
        uid = await require_any(app, m)
        role = best_role(uid, m)
        if role is None:
            raise Silent()
        text = help_text(role, private=not in_group(m))
        for i in range(0, len(text), 3900):
            await say(m, text[i:i + 3900])

    @command
    async def about(_, m):
        await require_any(app, m)
        await say(m, ABOUT)

    async def my_id(_, m):       # open to everyone, private chat only
        if m.from_user:
            await say(m, f"🆔 Your Telegram ID: `{m.from_user.id}`")

    @command
    async def restart(_, m):
        if not acl.is_bot_owner(sender_id(app, m)):
            raise Silent()
        await say(m, "🔄 `Restarting ...`")
        await app.player.shutdown()
        await asyncio.sleep(2)
        os.execl(sys.executable, sys.executable, *sys.argv)

    client.add_handler(MessageHandler(start, cmd("start")))
    client.add_handler(MessageHandler(help_, cmd("help")))
    client.add_handler(MessageHandler(about, cmd("about")))
    client.add_handler(MessageHandler(my_id, filters.private & cmd("id")), group=-1)
    client.add_handler(MessageHandler(restart, cmd("restart")))
