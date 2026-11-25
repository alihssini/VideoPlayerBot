# VideoPlayerBot – Manual (user-account edition)

The app logs in with a normal Telegram **user account** and streams audio / video into the voice chats of the groups that account is in. Commands are sent in the group or in the private chat with that account.

## 1. Requirements

- Debian / Ubuntu (an LXC with 2 vCPU / 2 GB RAM is plenty for 720p), or Docker
- `API_ID` / `API_HASH` from https://my.telegram.org → API development tools
- A Telegram account for the player (a second account is best; it must be a member of the groups)

## 2. Install

```bash
cd /root/VideoPlayerBot
./setup.sh --with-service     # apt: ffmpeg, fonts (Vazirmatn), libraqm, jq, moreutils · uv + Python 3.12 venv · requirements · systemd unit
```
`setup.sh` creates `.env` from `.env.sample` (mode 0600) and the folders `data/acl/groups` and `sessions` (0700).

## 3. Configure – `.env`

| Setting | Default | Meaning |
|---|---|---|
| `API_ID`, `API_HASH` | – | required |
| `PHONE_NUMBER` | asked at login | international format |
| `OWNER_USERS` | – | **root owners**: bot owners no command can remove (space separated ids). The logged-in account is always one. |
| `SUDO_USERS` | – | only read once: moved to `data/acl/global_sudo.json` on the first start, then removed from `.env` (backup in `~/backups`) |
| `VIDEO_QUALITY` | `SD_360p` | `SD_360p`, `SD_480p`, `HD_720p`, `FHD_1080p` — also the max height downloaded from YouTube. A wrong value stops the start with a message. |
| `MAX_QUEUE` | 10 | items waiting per group |
| `PROGRESS_EVERY` | 10 | seconds between card updates (min 5) |
| `AUTO_LEAVE_MINUTES` | 10 | leave the voice chat when nobody else listened this long (0 = never) |
| `USER_PARALLEL` | 2 | `/play` / `/download` requests one user may run at the same time (bot owners unlimited) |
| `DOWNLOAD_MAX_MB` | 1000 | bigger files are refused |
| `SEARCH_MAX_MINUTES` | 15 | song-name searches skip longer results |
| `LYRICS_MAX_MINUTES`, `LYRICS_TOLERANCE`, `LYRICS_FONT`, `LRCLIB_URL` | 15, 10, Vazirmatn, lrclib.net | lyrics videos |
| `REPLY_MESSAGE` | empty | auto-reply to private messages of people **without** a role |
| `SESSION_NAME`, `SESSION_DIR`, `DATA_DIR` | user, sessions, data | file locations |

## 4. Login (once)

```bash
.venv/bin/python login.py     # enter the code Telegram sends to the account (and the 2FA password)
```
The session is stored in `sessions/user.session` (0600). If it ever becomes invalid, the service stops with a message: run `login.py` again.

## 5. Run

```bash
systemctl start|stop|restart|status videoplayerbot
journalctl -u videoplayerbot -f            # log
```
On stop / restart (also `/restart`) the account leaves every voice chat, the cards show "Stopped (restart)" and what played is saved to `data/session.json`; after the start it continues (same position, queue, volume, loop, pause). The file is used once and is ignored when older than a day.

## 6. Roles

| Role | Who | Can |
|---|---|---|
| 👑 **Bot owner** | root owners (`OWNER_USERS` + the account) and runtime bot owners | everything, in every group and in private chat |
| 👥 **Group owner** | per group, set by a bot owner | playback in that group + manage its SUDO users |
| 🎧 **SUDO user** | per group (set by its owners) or **global** (every group, set by bot owners) | playback commands |

Strangers are ignored silently in groups. Telegram admin rights give **no** role. Commands sent anonymously "as the group" get a hint to send them as yourself.

### Managing roles (all apply at once, no restart)

| Command | Who | Where |
|---|---|---|
| `/admins` · `/promote <reply / id / @username>` · `/demote <reply / number / id / @username>` | group owners (their group), bot owners | in the group, or in private chat for the `/use` group or with a group number: `/promote 3 @name` |
| `/owners` · `/addowner …` · `/delowner …` | list: group owners · change: bot owners | same |
| `/gadmins` · `/gpromote …` · `/gdemote …` | bot owners | anywhere (global SUDO) |
| `/botowners` · `/addbotowner …` · `/delbotowner …` | list: bot owners · change: **root owners only** | anywhere; root owners (🔑) cannot be removed by a command |
| `/perms` | everyone with a role | your role here / in all your groups |

### The role files – `data/acl/`

```
data/acl/bot_owners.json          {"users": [{"id": 123, "name": "Ali", "added_by": 456, "added_at": "2026-11-25T19:40"}]}
data/acl/global_sudo.json         same shape
data/acl/dm_targets.json          {"123": -1001234567890}          (/use choice per user)
data/acl/groups/<chat_id>.json    {"title": "...", "owners": [...], "sudo": [...]}
data/acl/groups/left/             files of groups the account left (kept, not deleted)
```
Examples with fake ids: [`examples/acl/`](examples/acl/) (see [`examples/README.md`](examples/README.md)). They are pretty-printed and can be edited by hand; plain ids are accepted in the lists. Changes are picked up on the next command (no restart). A file with a JSON error is **not** used — the previous version stays active and the root owners get a private message about it.

```bash
cd /root/VideoPlayerBot/data/acl
jq '.users[] | "\(.id) \(.name)"' global_sudo.json
jq '.sudo += [{"id": 123456789, "name": "Sara"}]' groups/-1001234567890.json | sponge groups/-1001234567890.json
jq 'del(.sudo[] | select(.id == 123456789))' groups/-1001234567890.json | sponge groups/-1001234567890.json
```

## 7. Use

### In a group
Start a voice chat (or give the account the right to start it), then:

| Command | |
|---|---|
| `/play <song name>` | search YouTube, play as audio · `/play video <name or link>` as video · `/play audio …` forces audio |
| `/play <link>` | YouTube, live stream, radio, direct file — audio or video is detected; a YouTube **playlist** link adds its first videos |
| reply `/play` to an audio / video / a message with a link | play that |
| `/stream …` | same as `/play video …` |
| `/lyrics <song>` / `/lyrics` | song as a video with synced lyrics / the current song from its position |
| `/pause` `/resume` `/next` `/end` | |
| `/queue` · `/remove 2` · `/move 3 1` · `/shuffle` · `/clear` · `/now` | queue (with who requested what) and editing it; `/now` posts the card again |
| `/jump 30` `+2m` `-10` `-40s` `1h` · `/jump 1:30` | move ahead / back · go to 1:30 (`0` = from the start) |
| `/loop` (`on` / `off`) · `/vol 80` (1-200) | repeat · volume |
| `/delete` | delete all messages of the bot here (or only the replied one) |
| `/download <name or link>` (`video` first for mp4) | the file in the chat |

While something plays, new media joins the queue. YouTube videos in the queue are downloaded only when they are next (the next one is prepared in the background), audio links are refreshed right before they play.

### In the private chat with the account
Every playback command works here as well and goes to a group:

1. `/list` — your groups, numbered (bot owners: all joined groups; group owners / SUDO: the groups where they have a role; global SUDO: the groups they share with the account)
2. `/use 3` — your commands here go to group 3 from now on (remembered, also after restarts; 🎯 in `/list`), `/use` shows it, `/use off` removes it
3. `/pause`, `/queue`, `/play <song>`, … — for that group. Another group for one command: `#<number>` first: `/pause #2`, `/vol #2 80`, `/jump #2 1:30`. Where a number cannot be mistaken for a value a bare number works too: `/pause 2`, `/play 2 <song>`.

Media started from the private chat gets its card **only in the private chat** (with the group name); media started in the group gets it in the group. If you have a role in only one group, it is chosen automatically.

### The now-playing card
A rendered picture (blurred artwork, cover, title, artist, kind badge, length, group) with a caption:
```
▶️ Playing · 🎵 Audio
**Artist - Title**
`01:23 ━━━●────────── 04:56`
👤 Requested by **Ali** · 🔁 Loop · 🔊 100
⏭ Next: Other song (+3 more)
```
State changes name who did it ("⏸ Paused by **Sara**", "⏭ Skipped by …"). If a moderation bot deletes the card, playback goes on without it.

### Buttons under the card (optional)
With `BOT_TOKEN` in `.env` (a real bot from @BotFather) the card is posted by that bot with buttons:
`⏸/▶️` pause / resume · `⏭` next · `⏹` stop · `🔁` repeat
`⏪ 60` `⏪ 30` `⏩ 30` `⏩ 60` jump back / ahead (seconds)
`🔉 −20` / `🔊 +20` volume (the current volume is in the card text) · `📋` queue · `⬇️` the playing media as a file (sent as a new message by the bot; YouTube is downloaded again, Telegram files / lyrics videos are sent directly).
Live streams have no repeat / jump / download buttons.
A press needs the same role as the command (SUDO or higher in that group); others get "not allowed". The buttons follow the state (▶️ while paused) and disappear when the media ends.
- **Groups:** add the bot to the group (it only needs to send messages). Where it is not a member, the account posts the card without buttons (checked again every 10 minutes).
- **Private chat:** a bot can only write to people who started it: send `/start` to the bot once (it confirms), else the card comes from the account without buttons. The bot tries again for every new card, so it works right after `/start`.
- The bot logs in by itself on start (`sessions/bot.session`); a wrong token only disables the buttons (see the log).

### Renaming commands – `commandmapper.py`
Each command has a list of names; the first one is shown in texts. Names must be lowercase letters / digits / `_` (Persian letters work) and unique. Restart after editing.

## 8. Temp files / disk

Downloads live in `downloads/chat_<chat_id>/<media key>.<ext>` (folder removed when it is empty): the same media in the same chat is **one** file, also when it is queued several times. Files are reference counted and deleted when nothing plays or queues them any more; leftovers are swept every 30 minutes (older than 6 h) and the folder is wiped at start. `/status` shows the size.

## 9. Update

```bash
./scripts/update.sh          # backup, newest yt-dlp, tests, restart
./scripts/update.sh --all    # every package to its newest version (re-test, pins in requirements.txt are the tested ones)
```
Code updates: `git pull`, then `.venv/bin/python -m pytest -q tests` and `systemctl restart videoplayerbot`.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| "There is no active voice chat" | start the voice chat first (or give the account the "manage voice chats" right) |
| Nothing happens on a command | the sender has no role there (`/perms`), or sent it anonymously |
| YouTube errors / HTTP 403 | `./scripts/update.sh` (newer yt-dlp); `deno` must be in the venv |
| Stream stops / drops | the log shows "lost the voice call … rejoined"; after 2 drops in 5 minutes it gives up |
| Persian text wrong on the card | `libraqm0` / `libfribidi0` missing → `apt-get install libraqm0 libfribidi0` |
| Role change not applied | check the JSON file (`jq . file.json`); a broken file is reported to the root owners |

## 11. Backup and restore

```bash
tar --exclude=.venv --exclude=downloads -czf ~/backups/VideoPlayerBot-$(date +%F).tar.gz -C /root VideoPlayerBot
```
Contains the code, `.env`, `sessions/` (login) and `data/` (roles, `/use` choices). Restore: unpack, `./setup.sh --with-service`, `systemctl start videoplayerbot` (no new login needed when `sessions/` is restored).

## 12. Project layout

```
main.py              start / graceful stop (signals), restore after restart
login.py             one-time login
commandmapper.py     command names and aliases
app/                 config.py (typed .env settings) · client.py (Telegram client, sent messages) · container.py (wires everything) · restore.py
core/                no Telegram code: models, state, player (queue, pause, seek, volume, loop, stream end), recovery (lost calls),
                     idle (auto-leave), files (per-chat ref-counted downloads), acl (roles in JSON), session, timeparse, errors, events
services/            voice (PyTgCalls), youtube (yt-dlp), resolver (request → media item), telegram_media, probe (ffprobe/ffmpeg),
                     lyrics, card_renderer (Pillow), groups (joined groups, numbered lists)
ui/                  card (now-playing card + ticker), replies (safe replies, error wrapper, status messages), texts (help)
plugins/             thin command handlers: playback, roles, groups, info, download, nopm, common (target group + permission)
tests/               pytest: .venv/bin/python -m pytest -q tests
data/                acl/ (roles), session.json (only between stop and start)
deploy/              systemd unit · scripts/update.sh · Dockerfile · setup.sh
```
