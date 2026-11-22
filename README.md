# Telegram Video Player Bot

Plays video and audio in Telegram **group voice chats** from a normal **Telegram user account** (no bot token).
Based on [AsmSafone/VideoPlayerBot](https://github.com/AsmSafone/VideoPlayerBot), rebuilt on Kurigram, py-tgcalls 3 and yt-dlp.
See [manual.md](manual.md) for the full guide.

## Features

- Plays **songs by name**: `/play daft punk get lucky` finds it on YouTube and plays the audio.
- Plays YouTube videos, YouTube live streams, live radio / direct links and Telegram audio / video files.
- `/play` detects audio or video itself; `/play video <name or link>` forces video.
- Now-playing card with title, artwork, play state and a progress bar (`01:23 ━━●─── 04:56`). If something removes the card message, playback just goes on without it.
- Plays started from the **private chat** (`/play <number>`) post and update their card there, not in the group.
- **Survives lost voice calls**: when Telegram drops the connection the bot rejoins and continues from the same position; why a call was lost is written to the log.
- `/lyrics` plays a song as a **video with synced lyrics** (from [LRCLIB](https://lrclib.net)), Persian / right-to-left text included.
- `/jump` forward / back in time, `/loop` repeat, `/vol` volume, `/delete` clean up the bot's messages.
- `/download` sends the song (mp3) or video (mp4) as a file in the chat.
- All command names are configurable in `commandmapper.py`.
- Optional private-message auto reply (PM guard).

## Commands

Work with `/`, `!` or `.`, only from the logged-in account and the `SUDO_USERS`.

```sh
/play <song name or link>        - Play audio (links: audio or video is detected)
/play video <name or link>       - Play as video
/play audio <name or link>       - Force audio only
reply to audio/video + /play     - Play that file
(while something plays, /play and /stream add to the queue, MAX_QUEUE in .env, default 10)
/stream                          - Same as /play video
/pause                           - Pause the current stream
/resume                          - Resume the paused stream
/next (or /skip)                 - Skip to the next queued item
/queue                           - Show what is playing and what is queued
/jump <time>                     - Move in the media: 30 / +30s / +5m go ahead, -10 / -40s / -2m go back (s, m, h)
/loop                            - Repeat the current media (send again to stop)
/vol <1-200>                     - Voice chat volume (100 = normal)
/lyrics <song name or link>      - Play the song as a video with its synced lyrics (plain playback if none are found)
/lyrics                          - Turn the song that plays now into a lyrics video
/delete                          - Delete the bot's messages (reply to one to delete only that message)
/end                             - Stop streaming, clear the queue & leave the voice chat
/download <song name or link>    - Send the song as an mp3 file
/download video <name or link>   - Send the video as an mp4 file
/restart                         - Restart the app
/list                            - Owners only, in private chat: numbered list of joined groups
/play <number> [link]            - Owners only, in private chat: reply to a link / audio / video (or add a link) to play it in the group with that number of /list (the card is shown in the private chat)
/id                              - Everyone, private chat only: replies with the sender's Telegram number
/admins, /promote, /demote       - Owners only, in groups and private chat: list / add / remove SUDO users (saved to .env)
/join <invite link or @username> - Owners only: join that group
/leave <number>                  - Owners only: leave that group (inside a group without a number: leave it now)
/help, /start, /about            - Info
```

## Setup

Needs Debian/Ubuntu, Python 3.12 (installed by the script), ffmpeg (with libass) plus a Persian-capable font (both installed by the script) and a Telegram account with API credentials
from <https://my.telegram.org> (*API development tools*).

```sh
git clone https://github.com/AsmSafone/VideoPlayerBot && cd VideoPlayerBot   # or copy your own checkout
./setup.sh                          # ffmpeg, fonts, uv, Python 3.12 venv, dependencies, .env from .env.sample
nano .env                           # API_ID, API_HASH, SUDO_USERS ...
.venv/bin/python login.py           # once: log in with the code Telegram sends you
.venv/bin/python main.py            # run (or install the systemd service, see manual.md)
```

Add the account to a group, start a voice chat there, and send `/play <song>`.
Run only **one** program per Telegram session: a second client with the same session silently stops receiving messages.

## Config (.env)

| Variable | Meaning |
|---|---|
| `API_ID`, `API_HASH` | required, from my.telegram.org |
| `PHONE_NUMBER` | optional, otherwise asked at login |
| `SUDO_USERS` | user IDs (space separated) allowed to run commands besides the account itself |
| `OWNER_USERS` | user IDs (space separated) that may also manage the groups (`/list`, `/join`, `/leave`) besides the account itself |
| `VIDEO_QUALITY` | `SD_360p` (default), `SD_480p`, `HD_720p`, `FHD_1080p` |
| `DOWNLOAD_MAX_MB` | max file size for streaming and `/download` (default 1000) |
| `SEARCH_MAX_MINUTES` | name searches skip longer results (default 15) |
| `REPLY_MESSAGE` | optional auto reply to private messages |
| `SESSION_NAME`, `SESSION_DIR` | session file name / folder (default `user`, `sessions`) |
| `MAX_QUEUE` | items that may wait in the queue of one group (default 10) |
| `PROGRESS_EVERY` | seconds between progress bar updates (default 10) |
| `LYRICS_MAX_MINUTES` | longer songs play without lyrics (default 15) |
| `LYRICS_TOLERANCE` | allowed length difference in seconds between the song and the found lyrics (default 10) |
| `LYRICS_FONT` | font of the lyrics (default `Vazirmatn`, Latin + Persian/Arabic) |
| `LRCLIB_URL` | lyrics source, only change it for a self-hosted LRCLIB (default `https://lrclib.net/api`) |

## Docker

```sh
docker build -t videoplayerbot .
docker run -it --rm -v vpb-sessions:/app/sessions --env-file .env videoplayerbot python login.py   # once
docker run -d --restart unless-stopped -v vpb-sessions:/app/sessions --env-file .env videoplayerbot
```

## License
```sh
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
```

## Credits

- [Asm Safone](https://github.com/AsmSafone) for the original [VideoPlayerBot](https://github.com/AsmSafone/VideoPlayerBot)
- [Dan](https://github.com/delivrance) for [Pyrogram](https://github.com/pyrogram/pyrogram) and the [Kurigram](https://github.com/KurimuzonAkuma/kurigram) fork
- [MarshalX](https://github.com/MarshalX) and [Laky-64](https://github.com/Laky-64) for pytgcalls / ntgcalls
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) contributors
