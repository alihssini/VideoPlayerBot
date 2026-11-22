# VideoPlayerBot – Manual (user-account edition)

Streams audio / video into Telegram group **voice chats** from a normal **Telegram user account**
(no bot token), searches songs by name, and sends audio / video files into chats.
Stack: Kurigram (Pyrogram fork) + py-tgcalls 3 / ntgcalls + yt-dlp + ffmpeg, Python 3.12.

> Using a user account for automation can get the account restricted by Telegram.
> A spare account is safer than your main one.

---

## 1. Requirements

- Debian/Ubuntu (tested: Debian 13 LXC container), root or sudo
- **Resources:** 1 CPU core / 512 MB RAM is enough at 360p. For 720p use 2 cores / 2 GB RAM.
- Internet access, ~2 GB free disk (videos are downloaded temporarily)
- A Telegram account and API credentials from <https://my.telegram.org> → *API development tools*
  (gives you `API_ID` and `API_HASH`)

## 2. Install

```bash
cd /root
# get the code: unpack a backup (creates ./VideoPlayerBot) or clone/copy the repository
mkdir -p /root/VideoPlayerBot && tar -xzf VideoPlayerBot-*/code.tar.gz -C /root/VideoPlayerBot   # a backup made as in section 10
cd /root/VideoPlayerBot

# installs ffmpeg, uv, a Python 3.12 virtualenv (.venv), all dependencies, and creates .env from .env.sample
./setup.sh
```

`setup.sh` runs `apt-get install ffmpeg git curl fontconfig fonts-dejavu-core fonts-vazirmatn` (the font is downloaded into `assets/fonts` when the package does not exist), installs `uv`, creates `.venv` (Python 3.12) and runs
`uv pip install -r requirements.txt` (kurigram, py-tgcalls, tgcrypto, python-dotenv, yt-dlp[default], deno).
`deno` is needed by yt-dlp to solve YouTube JavaScript challenges; the app finds it in `.venv/bin` by itself.
Dependencies are pinned in `requirements.txt` (only yt-dlp has a minimum version, because YouTube changes often).

## 3. Configure

```bash
nano .env          # created from .env.sample by setup.sh
```

| Variable | Required | Meaning |
|---|---|---|
| `API_ID`, `API_HASH` | yes | from my.telegram.org |
| `PHONE_NUMBER` | no | e.g. `+49123456789`; if empty it is asked during login |
| `SUDO_USERS` | no | user IDs (space separated) that may control the bot besides the logged-in account |
| `OWNER_USERS` | no | user IDs (space separated) that may manage the bot's groups (`/list`, `/join`, `/leave`) besides the logged-in account |
| `VIDEO_QUALITY` | no | `SD_360p` (default), `SD_480p`, `HD_720p`, `FHD_1080p` – higher needs more CPU |
| `DOWNLOAD_MAX_MB` | no | refuse files bigger than this, for streaming and `/download` (default 1000) |
| `SEARCH_MAX_MINUTES` | no | name searches skip results longer than this (default 15) |
| `REPLY_MESSAGE` | no | optional text auto-reply to incoming private messages (empty = off) |
| `SESSION_NAME`, `SESSION_DIR` | no | session file name / folder (default `user`, `sessions`) |

Keys from older versions (`BOT_TOKEN`, `SESSION_STRING`, `PREFIX`) are **not used** any more
(`SUDOERS` is still accepted as a fallback for `SUDO_USERS`).

## 4. Login (once)

```bash
cd /root/VideoPlayerBot
.venv/bin/python login.py
```

1. Enter your phone number (international format) if it is not in `.env`.
2. Telegram sends a **login code** to your Telegram app (or SMS) – enter it.
3. Enter your 2FA password if you have one.
4. You see `[OK] - Logged in as ...`. The session is saved in `sessions/user.session`.

Keep `sessions/` private – it is a full login to the account.
**One session = one running app.** Never run a second program (another bot, a copy of this one, `login.py`)
with the same session file or string while the service runs: Telegram then delivers messages to only one of them
and the other one silently stops answering (see section 9).

## 5. Run

Foreground (for testing):

```bash
cd /root/VideoPlayerBot
.venv/bin/python main.py
```

As a service (recommended, starts automatically when the container/server boots):

```bash
cp deploy/videoplayerbot.service /etc/systemd/system/videoplayerbot.service
systemctl daemon-reload
systemctl enable --now videoplayerbot

systemctl status videoplayerbot            # state
journalctl -u videoplayerbot -f            # live logs  (add: | grep -v OpenH264 to hide codec noise)
systemctl restart videoplayerbot           # restart
systemctl stop videoplayerbot              # stop
```

The unit uses `/root/VideoPlayerBot` as working directory – edit the paths in the unit if you install elsewhere.
If the app runs in a Proxmox container, also set `pct set <id> --onboot 1` so the container starts with the host.

## 6. Use

Add the logged-in account to a group and **start a voice chat** there. Commands work with `/`, `!` or `.`
and only from the logged-in account itself and the `SUDO_USERS`:

| Command | Action |
|---|---|
| `/play <song name>` | search YouTube for the song and play it as **audio** |
| `/play video <name or link>` | search or open it and play it as **video** |
| `/play <link>` | YouTube link plays as video; other links are checked: with a video track → video, else audio |
| reply to an audio / video file with `/play` | play that file (audio or video is detected) |
| `/play audio <name or link>` | force audio only |
| `/stream` | same as `/play video` |
| `/pause`, `/resume` | pause / resume |
| `/next` (alias `/skip`) | skip to the next queued item |
| `/queue` | show what is playing and what waits in the queue |
| `/end` | stop, clear the queue and leave the voice chat |
| `/download <song name or link>` | send the song as an **mp3** file in the chat (works in groups and private chats) |
| `/download video <name or link>` | send the **mp4** video (max 720p) in the chat |
| `/restart` | restart the app |
| `/list` | **owners only**, in private chat: numbered list of the joined groups (fixed order until the next `/list`) |
| `/play <number>` / `/play <number> <link or song name>` | **owners only**, in private chat: send the bot a link, audio or video, reply to it with `/play <number>` (number of `/list`) and it plays in that group's voice chat; it is queued when the group already plays. `/stream <number>` forces video. The now-playing card is posted and updated in that private chat, the group gets none |
| `/join <invite link or @username>` | **owners only**: join that group |
| `/id` | **everyone**, private chat only: replies with the sender's Telegram number (also `/آیدی`) |
| `/admins` | **owners only**, in groups and private chat: numbered list of the SUDO users with names (also `/ادمینها`) |
| `/promote <id or @username>` (`/ارتقا`, `/ترفیع`) | **owners only**: add a SUDO user; or reply to the person's message with `/addsudo`. Applies at once and is saved to `.env` (`.env` backup in `~/backups`) |
| `/demote <number, id or @username>` (`/عزل`) | **owners only**: remove a SUDO user (number from `/admins`); or reply to the person's message |
| `/leave <number>` | **owners only**: leave the group with that number of `/list`; sent inside a group without a number it leaves that group at once |
| `/help`, `/start`, `/about` | info |

- `/play` posts a **now-playing card** with the title and a picture (track artwork or the video's thumbnail;
  the account's profile picture if there is none), the play state (▶️ Playing, ⏸ Paused, ⏹ Stopped, ✅ Finished)
  and a progress bar; the commands are listed by `/help`.
- If the card message gets removed (for example a moderation bot of the group deletes it), the bot logs it once
  and keeps playing without updating the card. Plays asked for from the private chat (`/play <number>`) post and
  update their card in that private chat instead of the group; queued items keep that.
- Songs found by name show `Artist - Title` on the card, without a link.
- **Queue:** while something plays, `/play` and `/stream` (name, link or replied file) add the new item to the
  queue instead of replacing the current one. When a stream ends, the next queued item starts by itself and gets its
  own card; after the last one the bot leaves the voice chat. `/next` skips the current item, `/queue` lists them,
  `/end` stops everything and clears the queue. Items that fail to start are skipped with a message.
  The queue is per group, kept in memory (lost on restart) and limited by `MAX_QUEUE` in `.env` (default 10).
  Queued YouTube videos are downloaded when they are added, so they use disk space until they are played.
- Name searches skip live streams and prefer results up to `SEARCH_MAX_MINUTES` minutes.
- YouTube videos are downloaded (max 720p, merged by yt-dlp) and then streamed; YouTube live streams
  and radio links are streamed directly. `/download` refuses live streams.

### Renaming commands – `commandmapper.py`

All command names (and the words `audio` / `video` after `/play`) are defined in `commandmapper.py`.
Each command has a list of names; the bot listens to all of them and shows the **first** one in cards and `/help`:

```python
"play": ["p", "play"],          # /p and /play both work, cards show /p
"end":  ["end", "stop"],
```

Names must be lowercase, without spaces and unique; otherwise the app refuses to start and tells you which one.
Restart the service after editing.

## 7. Temp files / disk

Temp files are deleted when a stream ends, at startup, and by a sweeper (every 30 min, files older than 6 h).
Files for `/download` are deleted right after they are sent. `DOWNLOAD_MAX_MB` limits single files.

## 8. Update

```bash
cd /root/VideoPlayerBot
. .venv/bin/activate
uv pip install -U "yt-dlp[default]"        # YouTube changes often – update yt-dlp first if YouTube breaks
systemctl restart videoplayerbot
```

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Service runs but the bot never reacts to commands (often after some idle time) | another program uses the **same Telegram session** (e.g. an old music bot). Stop it, then `systemctl restart videoplayerbot`. Check with `ps -eo pid,etime,cmd \| grep python` |
| `Not logged in yet` on start | run `.venv/bin/python login.py` |
| `no active voice chat` | start a voice chat in the group first |
| `-503 Timeout` on `phone.JoinGroupCall` | temporary Telegram-side error; just send the command again |
| Playback stops by itself / the bot disappears from the voice chat | the call was lost: Telegram dropped the connection, the voice chat was closed, or the account was removed. PyTgCalls forgets such a call silently, so the bot now watches for it (connection changes, call-left updates and a check every 5 seconds) and writes the reason to the log: `voice connection in <chat>: FAILED / TIMEOUT / CLOSED`, `call update in <chat>: kicked / closed_voice_chat ...` and `lost the voice call in <chat> (<reason>) at mm:ss`. After a lost connection it rejoins and goes on from the same position (at most 2 times per 5 minutes, `REJOIN_LIMIT` / `REJOIN_WINDOW` in `plugins/stream.py`); when that does not work it continues with the queue. When the voice chat was closed or the account was kicked it clears the queue and leaves. Look at it with `journalctl -u videoplayerbot \| grep -E 'lost the voice call\|rejoined\|voice connection\|call update'` |
| `the card message was removed from the chat` in the log | something (usually a moderation bot) deleted the card. Playback is not affected, the card just stops updating |
| Service dies with `SEGV` when joining | that was the old `tgcalls` library – this version uses ntgcalls and does not have it |
| `FILE_REFERENCE_EXPIRED` when replying to an old file | the app re-fetches the replied message for a fresh reference; update to this version |
| YouTube download / search error | update yt-dlp (section 8); make sure `deno` exists: `.venv/bin/deno --version` |
| Choppy video / high CPU | lower `VIDEO_QUALITY`; give the container more cores |
| `unknown constructor` in logs | Kurigram too old for Telegram's current layer – `uv pip install -U kurigram` |
| `commandmapper:` error on start | a name in `commandmapper.py` is not lowercase / is used twice |
| Session invalid / `AUTH_KEY_*` errors | stop the service, delete `sessions/user.session*`, run `login.py` again; never use the same session from two places at once |

## 10. Backup and restore

Make a backup (code and login kept apart):

```bash
cd /root/VideoPlayerBot
B=/root/backups/VideoPlayerBot-$(date +%F_%H%M); mkdir -p $B
tar --exclude=.venv --exclude=downloads --exclude=__pycache__ --exclude=.env --exclude=sessions --exclude=.git -czf $B/code.tar.gz .
tar -czf $B/secrets-env-session.tar.gz .env sessions && chmod 600 $B/secrets-env-session.tar.gz
.venv/bin/python -m pip freeze > $B/requirements.freeze.txt 2>/dev/null || uv pip freeze --python .venv/bin/python > $B/requirements.freeze.txt
```

Restore: unpack `code.tar.gz` into `/root/VideoPlayerBot`, run `./setup.sh`, then unpack `secrets-env-session.tar.gz`
in the same folder (restores `.env` and the login, so no new login is needed). Without the secrets archive: create `.env`
(section 3) and log in again (section 4).

## 11. Project layout

```
main.py                 start: loads plugins, starts the Telegram client + voice chat engine
login.py                one-time interactive login
config.py               reads .env
commandmapper.py        command names and aliases (edit to rename commands)
translations.py         texts of /start, /help, /about and the command hint (built from commandmapper)
helpers/user.py         the Telegram user-account client
helpers/voice.py        py-tgcalls engine (call_py)
helpers/ytdl.py         yt-dlp helpers: stream links, name search, file download, temp file cleanup
helpers/media.py        ffprobe audio/video detection, thumbnails, profile picture
helpers/download.py     Telegram download with progress, stall detection and timeouts
helpers/decorators.py   authorization (logged-in account + SUDO_USERS, owners = OWNER_USERS)
helpers/lyrics.py       synced lyrics lookup (LRCLIB) and the lyrics video (ffmpeg + libass)
plugins/stream.py       /play /stream /next /queue /pause /resume /end /restart /jump /loop /vol /lyrics /delete + queue + stream-end handling + lost-call recovery + now-playing card
plugins/download.py     /download
plugins/private.py      /start /help /about
plugins/dmplay.py       owners: /play <number> and /stream <number> from the private chat
plugins/owner.py        owners: /list /join /leave
plugins/sudo.py         owners: /admins /promote /demote (SUDO_USERS, saved to .env)
plugins/nopm.py         optional private-message auto reply
deploy/videoplayerbot.service   systemd unit
Dockerfile              optional container image (the login must be created once inside the sessions volume)
assets/, helpers/admins.py      unused leftovers of the original project; assets/profile.jpg is a runtime cache
```

## Progress bar, jump, volume, delete

- The now-playing card shows `elapsed bar total` and refreshes every PROGRESS_EVERY seconds (default 10, set in .env). Live streams show only the elapsed time.
- `/jump <time>` moves in the current media (aliases: seek). The time is a number with an optional unit: s = seconds (default), m = minutes, h = hours. No sign or `+` goes ahead, `-` goes back. Examples: `/jump 30`, `/jump +30s`, `/jump 5m`, `/jump -10`, `/jump -40s`, `/jump 1h`.
- `/loop` (aliases: repeat) repeats the media that plays now, again and again; send it again (or `/loop off`) to stop. Starting another item (/next, the queue moving on) switches it off. The card shows 🔁 while it is on. Not possible on live streams.
- `/vol <1-200>` (alias: volume) sets the bot's volume in the voice chat, 100 = normal. It is applied with an ffmpeg audio filter (Telegram ignores the volume of the bot own audio), so changing it restarts the running track at the same position, with a short gap. Without a number it shows the current value. The value is kept per chat and applied to every new track until the app restarts.
- `/delete` (alias: del) deletes all messages the bot sent in the chat (only those it sent itself, up to the last 300 since the last restart, never your normal messages). Reply to one message with it to delete only that message.
- Not possible on live streams, and not past the end of the media (use /next or /end).
- Names can be changed in commandmapper.py.
- `/lyrics <song name or link>` (aliases: lyric) finds the song like `/play` does, looks up time-synced lyrics on LRCLIB and plays the song as a video: blurred cover (or a dark background), the current line big in the middle, the previous / next line dimmed, title and artist on top. The lyrics are burned into the video by ffmpeg, so `/pause`, `/jump`, `/loop` and `/vol` keep them in sync. When no synced lyrics are found (or the song is longer than LYRICS_MAX_MINUTES, or it has no title), the song just plays as audio and the bot says why.
- `/lyrics` without a name converts the song that plays now: the video starts at the current position and replaces the audio stream.
- The search uses the title that is shown on the card (cleaned from "(Official Video)", "[HD]", "feat." ...) as `Artist - Song` or free text and needs the song length to be within LYRICS_TOLERANCE seconds of the lyrics. Titles in Persian script are normalised (Arabic letter forms, diacritics, ZWNJ) and searched several ways, and many are found (LRCLIB links some Persian names to its transliterated entries), but not all: its entries are mostly in English letters, and `Googoosh - Parandeh` works where the same in Persian letters does not. When nothing is found the bot suggests the English-letter form `/lyrics Artist - Song`; the lyrics themselves can be Persian.
- Persian / Arabic text: libass shapes and reorders it (HarfBuzz + FriBidi) and the **Vazirmatn** font covers the letters. On a fresh install `setup.sh` / the Dockerfile install it. Another font can be used with LYRICS_FONT in `.env` (put its .ttf into `assets/fonts` if it is not installed system-wide).
- Needs ffmpeg built with libass (the Debian / Ubuntu packages are) and internet access to lrclib.net. Rendering takes a few seconds, the video is 640x360 at 10 fps and deleted like any other temp file.
