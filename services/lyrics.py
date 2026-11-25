"""Synced lyrics: look them up on LRCLIB (https://lrclib.net) and render them into a video.

The lyrics are burned into the picture with ffmpeg (libass), so the timing stays correct for
pause / jump / loop / volume. Persian and other right-to-left text works because libass shapes
and reorders it (harfbuzz + fribidi) and the Vazirmatn font covers Arabic script.
"""

import os
import re
import json
import time
import asyncio

import urllib.error
import urllib.parse
import urllib.request

from app.config import settings

LRCLIB_URL = settings.lrclib_url
USER_AGENT = "VideoPlayerBot (https://github.com/AsmSafone/VideoPlayerBot)"
LYRICS_MAX_SECONDS = settings.lyrics_max_seconds  # longer media is played without lyrics
TOLERANCE = settings.lyrics_tolerance  # lyrics whose song length differs by more seconds are not used
RENDER_TIMEOUT = 600
WIDTH, HEIGHT, FPS = 640, 360, 10
FONT = settings.lyrics_font  # installed with the fonts-vazirmatn package (setup.sh), has Latin + Arabic script
FONT_DIR = os.path.abspath(os.path.join("assets", "fonts"))  # optional: any .ttf / .otf put here is found too

_NOISE = re.compile(r"\(.*?\)|\[.*?\]|\{.*?\}|【.*?】", re.S)
_WORDS = re.compile(r"\b(official|music video|lyric video|lyrics?|video|audio|visuali[sz]er|remaster(?:ed)?|karaoke|hd|hq|4k|mv)\b", re.I)
_FEAT = re.compile(r"\b(?:ft|feat|featuring)\b\.?.*$", re.I)
_EXT = re.compile(r"\.(mp3|m4a|flac|wav|ogg|opus|aac|mp4|mkv|webm)$", re.I)
_TS = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_OFFSET = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]", re.I)


# ---------------------------------------------------------------- lookup

_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_TASHKEEL = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_FA_FIX = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "ؤ": "و"})


def has_arabic_script(text: str) -> bool:
    """True for Persian / Arabic text (its letters do not exist in LRCLIB's mostly transliterated names)."""
    return bool(_ARABIC.search(str(text)))


def normalize_persian(text: str) -> str:
    """Arabic letter forms -> Persian ones, no diacritics, zero-width non-joiner -> space, Persian digits -> 0-9."""
    text = _TASHKEEL.sub("", str(text)).translate(_FA_FIX).replace("\u200c", " ")
    return text.translate({0x06F0 + i: 0x30 + i for i in range(10)} | {0x0660 + i: 0x30 + i for i in range(10)})

def clean_title(title: str) -> str:
    """"Artist - Song (Official Video) [HD]" -> "Artist - Song"."""
    t = _EXT.sub("", str(title)).replace("_", " ")
    t = _NOISE.sub(" ", t)
    t = _WORDS.sub(" ", t)
    t = _FEAT.sub(" ", t)
    t = re.sub(r"\s*[–—|~]+\s*", " - ", t)
    return re.sub(r"\s+", " ", t).strip(" -")


def _get(url: str):
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):  # LRCLIB is sometimes busy
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(1)
    return None


def _words(text: str) -> set:
    return {w for w in re.findall(r"\w{2,}", str(text).casefold())}


def _pick(results, duration, query: str, tolerance=None):
    """The best result that has synced lyrics and a similar length. For Latin queries it must also share a word with
    the query; Persian / Arabic queries skip that (LRCLIB matches them to transliterated names itself) and need a known length."""
    if not isinstance(results, list):
        return None
    persian = has_arabic_script(query)
    if persian and not duration:
        return None
    tolerance = TOLERANCE if tolerance is None else tolerance
    wanted, best = _words(query), None
    for r in results:
        if not isinstance(r, dict) or r.get("instrumental") or not (r.get("syncedLyrics") or "").strip():
            continue
        if not persian and wanted and not (wanted & _words(f"{r.get('artistName', '')} {r.get('trackName', '')}")):
            continue
        length = r.get("duration")
        diff = abs(length - duration) if duration and length else 0
        if duration and length and diff > tolerance:
            continue
        if best is None or diff < best[0]:
            best = (diff, r)
    return best[1] if best else None


def _search_sync(title: str, duration):
    cleaned = clean_title(title)
    if has_arabic_script(cleaned):
        cleaned = normalize_persian(cleaned)
    if not cleaned:
        return None
    tries = []  # (search parameters, allowed length difference or None for the default)
    if " - " in cleaned:
        left, right = (p.strip() for p in cleaned.split(" - ", 1))
        tries.append(({"artist_name": left, "track_name": right}, None))   # "Artist - Song"
        tries.append(({"artist_name": right, "track_name": left}, None))   # "Song - Artist"
    tries.append(({"q": cleaned}, None))
    if " - " in cleaned:
        tries.append(({"q": cleaned.replace(" - ", " ")}, None))
        if has_arabic_script(cleaned):  # one part alone finds the artist or the song under a transliterated name; the length must then fit closely
            tries += [({"q": left}, 4), ({"q": right}, 4)]
    seen = set()
    for params, tolerance in tries:
        url = f"{LRCLIB_URL}/search?" + urllib.parse.urlencode(params)
        if url in seen:
            continue
        seen.add(url)
        found = _pick(_get(url), duration, cleaned, tolerance)
        if found:
            return found
    return None


async def find_lyrics(title: str, duration=None):
    """{"title", "artist", "lines": [(seconds, text), ...]} for a song title and its length, or None when nothing synced is found."""
    found = await asyncio.to_thread(_search_sync, title, duration)
    if not found:
        return None
    lines = parse_lrc(found["syncedLyrics"])
    if not any(text for _, text in lines):
        return None
    return {"title": found.get("trackName") or clean_title(title), "artist": found.get("artistName") or "", "lines": lines}


def parse_lrc(text: str) -> list:
    """LRC text -> sorted [(seconds, line)]; empty lines (instrumental breaks) are kept as ""."""
    offset = _OFFSET.search(text)
    shift = int(offset.group(1)) / 1000 if offset else 0.0
    lines = []
    for raw in text.splitlines():
        stamps = list(_TS.finditer(raw))
        if not stamps:
            continue
        body = re.sub(r"<\d+:\d+(?:[.:]\d+)?>", "", raw[stamps[-1].end():]).strip()  # word-by-word tags
        for s in stamps:
            frac = s.group(3) or "0"
            sec = int(s.group(1)) * 60 + int(s.group(2)) + int(frac) / 10 ** len(frac)
            lines.append((max(0.0, sec - shift), body))
    lines.sort(key=lambda x: x[0])
    return lines


# ---------------------------------------------------------------- subtitles

def _ass_text(text: str) -> str:
    return str(text).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _ts(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(lines: list, duration: float, heading: str) -> str:
    """ASS subtitle script: the heading on top, the current line big in the middle, the previous / next one dimmed."""
    cx, y_prev, y_cur, y_next = WIDTH // 2, 112, 185, 262
    out = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cur,{FONT},30,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,0,5,36,36,10,1",
        f"Style: Dim,{FONT},19,&H00D0D0D0,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1,0,5,36,36,10,1",
        f"Style: Head,{FONT},15,&H00E0E0E0,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1,0,8,20,20,10,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def event(start, end, style, y, text, extra=""):
        if text and end - start > 0.02:
            out.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},{style},,0,0,0,,{{\\an5\\pos({cx},{y}){extra}}}{_ass_text(text)}")

    if heading:
        out.append(f"Dialogue: 0,{_ts(0)},{_ts(duration)},Head,,0,0,0,,{{\\an8\\pos({cx},12)}}{_ass_text(heading)}")

    texts = [(t, s) for t, s in lines if s]
    slots = []  # (start, end, current, previous, next)
    if lines and lines[0][0] > 0.5 and texts:  # intro: only the first line, dimmed
        slots.append((0.0, lines[0][0], "", "", texts[0][1]))
    for i, (t, body) in enumerate(lines):
        end = lines[i + 1][0] if i + 1 < len(lines) else t + 8
        end = min(end, t + 12, duration)
        prev = next((s for tt, s in reversed(texts) if tt < t), "")
        nxt = next((s for tt, s in texts if tt > t), "")
        slots.append((t, end, body, prev if body else "", nxt))
    for start, end, cur, prev, nxt in slots:
        event(start, end, "Dim", y_prev, prev, "\\alpha&H50&")
        event(start, end, "Cur", y_cur, cur, "\\fad(120,80)")
        event(start, end, "Dim", y_next, nxt, "\\alpha&H50&")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- video

def _esc(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


async def render_video(lines: list, duration: float, source, cover, heading: str, out_path: str) -> str:
    """Make an mp4 (picture = blurred cover or a dark background, lyrics burned in, audio of `source`).
    Raises RuntimeError with ffmpeg's message when it fails."""
    out_path = os.path.abspath(out_path)
    ass_path = os.path.splitext(out_path)[0] + ".ass"
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(build_ass(lines, duration, heading))

    cmd = ["ffmpeg", "-y", "-v", "error"]
    if cover:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(cover)]
    else:
        cmd += ["-f", "lavfi", "-i", f"color=c=0x0f172a:s={WIDTH}x{HEIGHT}:r={FPS}"]
    cmd += ["-i", str(source)]
    background = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
        "boxblur=20:2,eq=brightness=-0.28:saturation=1.1,"
        if cover else ""
    )
    subs = f"subtitles=filename='{_esc(ass_path)}'"
    if os.path.isdir(FONT_DIR) and any(n.lower().endswith((".ttf", ".otf")) for n in os.listdir(FONT_DIR)):
        subs += f":fontsdir='{_esc(FONT_DIR)}'"
    cmd += [
        "-vf", f"{background}format=yuv420p,{subs}",
        "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.2f}", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-crf", "30", "-g", str(FPS * 5),
        "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-movflags", "+faststart", out_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), RENDER_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("rendering took too long")
        if proc.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError((err or b"").decode(errors="replace").strip()[-300:] or "ffmpeg failed")
    except BaseException:
        if os.path.isfile(out_path):
            os.remove(out_path)
        raise
    finally:
        if os.path.isfile(ass_path):
            os.remove(ass_path)
    return out_path


class LyricsUnavailable(Exception):
    """Why the song plays without lyrics (shown to the user)."""


class LyricsMaker:
    """Synced lyrics video for an audio item: downloads/<chat>/<key>_lyrics.mp4 (re-used for the same song)."""

    def __init__(self, files, to_jpg):
        self.files, self.to_jpg = files, to_jpg

    async def make(self, chat_id: int, source: str, title: str | None, length: float | None, cover: str | None,
                   key: str, status) -> str:
        """Path of the lyrics video, acquired for the caller. Raises LyricsUnavailable."""
        if not title:
            raise LyricsUnavailable("there is no song title to search the lyrics for")
        if not length:
            raise LyricsUnavailable("the length of the media is unknown (live stream?)")
        if length > LYRICS_MAX_SECONDS:
            raise LyricsUnavailable(f"it is longer than {LYRICS_MAX_SECONDS // 60} minutes")
        dest = self.files.path(chat_id, f"{key}_lyrics", "mp4")
        async with self.files.lock(dest):
            if os.path.isfile(dest) and os.path.getsize(dest) > 0:
                return self.files.acquire(dest)
            await status.update("🎤 `Looking for lyrics ...`")
            found = await find_lyrics(title, length)
            if not found:
                hint = " (Persian names often only match in English letters, try `Artist - Song`)" if has_arabic_script(title) else ""
                raise LyricsUnavailable("no synced lyrics were found for it" + hint)
            heading = f"{found['artist']} - {found['title']}" if found["artist"] else found["title"]
            await status.update(f"🎞 `Rendering the lyrics video ...`\n`{heading.replace('`', ' ')}`")
            own_cover = None
            if not cover:
                own_cover = await self.to_jpg(source, self.files.path(chat_id, f"{key}_cover", "jpg"))
            try:
                await render_video(found["lines"], length, source, cover or own_cover, heading, dest)
            except Exception as e:
                raise LyricsUnavailable(f"the lyrics video could not be made ({type(e).__name__})")
            finally:
                self.files.drop_unused(own_cover)
            return self.files.acquire(dest)
