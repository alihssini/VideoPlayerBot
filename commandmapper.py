"""Command mapper: every command of the bot and the name(s) it answers to.

Edit the lists below to rename commands or add aliases, then restart the app.
 - The bot listens ONLY to the names listed here (with the prefixes from config.COMMAND_PREFIXES).
 - The FIRST name of each list is the one shown to people (now-playing card, /help, usage hints).
 - Names must be lowercase, without spaces and without the prefix, and unique across all commands.

Example: "play": ["p", "play", "spiel"] -> /p, /play and /spiel all start playback, and /p is what the cards show.
"""

import re
from config import COMMAND_PREFIXES

COMMANDS = {
    "play":      ["play", "پخش"],       # play a link / replied audio or video (audio or video is detected)
    "stream":    ["stream", "استریم"],     # same as play, but forces video
    "pause":     ["pause", "توقف"],      # pause the current stream
    "resume":    ["resume", "ادامه"],     # resume a paused stream
    "end":       ["end", "اتمام"],  # stop the stream and leave the voice chat
    "download":  ["download", "دانلود"],  # download the song / video and send the file in chat
    "next":      ["next", "skip", "بعدی"],  # skip to the next queued item
    "queue":     ["queue", "صف"],         # show what plays and what waits
    "jump":      ["jump", "seek", "پرش"],    # move in the media: /jump 30 or /jump +30s (ahead), /jump -10 (back), units s / m / h
    "lyrics":    ["lyrics", "lyric", "متن", "شعر"],  # play a song as a video with its synced lyrics: /lyrics <song name>, or /lyrics alone for the song that plays now
    "loop":      ["loop", "repeat", "تکرار"],  # repeat the current media: /loop (on / off toggle), /loop on, /loop off
    "vol":       ["vol", "volume", "صدا"],   # voice chat volume of the bot: /vol 80 (1-200, 100 = normal)
    "delete":    ["delete", "del", "حذف"],   # delete the bot's messages (all of them, or only the replied one)
    "restart":   ["restart", "ریستارت"],    # restart the app
    "list":      ["list", "لیست"],       # owners only, in private chat: numbered list of the joined groups
    "join":      ["join", "ورود"],       # owners only: join a group by invite link or @username
    "leave":     ["leave", "خروج"],      # owners only: leave the group with that list number, or the current group when sent inside one
    "sudolist":  ["admins", "ادمینها"],   # owners only: numbered list of the SUDO users (names fetched from Telegram)
    "addsudo":   ["promote", "ارتقا", "ترفیع"],   # owners only: add a SUDO user by reply, id or @username
    "delsudo":   ["demote", "عزل"],    # owners only: remove a SUDO user by reply, list number, id or @username
    "id":        ["id", "آیدی"],          # anyone, private chat only: replies with the sender's Telegram number
    "start":     ["start", "استارت"],      # short intro text
    "help":      ["help", "راهنما"],       # list of commands
    "about":     ["about", "درباره"],      # information about the app
}

# Words that can follow the play command to choose the kind: "/play video <name or link>".
# Same rules as above (first name is the displayed one).
MODES = {
    "audio": ["audio", "موزیک"],  # "/play audio <name or link>": audio only
    "video": ["video", "ویدیو"],  # "/play video <name or link>": video
}


def _validate() -> None:
    seen = {}
    for key, names in COMMANDS.items():
        if not names:
            raise SystemExit(f"[ERROR] - commandmapper: '{key}' needs at least one name")
        for name in names:
            if not re.fullmatch(r"\w+", name) or name != name.lower():
                raise SystemExit(f"[ERROR] - commandmapper: '{name}' ({key}) must be lowercase letters/digits/_ only")
            if name in seen:
                raise SystemExit(f"[ERROR] - commandmapper: '{name}' is used by both '{seen[name]}' and '{key}'")
            seen[name] = key
    words = {}
    for mode, names_ in MODES.items():
        for name in names_:
            if not re.fullmatch(r"\w+", name) or name != name.lower():
                raise SystemExit(f"[ERROR] - commandmapper: mode word '{name}' ({mode}) must be lowercase letters/digits/_ only")
            if name in words:
                raise SystemExit(f"[ERROR] - commandmapper: mode word '{name}' is used by both '{words[name]}' and '{mode}'")
            words[name] = mode


_validate()


def names(key: str) -> list:
    """All names that trigger this command (for pyrogram filters.command)."""
    return list(COMMANDS[key])


def label(key: str) -> str:
    """The command as shown to people, e.g. /play (first name, first prefix)."""
    return COMMAND_PREFIXES[0] + COMMANDS[key][0]


def tag(key: str) -> str:
    """label() wrapped in markdown code, e.g. `/play`."""
    return f"`{label(key)}`"


def alt(key: str) -> str:
    """The other names of a command for the help text, e.g. " (also `/skip`, `/بعدی`)", or "" when it has none."""
    others = COMMANDS[key][1:]
    if not others:
        return ""
    return " (also " + ", ".join(f"`{COMMAND_PREFIXES[0]}{n}`" for n in others) + ")"


def mode_alt(mode: str) -> str:
    """Other words for a mode for the help text, e.g. " (also `ویدیو`)", or ""."""
    others = MODES[mode][1:]
    return " (also " + ", ".join(f"`{n}`" for n in others) + ")" if others else ""


def mode_of(word: str):
    """"audio" / "video" if the word is one of the mapped mode words, else None."""
    word = word.lower()
    for mode, names_ in MODES.items():
        if word in names_:
            return mode
    return None


def mode_label(mode: str) -> str:
    """The displayed word for a mode, e.g. video."""
    return MODES[mode][0]
