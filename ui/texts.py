"""User-facing texts built from the command names of commandmapper.py."""

from commandmapper import tag, alt, mode_alt, mode_label as mode
from core.acl import Role

START = (f"👋🏻 **Video Player is alive!** ✨\n\nI play live links, radios, YouTube videos, songs by name and Telegram audio / "
         f"video files in the voice chats of your groups. Send {tag('help')} to see the commands.")
ABOUT = "💡-- **Information**:-- \n\nThis app plays audio and video in Telegram group voice chats from a normal user account."
USAGE_PLAY = (f"__Send a song name or a link (YouTube, live stream, radio, direct file), or reply to an audio / video "
              f"file with__ {tag('play')}. __See__ {tag('help')} __for everything else.__")


def _line(key: str, args: str, text: str) -> str:
    return f"• {tag(key)}{alt(key)}{' `' + args + '`' if args else ''} — {text}"


PLAYBACK = [
    _line("play", "<song name>", "search on YouTube and play it as audio"),
    _line("play", f"{mode('video')} <name or link>", "play as video"),
    _line("play", "<link>", "YouTube / live / direct link, audio or video is detected"),
    f"• reply to an audio / video with {tag('play')} — play that file; {tag('play')} `{mode('audio')} …` forces audio",
    _line("stream", "", f"same as {tag('play')} `{mode('video')}`"),
    _line("lyrics", "<song>", "play the song as a video with synced lyrics (Persian works); alone: the song that plays now"),
    _line("pause", "", "pause"), _line("resume", "", "resume"),
    _line("next", "", "skip to the next queued item"), _line("queue", "", "what plays and what waits"),
    _line("jump", "<30 | +2m | -10 | 1:30>", "move in the media (s / m / h; mm:ss goes to that time)"),
    _line("loop", "[on | off]", "repeat the current media"),
    _line("vol", "<1-200>", "volume (100 = normal)"),
    _line("delete", "", "delete the bot's messages here (or only the replied one)"),
    _line("end", "", "stop, clear the queue and leave the voice chat"),
    _line("download", "<name or link>", f"send the song as a file (`{mode('video')}` first for the video)"),
    "• While something plays, new media joins the queue.",
]
GROUP_OWNER = [
    _line("sudolist", "", "SUDO users of this group"),
    _line("addsudo", "<reply | id | @username>", "add a SUDO user to this group"),
    _line("delsudo", "<reply | number | id | @username>", "remove a SUDO user of this group"),
    _line("owners", "", "owners of this group"),
]
BOT_OWNER = [
    _line("addowner", "<reply | id | @username>", "add a group owner"), _line("delowner", "<…>", "remove a group owner"),
    _line("gsudolist", "", "global SUDO users"), _line("gaddsudo", "<…>", "add a global SUDO user (every group)"),
    _line("gdelsudo", "<…>", "remove a global SUDO user"),
    _line("botowners", "", "bot owners"), _line("addbotowner", "<…>", "root owners only: add a bot owner"),
    _line("delbotowner", "<…>", "root owners only: remove a bot owner"),
    _line("join", "<invite link | @username>", "join a group"), _line("leave", "[number]", "leave a group"),
    _line("restart", "", "restart the app"),
]
GENERAL = [
    _line("list", "", "your groups, numbered"),
    _line("use", "<number>", "private chat: the group your commands go to"),
    _line("perms", "", "your role"), _line("id", "", "your Telegram ID (private chat, open to everyone)"),
    _line("about", "", "about this app"), _line("help", "", "this list"),
    f"• Words after {tag('play')}: `{mode('video')}`{mode_alt('video')} · `{mode('audio')}`{mode_alt('audio')}",
]
DM_NOTE = (f"🔒 **Private chat:** every command works here too and goes to the group chosen with {tag('use')}. "
           f"Name another group for one command with `#<number>`: {tag('pause')} `#2` · {tag('vol')} `#2 80` · "
           f"{tag('play')} `2 <song>`.")


def help_text(role: Role | None, private: bool) -> str:
    parts = ["🛠 **Commands** (`/`, `!` or `.` work)", "", "🎧 **Playback**", *PLAYBACK]
    if role and role >= Role.GROUP_OWNER:
        parts += ["", "👥 **Group owners**", *GROUP_OWNER]
    if role and role >= Role.BOT_OWNER:
        parts += ["", "👑 **Bot owners**", *BOT_OWNER]
    parts += ["", "ℹ️ **General**", *GENERAL]
    if private:
        parts += ["", DM_NOTE]
    return "\n".join(parts)
