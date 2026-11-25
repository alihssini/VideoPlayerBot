"""Shared by all command plugins: filters, the target group of a command and the permission check."""

import re
from dataclasses import dataclass
from pyrogram import filters
from commandmapper import names, tag
from app.config import settings
from core.acl import Role
from core.errors import Silent, UserError
from core.models import Requester
from services.groups import GROUP_TYPES

NUMBER = re.compile(r"#?-?\d+")


def cmd(key: str):
    return filters.command(names(key), prefixes=list(settings.prefixes))


@dataclass
class Target:
    chat_id: int
    title: str
    role: Role
    args: list
    dm: bool
    user: Requester | None

    @property
    def where(self) -> str:
        """' in **Group**' for answers in the private chat, '' in the group itself."""
        return f" in **{_plain(self.title)}**" if self.dm else ""


def _plain(text) -> str:
    return "".join(" " if c in "`*_[]~|" else c for c in str(text)).strip()


def sender_id(app, m) -> int | None:
    if m.outgoing:
        return app.me_id
    return m.from_user.id if m.from_user else None


def in_group(m) -> bool:
    return m.chat.type in GROUP_TYPES


def anonymous(m) -> None:
    if m.from_user is None and in_group(m) and m.sender_chat and m.sender_chat.id == m.chat.id:
        raise UserError("__Send the command as yourself, not anonymously as the group.__")


async def require_any(app, m) -> int:
    """Private-chat commands that need some role but no group (help, /list, /use, /perms)."""
    anonymous(m)
    uid = sender_id(app, m)
    if not app.acl.has_any_role(uid):
        raise Silent()
    return uid


async def target(app, m, need: Role = Role.SUDO, bare: str = "always") -> Target:
    """The group the command is for, after checking the sender's role there.

    In a group: that group (strangers are ignored silently).
    In private chat: a group number first ('#3' always; a bare '3' when bare == "always", or when bare ==
    "with_more" and more words or a replied media follow), else the /use choice, else the only group the user
    has a role in."""
    anonymous(m)
    uid = sender_id(app, m)
    args = list(m.command[1:])
    user = Requester.of(m.from_user)
    if in_group(m):
        role = app.acl.role(uid, m.chat.id)
        if role is None or role < need:
            raise Silent()
        app.acl.set_title(m.chat.id, m.chat.title or "")
        return Target(m.chat.id, m.chat.title or str(m.chat.id), role, args, False, user)

    if not app.acl.has_any_role(uid):
        raise Silent()
    chat_id = None
    if args and NUMBER.fullmatch(args[0]):
        token = args[0]
        explicit = token.startswith("#") or bare == "always" or (bare == "with_more" and (len(args) > 1 or m.reply_to_message))
        if explicit:
            chat_id = await app.groups.resolve(uid, token)
            if chat_id is None:
                raise UserError(f"**There is no group number** `{token.lstrip('#')}`. Send {tag('list')} to see your groups.")
            args = args[1:]
    if chat_id is None:
        chat_id = app.acl.target(uid)
    if chat_id is None:
        mine = await app.groups.numbered(uid)
        if len(mine) == 1:
            chat_id = mine[0][0]
        else:
            raise UserError(f"**Which group?** Choose one with {tag('use')} `<number>` (numbers from {tag('list')}), "
                            f"or put `#<number>` after the command.")
    role = app.acl.role(uid, chat_id)
    if role is None or role < need:
        raise UserError(f"**You are not allowed to do that in this group** (needs {need.label}).")
    return Target(chat_id, await app.groups.title(chat_id), role, args, True, user)
