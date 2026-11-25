"""/list (your groups, numbered), /use (private chat target), /join and /leave (bot owners)."""

import re
from pyrogram.errors import RPCError
from pyrogram.handlers import MessageHandler
from commandmapper import tag
from core.errors import Silent, UserError
from plugins.common import cmd, in_group, require_any, sender_id
from ui.replies import clean, command, say

CHUNK = 3800
JOIN_ERRORS = {
    "UserAlreadyParticipant": "ℹ️ **This account is already a member of that group.**",
    "InviteHashExpired": "❌ **That invite link has expired or was revoked.**",
    "InviteHashInvalid": "❌ **That invite link is not valid.**",
    "UsernameNotOccupied": "❌ **No group with that username exists.**",
    "UsernameInvalid": "❌ **That username is not valid.**",
    "ChannelsTooMuch": "❌ **This account is in too many groups / channels already.** Leave one first.",
    "UserBannedInChannel": "❌ **This account is banned in that group.**",
}


def normalize_invite(text: str) -> str | None:
    """Invite link / t.me link / @username / username -> what join_chat accepts, or None."""
    text = text.strip()
    for pattern in (r"tg://join\?invite=([\w-]+)", r"(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/|\+)([\w-]+)"):
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            return f"https://t.me/+{found.group(1)}"
    found = re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/([A-Za-z]\w{3,})", text, re.IGNORECASE)
    if found:
        return f"@{found.group(1)}"
    name = text.lstrip("@")
    return f"@{name}" if re.fullmatch(r"[A-Za-z]\w{3,}", name) else None


def register(app) -> None:
    client, acl, groups = app.client, app.acl, app.groups

    def bot_owner(m) -> int:
        uid = sender_id(app, m)
        if not acl.is_bot_owner(uid):
            raise Silent()
        return uid

    @command
    async def list_groups(_, m):
        uid = await require_any(app, m)
        mine = await groups.numbered(uid, refresh=True)
        if not mine:
            raise UserError("**You have no group with this account.**")
        same = {}
        for _cid, title, _r in mine:
            same[title] = same.get(title, 0) + 1
        owner = acl.is_bot_owner(uid)
        current = acl.target(uid)
        lines = []
        for i, (cid, title, role) in enumerate(mine, 1):
            extra = f" [{cid}]" if same[title] > 1 else ""
            extra += "" if owner or role is None else f" · {role.label}"
            extra += " 🎯" if cid == current else ""
            lines.append(f"{i}. {clean(title)}{extra}")
        footer = (f"\n{tag('use')} `<number>` chooses the group for your commands here (🎯). "
                  f"Numbers stay until your next {tag('list')}.")
        if owner:
            footer += f"\n{tag('leave')} `<number>` leaves that group."
        pages, page = [], f"📋 **{'Joined groups' if owner else 'Your groups'}** ({len(lines)}):\n"
        for line in lines:
            if len(page) + len(line) + 1 > CHUNK:
                pages.append(page)
                page = ""
            page += "\n" + line
        pages.append(page + "\n" + footer)
        for text in pages:
            await say(m, text)

    @command
    async def use(_, m):
        uid = await require_any(app, m)
        if in_group(m):
            raise UserError(f"__{tag('use')} works in the private chat with this account.__")
        arg = (m.command[1] if len(m.command) > 1 else "").strip()
        if not arg:
            current = acl.target(uid)
            return await say(m, f"🎯 Your commands go to: **{clean(await groups.title(current))}**" if current
                             else f"🎯 __No group chosen.__ Send {tag('list')}, then {tag('use')} `<number>`.")
        if arg.lower() in ("off", "none", "0"):
            acl.set_target(uid, None)
            return await say(m, "🎯 **Group choice removed.**")
        chat_id = await groups.resolve(uid, arg)
        if chat_id is None:
            raise UserError(f"**There is no group number** `{clean(arg)}`. Send {tag('list')} to see your groups.")
        if acl.role(uid, chat_id) is None:
            raise UserError("**You have no role in that group.**")
        acl.set_target(uid, chat_id)
        await say(m, f"🎯 **Your commands here now go to** {clean(await groups.title(chat_id))}.")

    @command
    async def join(_, m):
        bot_owner(m)
        invite = normalize_invite(m.command[1]) if len(m.command) > 1 else None
        if not invite:
            raise UserError(f"__Send the invite link or username of the group:__ {tag('join')} `https://t.me/+AbCdEf123` · {tag('join')} `@groupname`")
        try:
            result = await client.join_chat(invite)
        except RPCError as e:
            name = type(e).__name__
            if name == "FloodWait":
                raise UserError(f"⏳ **Telegram asks to wait {getattr(e, 'value', '?')} seconds before joining again.**")
            return await say(m, JOIN_ERRORS.get(name) or f"❌ **Could not join!**\n\n`{name}: {clean(e)}`")
        kind = type(result).__name__
        if kind == "ChatJoinResultRequestSent":
            return await say(m, "📨 **Join request sent.** An admin of the group has to approve it.")
        title = getattr(getattr(result, "chat", None), "title", None) or "the group"
        await groups.joined(refresh=True)
        await say(m, f"✅ **Joined:** {clean(title)}\n\nSend {tag('list')} to refresh the numbers.")

    async def _leave(chat_id: int) -> None:
        state = app.store.peek(chat_id)
        if state:
            async with state.lock:
                if state.active:
                    await app.player.reset_locked(state, "⏹ Stopped (left the group)")
        await client.leave_chat(chat_id)
        groups.forget(chat_id)
        acl.archive(chat_id)

    @command
    async def leave(_, m):
        uid = bot_owner(m)
        arg = (m.command[1] if len(m.command) > 1 else "").strip()
        if arg:
            chat_id = await groups.resolve(uid, arg)
            if chat_id is None:
                raise UserError(f"**There is no group number** `{clean(arg)}`. Send {tag('list')} first.")
            title = await groups.title(chat_id)
            await _leave(chat_id)
            return await say(m, f"👋 **Left:** {clean(title)}")
        if in_group(m):
            await say(m, "👋 **Leaving this group ...**")
            return await _leave(m.chat.id)
        raise UserError(f"__Send {tag('leave')} inside a group, or {tag('leave')} `<number>` here (numbers from {tag('list')}).__")

    for key, handler in (("list", list_groups), ("use", use), ("join", join), ("leave", leave)):
        client.add_handler(MessageHandler(handler, cmd(key)), group=-1)
