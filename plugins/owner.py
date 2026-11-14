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

Owner-only commands to manage the groups of the account: list, join, leave.
Owners are the OWNER_USERS of .env plus the logged-in account itself.
"""

import re
from pyrogram import filters, enums
from pyrogram.errors import RPCError
from helpers.user import User
from helpers.voice import call_py
from commandmapper import names, tag
from config import COMMAND_PREFIXES
from helpers.decorators import owner_only
from plugins.stream import ACTIVE, CARDS, _lock, forget, clear_queue, release_file, update_card

PLAIN = enums.ParseMode.DISABLED  # group titles may contain markdown characters
GROUP_TYPES = (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP)
CHUNK = 3800  # Telegram allows 4096 characters per message

# Numbered groups of the last list command. The order is fixed until the next list command
# (sorted by title, then id), so a leave number keeps pointing at the same group.
SNAPSHOT = []  # [{"id", "title", "left"}]

JOIN_ERRORS = {
    "UserAlreadyParticipant": "ℹ️ **This account is already a member of that group.**",
    "InviteHashExpired": "❌ **That invite link has expired or was revoked.**",
    "InviteHashInvalid": "❌ **That invite link is not valid.**",
    "UsernameNotOccupied": "❌ **No group with that username exists.**",
    "UsernameInvalid": "❌ **That username is not valid.**",
    "ChannelsTooMuch": "❌ **This account is in too many groups / channels already.** Leave one first.",
    "UserBannedInChannel": "❌ **This account is banned in that group.**",
}


def _normalize(text: str):
    """Invite link / t.me link / @username / username -> what join_chat accepts, or None."""
    text = text.strip()
    found = re.search(r"tg://join\?invite=([\w-]+)", text, re.IGNORECASE)
    if found:
        return f"https://t.me/+{found.group(1)}"
    found = re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/(?:joinchat/|\+)([\w-]+)", text, re.IGNORECASE)
    if found:
        return f"https://t.me/+{found.group(1)}"
    found = re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/([A-Za-z]\w{3,})", text, re.IGNORECASE)
    if found:
        return f"@{found.group(1)}"
    name = text.lstrip("@")
    if re.fullmatch(r"[A-Za-z]\w{3,}", name):
        return f"@{name}"
    return None


async def _say(m, text, **kwargs):
    try:
        return await m.reply_text(text, **kwargs)
    except Exception:
        return None  # e.g. the account has already left the chat the command came from


async def _dialogs(client):
    """All dialogs, archived ones included."""
    async for dialog in client.get_dialogs():
        yield dialog
    try:
        async for dialog in client.get_dialogs(from_archive=True):
            yield dialog
    except Exception:
        pass


async def _leave(client, chat_id: int):
    """Stops a stream running there, then leaves the group."""
    async with _lock(chat_id):
        ACTIVE.pop(chat_id, None)
        forget(chat_id)
        clear_queue(chat_id)
        release_file(chat_id)
        try:
            await call_py.leave_call(chat_id)
        except Exception:
            pass  # not in a voice chat
    try:
        await update_card(CARDS.pop(chat_id, None), "⏹ Stopped")
    except Exception:
        pass
    await client.leave_chat(chat_id)


def _mark_left(chat_id: int):
    for entry in SNAPSHOT:
        if entry["id"] == chat_id:
            entry["left"] = True


@User.on_message(filters.command(names("list"), prefixes=COMMAND_PREFIXES) & filters.private, group=-1)
@owner_only
async def list_groups(client, m):
    found = {}
    async for dialog in _dialogs(client):
        chat = dialog.chat
        if chat and chat.type in GROUP_TYPES and not chat.is_deactivated:  # deactivated = old group that was upgraded to a supergroup
            found[chat.id] = chat.title or str(chat.id)
    items = sorted(found.items(), key=lambda kv: (kv[1].casefold(), kv[0]))
    SNAPSHOT[:] = [{"id": cid, "title": title, "left": False} for cid, title in items]
    if not SNAPSHOT:
        return await m.reply_text("📭 This account has not joined any group.", parse_mode=PLAIN)

    leave = COMMAND_PREFIXES[0] + names("leave")[0]
    same = {}
    for entry in SNAPSHOT:
        same[entry["title"]] = same.get(entry["title"], 0) + 1
    # groups that share a title get their id appended, so they can be told apart
    lines = [f"{i}. {entry['title']}" + (f" [{entry['id']}]" if same[entry["title"]] > 1 else "") for i, entry in enumerate(SNAPSHOT, 1)]
    footer = f"\n{leave} <number> leaves that group. Numbers stay the same until you send the list command again."
    pages, page = [], f"📋 Joined groups ({len(lines)}):\n"
    for line in lines:
        if len(page) + len(line) + 1 > CHUNK:
            pages.append(page)
            page = ""
        page += "\n" + line
    pages.append(page + "\n" + footer)
    for text in pages:
        await m.reply_text(text, parse_mode=PLAIN)


@User.on_message(filters.command(names("join"), prefixes=COMMAND_PREFIXES), group=-1)
@owner_only
async def join_group(client, m):
    target = _normalize(m.command[1]) if len(m.command) > 1 else None
    if not target:
        return await _say(m, f"❗ __Send the invite link or username of the group:__\n\n{tag('join')} `https://t.me/+AbCdEf123` · {tag('join')} `@groupname`")
    try:
        result = await client.join_chat(target)
    except RPCError as e:
        name = type(e).__name__
        if name == "FloodWait":
            return await _say(m, f"⏳ **Telegram asks to wait {getattr(e, 'value', '?')} seconds before joining again.**")
        return await _say(m, JOIN_ERRORS.get(name) or f"❌ **Could not join !** \n\nError: `{name}: {e}`")
    except Exception as e:
        return await _say(m, f"❌ **Could not join !** \n\nError: `{type(e).__name__}: {e}`")

    kind = type(result).__name__
    if kind == "ChatJoinResultRequestSent":
        return await _say(m, "📨 **Join request sent.** An admin of the group has to approve it.")
    if kind == "ChatJoinResultSuccess":
        title = getattr(result.chat, "title", None) or str(result.chat.id)
        return await _say(m, f"✅ Joined: {title}\n\nSend {COMMAND_PREFIXES[0]}{names('list')[0]} in private chat to refresh the numbered list.", parse_mode=PLAIN)
    await _say(m, f"❌ **Joining was not completed:** `{kind}`")


@User.on_message(filters.command(names("leave"), prefixes=COMMAND_PREFIXES), group=-1)
@owner_only
async def leave_group(client, m):
    arg = m.command[1].strip() if len(m.command) > 1 else ""

    if arg:  # leave by the number of the list command
        if not arg.isdigit():
            return await _say(m, f"❗ __Send the group number from {tag('list')}:__ {tag('leave')} `3`")
        if not SNAPSHOT:
            return await _say(m, f"❗ __Send {tag('list')} in private chat first, to get the numbers.__")
        number = int(arg)
        if not 1 <= number <= len(SNAPSHOT):
            return await _say(m, f"❌ **There is no group number {number}.** The list has {len(SNAPSHOT)}.")
        entry = SNAPSHOT[number - 1]
        if entry["left"]:
            return await _say(m, f"ℹ️ Already left: {entry['title']}", parse_mode=PLAIN)
        try:
            await _leave(client, entry["id"])
        except Exception as e:
            return await _say(m, f"❌ **Could not leave !** \n\nError: `{type(e).__name__}: {e}`")
        entry["left"] = True
        return await _say(m, f"👋 Left: {entry['title']}", parse_mode=PLAIN)

    if m.chat.type in GROUP_TYPES:  # no number inside a group: leave this group right away
        chat_id = m.chat.id
        await _say(m, "👋 **Leaving this group ...**")
        try:
            await _leave(client, chat_id)
        except Exception as e:
            return await _say(m, f"❌ **Could not leave !** \n\nError: `{type(e).__name__}: {e}`")
        _mark_left(chat_id)
        return

    await _say(m, f"❗ __Send {tag('leave')} inside a group, or {tag('leave')} `<number>` here with the number from {tag('list')}.__")
