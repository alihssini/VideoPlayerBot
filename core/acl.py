"""Roles, stored as small JSON files you can edit by hand (picked up without restart):

data/acl/bot_owners.json        {"users": [{"id", "name", "added_by", "added_at"}]}   runtime bot owners
data/acl/global_sudo.json       {"users": [...]}                                      SUDO in every group
data/acl/dm_targets.json        {"<user id>": <chat id>}                              /use choice per user
data/acl/groups/<chat_id>.json  {"title", "owners": [...], "sudo": [...]}             per group

Root owners (the account itself + OWNER_USERS of .env) are bot owners that commands can never remove.
A file with a JSON error is not loaded: the last good version stays active and on_error is told about it.
Examples with fake ids: examples/acl/ (see examples/README.md).
"""

import os
import json
import time
import logging
import tempfile
from enum import IntEnum
from typing import Callable

log = logging.getLogger("vpb.acl")


class Role(IntEnum):
    SUDO = 1
    GROUP_OWNER = 2
    BOT_OWNER = 3

    @property
    def label(self) -> str:
        return {1: "SUDO user", 2: "group owner", 3: "bot owner"}[self.value]


class JsonFile:
    """One JSON document, re-read when its mtime changes, written atomically with mode 0600."""

    def __init__(self, path: str, default: Callable[[], dict], on_error: Callable[[str], None]):
        self.path, self._default, self._on_error = path, default, on_error
        self._data, self._mtime = default(), None

    def data(self) -> dict:
        try:
            mtime = os.stat(self.path).st_mtime_ns
        except FileNotFoundError:
            if self._mtime is not None:          # deleted by hand: back to empty
                self._data, self._mtime = self._default(), None
            return self._data
        if mtime != self._mtime:
            try:
                with open(self.path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ValueError("the top level must be an object { ... }")
                self._data = loaded
            except Exception as e:
                self._on_error(f"{os.path.basename(self.path)}: {e} (the previous version stays active)")
            self._mtime = mtime
        return self._data

    def save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        self._data, self._mtime = data, os.stat(self.path).st_mtime_ns

    @property
    def exists(self) -> bool:
        return os.path.isfile(self.path)


def _entry(uid: int, name: str | None, by: int | None) -> dict:
    return {"id": uid, "name": name or "", "added_by": by, "added_at": time.strftime("%Y-%m-%dT%H:%M")}


def _ids(entries) -> set:
    out = set()
    for e in entries or []:
        try:
            out.add(int(e["id"] if isinstance(e, dict) else e))   # plain numbers are accepted in hand edits too
        except (KeyError, TypeError, ValueError):
            pass
    return out


class UserList:
    """A list of users inside one JSON file (key = "users", "owners" or "sudo")."""

    def __init__(self, file: JsonFile, key: str, extra: Callable[[], dict] = dict):
        self.file, self.key, self.extra = file, key, extra

    def ids(self) -> set:
        return _ids(self.file.data().get(self.key))

    def entries(self) -> list[dict]:
        return [e if isinstance(e, dict) else {"id": int(e), "name": ""} for e in self.file.data().get(self.key) or []]

    def add(self, uid: int, name: str | None, by: int | None) -> bool:
        if uid in self.ids():
            return False
        data = {**self.extra(), **self.file.data()}
        items = sorted(self.entries() + [_entry(uid, name, by)], key=lambda e: int(e["id"]))
        self.file.save({**data, self.key: items})
        return True

    def remove(self, uid: int) -> bool:
        if uid not in self.ids():
            return False
        data = dict(self.file.data())
        data[self.key] = [e for e in self.entries() if int(e["id"]) != uid]
        self.file.save(data)
        return True


class AclService:
    def __init__(self, data_dir: str, root_owners, on_error: Callable[[str], None] | None = None):
        self.dir = os.path.join(data_dir, "acl")
        self.groups_dir = os.path.join(self.dir, "groups")
        os.makedirs(self.groups_dir, exist_ok=True)
        os.chmod(self.dir, 0o700)
        self._on_error = on_error or (lambda text: log.warning("acl: %s", text))
        self.root = set(root_owners)
        users = lambda: {"users": []}  # noqa: E731
        self.bot_owners = UserList(self._file("bot_owners.json", users), "users")
        self.global_sudo = UserList(self._file("global_sudo.json", users), "users")
        self._targets = self._file("dm_targets.json", dict)
        self._groups: dict[int, JsonFile] = {}

    def _file(self, name: str, default) -> JsonFile:
        return JsonFile(os.path.join(self.dir, name), default, lambda text: self._on_error(text))

    def add_root(self, uid: int) -> None:
        self.root.add(uid)

    # ---- per group ----
    def _group(self, chat_id: int) -> JsonFile:
        file = self._groups.get(chat_id)
        if file is None:
            file = self._groups[chat_id] = self._file(os.path.join("groups", f"{chat_id}.json"), lambda: {"title": "", "owners": [], "sudo": []})
        return file

    def group_owners(self, chat_id: int) -> UserList:
        return UserList(self._group(chat_id), "owners", lambda: {"title": "", "owners": [], "sudo": []})

    def group_sudo(self, chat_id: int) -> UserList:
        return UserList(self._group(chat_id), "sudo", lambda: {"title": "", "owners": [], "sudo": []})

    def set_title(self, chat_id: int, title: str) -> None:
        file = self._group(chat_id)
        if file.exists and file.data().get("title") != title:
            file.save({**file.data(), "title": title})

    def archive(self, chat_id: int) -> None:
        """The account left the group: keep its file under groups/left/ instead of losing it."""
        src = os.path.join(self.groups_dir, f"{chat_id}.json")
        if os.path.isfile(src):
            os.makedirs(os.path.join(self.groups_dir, "left"), exist_ok=True)
            os.replace(src, os.path.join(self.groups_dir, "left", f"{chat_id}.json"))
        self._groups.pop(chat_id, None)

    def known_groups(self) -> list[int]:
        out = []
        for name in os.listdir(self.groups_dir):
            if os.path.isfile(os.path.join(self.groups_dir, name)) and name.endswith(".json") and name[:-5].lstrip("-").isdigit():
                out.append(int(name[:-5]))
        return out

    # ---- questions ----
    def is_root(self, uid: int) -> bool:
        return uid in self.root

    def is_bot_owner(self, uid: int) -> bool:
        return uid in self.root or uid in self.bot_owners.ids()

    def role(self, uid: int | None, chat_id: int | None) -> Role | None:
        """Highest role of the user in that group (chat_id None = no group context: only bot-wide roles)."""
        if uid is None:
            return None
        if self.is_bot_owner(uid):
            return Role.BOT_OWNER
        if chat_id is not None and chat_id < 0:
            if uid in self.group_owners(chat_id).ids():
                return Role.GROUP_OWNER
            if uid in self.group_sudo(chat_id).ids():
                return Role.SUDO
        if uid in self.global_sudo.ids():
            return Role.SUDO
        return None

    def has_any_role(self, uid: int | None) -> bool:
        if uid is None:
            return False
        return self.is_bot_owner(uid) or uid in self.global_sudo.ids() or bool(self.group_roles(uid))

    def group_roles(self, uid: int) -> dict[int, Role]:
        """Groups where the user is owner / SUDO by the group files (global roles not included)."""
        out = {}
        for chat_id in self.known_groups():
            if uid in self.group_owners(chat_id).ids():
                out[chat_id] = Role.GROUP_OWNER
            elif uid in self.group_sudo(chat_id).ids():
                out[chat_id] = Role.SUDO
        return out

    # ---- /use choice ----
    def target(self, uid: int) -> int | None:
        value = self._targets.data().get(str(uid))
        return int(value) if isinstance(value, int) or (isinstance(value, str) and value.lstrip("-").isdigit()) else None

    def set_target(self, uid: int, chat_id: int | None) -> None:
        data = dict(self._targets.data())
        if chat_id is None:
            data.pop(str(uid), None)
        else:
            data[str(uid)] = chat_id
        self._targets.save(data)

    # ---- migration of SUDO_USERS from .env (once) ----
    def migrate_legacy_sudo(self, ids) -> int:
        if self.global_sudo.file.exists or not ids:
            return 0
        self.global_sudo.file.save({"users": [_entry(i, "", None) for i in sorted(set(ids))]})
        return len(set(ids))
