"""
Owner-only commands to manage the SUDO users: list, add, remove.
Owners are the OWNER_USERS of .env plus the logged-in account itself.
Works in groups and in private chat. Changes apply at once and are written to .env.
"""

import os
import re
import shutil
import time
import tempfile
from pyrogram import filters, enums
from helpers.user import User
from commandmapper import names, tag
from config import COMMAND_PREFIXES, SUDO_USERS
from helpers.decorators import owner_only

PLAIN = enums.ParseMode.DISABLED  # names may contain markdown characters
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
BACKUP_DIR = os.path.expanduser("~/backups")
_backed_up = False


def _display(user, uid):
    if user is None:
        return f"{uid} (name not available)"
    name = " ".join(x for x in (user.first_name, user.last_name) if x) or "no name"
    handle = f" @{user.username}" if user.username else ""
    return f"{name}{handle} [{uid}]"


async def _lookup(client, ref):
    """int id or @username -> pyrogram User, or None when Telegram does not know that account."""
    try:
        return await client.get_users(ref)
    except Exception:
        return None


async def _resolve(client, m, index_ok=False):
    """The target of the command: replied message's sender, or the id / @username after the command.
    Returns (user_id, user_or_None, error_text_or_None)."""
    if m.reply_to_message and m.reply_to_message.from_user:
        user = m.reply_to_message.from_user
        return user.id, user, None
    arg = m.command[1].strip() if len(m.command) > 1 else ""
    if not arg:
        return None, None, "missing"
    if re.fullmatch(r"-?\d+", arg):
        uid = int(arg)
        if index_ok and uid not in SUDO_USERS and 1 <= uid <= len(SUDO_USERS):
            uid = SUDO_USERS[uid - 1]
        return uid, await _lookup(client, uid), None
    name = arg.lstrip("@")
    if re.fullmatch(r"[A-Za-z]\w{3,}", name):
        user = await _lookup(client, name)
        if not user:
            return None, None, f"❌ **No account with the username @{name} was found.**"
        return user.id, user, None
    return None, None, "missing"


def _save():
    """Writes SUDO_USERS to .env (one backup per run of the app, atomic replace)."""
    global _backed_up
    value = " ".join(str(x) for x in SUDO_USERS)
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    if not _backed_up and os.path.isfile(ENV_FILE):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(ENV_FILE, os.path.join(BACKUP_DIR, f".env.{time.strftime('%Y%m%d-%H%M%S')}.bak"))
        _backed_up = True
    key = None
    for i, line in enumerate(lines):
        found = re.match(r"\s*(SUDO_USERS|SUDOERS)\s*=", line)
        if found:
            key = found.group(1)
            lines[i] = f"{key}={value}"
            break
    if key is None:
        lines.append(f"SUDO_USERS={value}")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ENV_FILE), prefix=".env.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        shutil.copymode(ENV_FILE, tmp)
    except FileNotFoundError:
        os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_FILE)


async def _say(m, text, **kwargs):
    try:
        return await m.reply_text(text, **kwargs)
    except Exception:
        return None


@User.on_message(filters.command(names("sudolist"), prefixes=COMMAND_PREFIXES), group=-1)
@owner_only
async def sudo_list(client, m):
    if not SUDO_USERS:
        return await _say(m, "📭 There are no SUDO users.", parse_mode=PLAIN)
    lines = []
    for i, uid in enumerate(SUDO_USERS, 1):
        lines.append(f"{i}. {_display(await _lookup(client, uid), uid)}")
    text = f"👥 SUDO users ({len(lines)}):\n\n" + "\n".join(lines)
    text += f"\n\n{COMMAND_PREFIXES[0]}{names('addsudo')[0]} <id | @username> or reply · {COMMAND_PREFIXES[0]}{names('delsudo')[0]} <number | id | @username> or reply"
    for start in range(0, len(text), 3800):
        await _say(m, text[start:start + 3800], parse_mode=PLAIN)


@User.on_message(filters.command(names("addsudo"), prefixes=COMMAND_PREFIXES), group=-1)
@owner_only
async def sudo_add(client, m):
    uid, user, error = await _resolve(client, m)
    if error == "missing":
        return await _say(m, f"❗ __Reply to a user, or send the id / @username:__ {tag('addsudo')} `@username` · {tag('addsudo')} `123456789`")
    if error:
        return await _say(m, error)
    if user is not None and user.is_bot:
        return await _say(m, "❌ **That is a bot account.**")
    me = await client.get_me()
    if uid == me.id:
        return await _say(m, "ℹ️ **That is this account itself, it always has full access.**")
    if uid in SUDO_USERS:
        return await _say(m, f"ℹ️ Already a SUDO user: {_display(user, uid)}", parse_mode=PLAIN)
    if user is None:
        return await _say(m, f"❌ **Telegram does not know an account with the id {uid}.** Send its @username, or reply to one of its messages.")
    SUDO_USERS.append(uid)
    try:
        _save()
    except Exception as e:
        SUDO_USERS.remove(uid)
        return await _say(m, f"❌ **Could not save .env, nothing changed !** \n\nError: `{type(e).__name__}: {e}`")
    await _say(m, f"✅ Added SUDO user: {_display(user, uid)}", parse_mode=PLAIN)


@User.on_message(filters.command(names("delsudo"), prefixes=COMMAND_PREFIXES), group=-1)
@owner_only
async def sudo_del(client, m):
    uid, user, error = await _resolve(client, m, index_ok=True)
    if error == "missing":
        return await _say(m, f"❗ __Reply to a user, or send the number from {tag('sudolist')}, the id or the @username:__ {tag('delsudo')} `2`")
    if error:
        return await _say(m, error)
    if uid not in SUDO_USERS:
        return await _say(m, f"ℹ️ Not a SUDO user: {_display(user, uid)}", parse_mode=PLAIN)
    SUDO_USERS.remove(uid)
    try:
        _save()
    except Exception as e:
        SUDO_USERS.append(uid)
        return await _say(m, f"❌ **Could not save .env, nothing changed !** \n\nError: `{type(e).__name__}: {e}`")
    await _say(m, f"🗑 Removed SUDO user: {_display(user, uid)}", parse_mode=PLAIN)
