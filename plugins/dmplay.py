"""
Owner-only: play in a group from the private chat.

Send the bot a link, an audio or a video file in private chat, then reply to that message with
/play <number> (the number from /list), or send /play <number> <link or song name> directly.
The media is played (or queued, when the group already plays something) in that group.
"""

from pyrogram import filters, enums
from helpers.user import User
from commandmapper import names, tag
from config import COMMAND_PREFIXES
from helpers.decorators import owner_only
from plugins.owner import SNAPSHOT
from plugins.stream import handle_play

PLAIN = enums.ParseMode.DISABLED


def _target(token: str):
    """Number of the list command (or the id of a listed group) -> that group, or None."""
    try:
        number = int(token)
    except ValueError:
        return None
    if 1 <= number <= len(SNAPSHOT):
        return SNAPSHOT[number - 1]
    for entry in SNAPSHOT:
        if entry["id"] == number:
            return entry
    return None


async def _dm_play(client, m, force=None):
    command = tag("stream") if force else tag("play")
    list_cmd = tag("list")
    args = m.command[1:]
    if not args:
        return await m.reply_text(
            f"❗ __Send me a link, audio or video, then reply to it with__ {command} `<group number>`\n"
            f"__or send__ {command} `<group number> <link or song name>`\n\n__Numbers come from__ {list_cmd}"
        )
    if not SNAPSHOT:
        return await m.reply_text(f"❗ __Send {list_cmd} first, to get the group numbers.__")
    entry = _target(args[0])
    if entry is None:
        return await m.reply_text(f"❌ **There is no group number** `{args[0]}`**.** __The list has {len(SNAPSHOT)}; send {list_cmd} to refresh it.__")
    if entry["left"]:
        return await m.reply_text("❌ **This account has left that group.** __Send the list command again.__")
    await handle_play(client, m, force, target={"id": entry["id"], "title": entry["title"]}, args=args[1:])


@User.on_message(filters.command(names("play"), prefixes=COMMAND_PREFIXES) & filters.private, group=-1)
@owner_only
async def dm_play(client, m):
    await _dm_play(client, m)


@User.on_message(filters.command(names("stream"), prefixes=COMMAND_PREFIXES) & filters.private, group=-1)
@owner_only
async def dm_stream(client, m):
    await _dm_play(client, m, "video")
