"""Role lists, all built from one table (no copy per list):

  /admins /promote /demote        SUDO users of a group      list: group owners · change: group owners
  /owners /addowner /delowner     owners of a group          list: group owners · change: bot owners
  /gadmins /gpromote /gdemote     global SUDO users          bot owners
  /botowners /addbotowner /delbotowner   bot owners        list: bot owners · change: root owners only
Group lists work in the group or in private chat with a group number ('/promote 3 @user') or the /use group.
"""

import re
from dataclasses import dataclass
from pyrogram.handlers import MessageHandler
from commandmapper import tag
from core.acl import Role
from core.errors import Silent, UserError
from plugins.common import cmd, require_any, sender_id, target
from ui.replies import clean, command, say


@dataclass(frozen=True)
class RoleList:
    list_key: str
    add_key: str
    del_key: str
    title: str
    scope: str                      # "group" | "global" | "bot"
    need_list: Role
    need_change: Role               # Role.BOT_OWNER + root_only for bot owners
    root_only: bool = False


LISTS = [
    RoleList("sudolist", "addsudo", "delsudo", "SUDO users", "group", Role.GROUP_OWNER, Role.GROUP_OWNER),
    RoleList("owners", "addowner", "delowner", "Group owners", "group", Role.GROUP_OWNER, Role.BOT_OWNER),
    RoleList("gsudolist", "gaddsudo", "gdelsudo", "Global SUDO users", "global", Role.BOT_OWNER, Role.BOT_OWNER),
    RoleList("botowners", "addbotowner", "delbotowner", "Bot owners", "bot", Role.BOT_OWNER, Role.BOT_OWNER, root_only=True),
]


def register(app) -> None:
    acl, client = app.acl, app.client
    names: dict[int, str] = {}

    async def display(uid: int, stored: str = "") -> str:
        if uid not in names:
            try:
                user = await client.get_users(uid)
                full = " ".join(x for x in (user.first_name, user.last_name) if x) or "no name"
                names[uid] = full + (f" @{user.username}" if user.username else "")
            except Exception:
                names[uid] = stored or "name not available"
        return f"{clean(names[uid])} [{uid}]"

    def users_of(spec: RoleList, chat_id: int | None):
        return {"group": lambda: (acl.group_sudo(chat_id) if spec.list_key == "sudolist" else acl.group_owners(chat_id)),
                "global": lambda: acl.global_sudo, "bot": lambda: acl.bot_owners}[spec.scope]()

    async def scope(spec: RoleList, m, need: Role):
        """(chat_id | None, title, args) after the permission check."""
        if spec.scope == "group":
            t = await target(app, m, need, bare="with_more")
            return t.chat_id, t.title, t.args
        uid = sender_id(app, m)
        allowed = acl.is_root(uid) if (spec.root_only and need == spec.need_change) else acl.role(uid, None) == Role.BOT_OWNER
        if not allowed:
            if acl.has_any_role(uid):
                raise UserError("**Only root owners may change the bot owners.**" if spec.root_only else "**Only bot owners may do that.**")
            raise Silent()
        return None, "", list(m.command[1:])

    async def who(m, args, entries=None) -> tuple[int, object | None]:
        """Reply, @username, id — or a list number (entries given = remove)."""
        if m.reply_to_message and m.reply_to_message.from_user:
            return m.reply_to_message.from_user.id, m.reply_to_message.from_user
        arg = args[0] if args else ""
        if re.fullmatch(r"-?\d+", arg):
            number = int(arg)
            if entries is not None and 1 <= number <= len(entries) and number not in {int(e["id"]) for e in entries}:
                return int(entries[number - 1]["id"]), None
            try:
                return number, await client.get_users(number)
            except Exception:
                return number, None
        name = arg.lstrip("@")
        if re.fullmatch(r"[A-Za-z]\w{3,}", name):
            try:
                user = await client.get_users(name)
                return user.id, user
            except Exception:
                raise UserError(f"**No account with the username @{name} was found.**")
        raise UserError("__Reply to the person's message, or send the id / @username.__")

    def make(spec: RoleList):
        @command
        async def show(_, m):
            chat_id, title, _args = await scope(spec, m, spec.need_list)
            entries = users_of(spec, chat_id).entries()
            head = f"👥 **{spec.title}**" + (f" of **{title}**" if title else "")
            lines = [f"{i}. {await display(int(e['id']), e.get('name', ''))}" for i, e in enumerate(entries, 1)]
            if spec.scope == "bot":
                roots = [f"🔑 {await display(uid)}" for uid in sorted(acl.root)]
                lines = roots + lines
            if spec.list_key == "sudolist":
                globals_ = [f"🌐 {await display(int(e['id']), e.get('name', ''))}" for e in acl.global_sudo.entries()]
                if globals_:
                    lines += ["", "Global (every group):", *globals_]
            body = "\n".join(lines) if lines else "__nobody yet__"
            await say(m, f"{head} ({len(entries)})\n\n{body}\n\n{tag(spec.add_key)} `<reply | id | @username>` · "
                         f"{tag(spec.del_key)} `<reply | number | id | @username>`")

        @command
        async def add(_, m):
            chat_id, title, args = await scope(spec, m, spec.need_change)
            uid, user = await who(m, args)
            if user is not None and getattr(user, "is_bot", False):
                raise UserError("**That is a bot account.**")
            if user is None:
                raise UserError(f"**Telegram does not know the id {uid}.** Send the @username or reply to a message of that person.")
            if uid == app.me_id:
                raise UserError("**That is this account itself, it always has full access.**")
            name = " ".join(x for x in (user.first_name, user.last_name) if x)
            if not users_of(spec, chat_id).add(uid, name, sender_id(app, m)):
                return await say(m, f"ℹ️ Already in {spec.title.lower()}: {await display(uid, name)}")
            names.pop(uid, None)
            await say(m, f"✅ Added to {spec.title.lower()}" + (f" of {title}" if title else "") + f": {await display(uid, name)}")

        @command
        async def remove(_, m):
            chat_id, title, args = await scope(spec, m, spec.need_change)
            entries = users_of(spec, chat_id).entries()
            uid, _user = await who(m, args, entries)
            if spec.scope == "bot" and acl.is_root(uid):
                raise UserError("**Root owners (OWNER_USERS in .env) cannot be removed by a command.**")
            if not users_of(spec, chat_id).remove(uid):
                return await say(m, f"ℹ️ Not in {spec.title.lower()}: {await display(uid)}")
            if acl.target(uid) == chat_id and acl.role(uid, chat_id) is None:
                acl.set_target(uid, None)      # the /use choice of a user who lost his role there
            await say(m, f"🗑 Removed from {spec.title.lower()}" + (f" of {title}" if title else "") + f": {await display(uid)}")

        return show, add, remove

    for spec in LISTS:
        show, add, remove = make(spec)
        client.add_handler(MessageHandler(show, cmd(spec.list_key)), group=-1)
        client.add_handler(MessageHandler(add, cmd(spec.add_key)), group=-1)
        client.add_handler(MessageHandler(remove, cmd(spec.del_key)), group=-1)

    @command
    async def perms(_, m):
        uid = await require_any(app, m)
        if m.chat.type.name != "PRIVATE":
            role = acl.role(uid, m.chat.id)
            return await say(m, f"🔐 Your role here: **{role.label if role else 'none'}**")
        lines = ["🔐 **Your roles**", ""]
        if acl.is_bot_owner(uid):
            lines.append("👑 **bot owner**" + (" (root)" if acl.is_root(uid) else "") + " — every group")
        elif uid in acl.global_sudo.ids():
            lines.append("🌐 **global SUDO user** — every group you share with this account")
        for chat_id, title, role in await app.groups.numbered(uid, refresh=True):
            lines.append(f"• {title}: **{role.label if role else 'none'}**")
        current = acl.target(uid)
        if current:
            lines += ["", f"🎯 Commands here go to: **{await app.groups.title(current)}** ({tag('use')})"]
        await say(m, "\n".join(lines))

    client.add_handler(MessageHandler(perms, cmd("perms")), group=-1)
