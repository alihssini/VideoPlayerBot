"""The groups the account is in, who may see which, and the numbered lists used by /list, /use and '/pause 3'."""

import re
import time
import asyncio
import logging
from pyrogram import enums
from core.acl import AclService, Role

log = logging.getLogger("vpb.groups")
GROUP_TYPES = (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP)
JOINED_TTL, MEMBER_TTL = 300, 900


class GroupDirectory:
    def __init__(self, client, acl: AclService):
        self.client, self.acl = client, acl
        self._joined: list[tuple[int, str]] = []
        self._joined_at = 0.0
        self._members: dict[tuple[int, int], tuple[bool, float]] = {}
        self._lists: dict[int, list[int]] = {}       # user -> numbered group ids of his last list
        self._lock = asyncio.Lock()

    async def joined(self, refresh: bool = False) -> list[tuple[int, str]]:
        """(id, title) of all joined groups, archived ones included, sorted by title (cached 5 min)."""
        async with self._lock:
            if refresh or not self._joined or time.monotonic() - self._joined_at > JOINED_TTL:
                found = {}
                for archive in (False, True):
                    try:
                        async for dialog in self.client.get_dialogs(**({"from_archive": True} if archive else {})):
                            chat = dialog.chat
                            if chat and chat.type in GROUP_TYPES and not chat.is_deactivated:
                                found[chat.id] = chat.title or str(chat.id)
                    except Exception as e:
                        if not archive:
                            raise
                        log.debug("archive dialogs unavailable: %s", e)
                self._joined = sorted(found.items(), key=lambda kv: (kv[1].casefold(), kv[0]))
                self._joined_at = time.monotonic()
            return list(self._joined)

    def forget(self, chat_id: int) -> None:
        self._joined = [g for g in self._joined if g[0] != chat_id]

    async def title(self, chat_id: int) -> str:
        for cid, title in await self.joined():
            if cid == chat_id:
                return title
        return str(chat_id)

    async def is_member(self, chat_id: int, uid: int) -> bool:
        cached = self._members.get((chat_id, uid))
        if cached and time.monotonic() - cached[1] < MEMBER_TTL:
            return cached[0]
        try:
            await self.client.get_chat_member(chat_id, uid)
            result = True
        except Exception:
            result = False          # UserNotParticipant, no rights to look, ...
        self._members[(chat_id, uid)] = (result, time.monotonic())
        await asyncio.sleep(0.2)   # be gentle with Telegram
        return result

    async def visible(self, uid: int) -> list[tuple[int, str, Role]]:
        """Groups this user may command: bot owners all; others where they have a role (global SUDO: where they
        are a member together with the account)."""
        joined = await self.joined()
        if self.acl.is_bot_owner(uid):
            return [(cid, title, Role.BOT_OWNER) for cid, title in joined]
        roles = self.acl.group_roles(uid)
        out = [(cid, title, roles[cid]) for cid, title in joined if cid in roles]
        if uid in self.acl.global_sudo.ids():
            for cid, title in joined:
                if cid not in roles and await self.is_member(cid, uid):
                    out.append((cid, title, Role.SUDO))
            out.sort(key=lambda g: (g[1].casefold(), g[0]))
        return out

    async def numbered(self, uid: int, refresh: bool = False) -> list[tuple[int, str, Role]]:
        """The user's numbered list; the numbers stay until his next /list (rebuilt automatically after a restart)."""
        groups = await self.visible(uid) if refresh or uid not in self._lists else None
        if groups is not None:
            self._lists[uid] = [g[0] for g in groups]
            return groups
        titles = dict(await self.joined())
        return [(cid, titles.get(cid, str(cid)), self.acl.role(uid, cid)) for cid in self._lists[uid]]

    async def resolve(self, uid: int, token: str) -> int | None:
        """'3' / '#3' (list number) or a group id -> chat id, or None."""
        token = token.lstrip("#")
        if not re.fullmatch(r"-?\d+", token):
            return None
        number = int(token)
        groups = await self.numbered(uid)
        if 1 <= number <= len(groups):
            return groups[number - 1][0]
        return number if any(g[0] == number for g in groups) else None
