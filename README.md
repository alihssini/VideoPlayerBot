# Telegram Video Player Bot

Plays YouTube videos, songs by name, live streams, radios and Telegram audio / video files in the **voice chats of your groups** — from a normal Telegram **user account** (no bot token).

## Features

- `/play <song name | link>` or reply to a file — audio or video is detected; a queue when something plays already
- YouTube playlists (first videos up to the queue limit), live streams, direct links, radios
- Rendered now-playing card (artwork, title, artist, kind, length; Persian / Arabic text right-to-left) with progress bar, who requested it and what comes next
- Optional buttons under the card (pause, next, stop, loop, volume, queue) via a real bot (`BOT_TOKEN`)
- Pause / resume / next / jump (`+30s`, `-2m`, `1:30`) / loop / volume / queue editing (remove, move, shuffle, clear)
- `/lyrics` — the song as a video with synced lyrics (LRCLIB), Persian works
- `/download` — the song (mp3) or video (mp4) as a file
- **Three roles**, editable at runtime without restart: bot owners · group owners (per group) · SUDO users (per group or global), stored as small JSON files in `data/acl/`
- **Every command works in the private chat** too, for the group chosen with `/use` or `#<number>`
- Survives lost voice calls (rejoins where it stopped), leaves empty voice chats, continues what played after a restart
- Command names and aliases (English + Persian) in one file: `commandmapper.py`

## Commands (short)

| | |
|---|---|
| Playback (SUDO and up) | `/play` `/stream` `/lyrics` `/pause` `/resume` `/next` `/queue` `/remove` `/move` `/shuffle` `/clear` `/now` `/jump` `/loop` `/vol` `/delete` `/end` `/download` |
| Group owners | `/admins` `/promote` `/demote` `/owners` |
| Bot owners | `/addowner` `/delowner` `/gadmins` `/gpromote` `/gdemote` `/botowners` `/addbotowner`* `/delbotowner`* `/join` `/leave` `/status` `/restart` (*root owners only) |
| Everyone with a role | `/list` `/use` `/perms` `/help` `/start` `/about` · `/id` is open to everybody in private chat |

`/help` shows exactly the commands the sender may use. Details: **[manual.md](manual.md)**.

## Setup

```bash
./setup.sh --with-service          # ffmpeg, fonts, Python 3.12 venv, dependencies, systemd unit
nano .env                          # API_ID, API_HASH (https://my.telegram.org), OWNER_USERS
.venv/bin/python login.py          # once: log in with the code Telegram sends you
systemctl start videoplayerbot
```

## Docker

```bash
docker build -t videoplayerbot .
docker run -it --rm -v vpb-sessions:/app/sessions -v vpb-data:/app/data --env-file .env videoplayerbot python login.py
docker run -d --name vpb -v vpb-sessions:/app/sessions -v vpb-data:/app/data --env-file .env videoplayerbot
```

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE). Based on VideoPlayerBot by Asm Safone.

## Credits

[Asm Safone](https://github.com/AsmSafone) (original project) · [py-tgcalls](https://github.com/pytgcalls/pytgcalls) · [kurigram](https://github.com/KurimuzonAkuma/pyrogram) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [LRCLIB](https://lrclib.net)
