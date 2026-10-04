# Telegram Video Player Bot

Plays video and audio in Telegram **group voice chats** from a normal **Telegram user account** (no bot token).
Based on [AsmSafone/VideoPlayerBot](https://github.com/AsmSafone/VideoPlayerBot), rebuilt on Kurigram, py-tgcalls 3 and yt-dlp.
See [manual.md](manual.md) for the full guide.

## Features

- Plays **songs by name**: `/play daft punk get lucky` finds it on YouTube and plays the audio.
- Plays YouTube videos, YouTube live streams, live radio / direct links and Telegram audio / video files.
- `/play` detects audio or video itself; `/play video <name or link>` forces video.
- Now-playing card with title, artwork, play state and the available commands.
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
/stream                          - Same as /play video
/pause                           - Pause the current stream
/resume                          - Resume the paused stream
/end                             - Stop streaming & leave the voice chat
/download <song name or link>    - Send the song as an mp3 file
/download video <name or link>   - Send the video as an mp4 file
/restart                         - Restart the app
/help, /start, /about            - Info
```

## Setup

Needs Debian/Ubuntu, Python 3.12 (installed by the script), ffmpeg and a Telegram account with API credentials
from <https://my.telegram.org> (*API development tools*).

```sh
git clone https://github.com/AsmSafone/VideoPlayerBot && cd VideoPlayerBot   # or copy your own checkout
./setup.sh                          # ffmpeg, uv, Python 3.12 venv, dependencies, .env from .env.sample
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
| `VIDEO_QUALITY` | `SD_360p` (default), `SD_480p`, `HD_720p`, `FHD_1080p` |
| `DOWNLOAD_MAX_MB` | max file size for streaming and `/download` (default 1000) |
| `SEARCH_MAX_MINUTES` | name searches skip longer results (default 15) |
| `REPLY_MESSAGE` | optional auto reply to private messages |

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
