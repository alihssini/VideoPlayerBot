"""Typed settings read once from .env and validated at start-up (bad values stop the app with a clear message)."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

QUALITY_HEIGHT = {"SD_360p": 360, "SD_480p": 480, "HD_720p": 720, "FHD_1080p": 1080}


def _text(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    raw = _text(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"[ERROR] - {name} in .env must be a whole number, not {raw!r}")


def _ids(*names: str) -> tuple:
    for name in names:
        raw = _text(name)
        if raw:
            return tuple(int(x) for x in raw.replace(",", " ").split() if x.lstrip("-").isdigit())
    return ()


def _required(name: str) -> str:
    value = _text(name)
    if not value:
        raise SystemExit(f"[ERROR] - {name} is missing in .env (get API_ID / API_HASH from https://my.telegram.org)")
    return value


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str | None
    bot_token: str | None       # optional real bot: posts the card with buttons
    session_name: str
    session_dir: str
    root_owners: tuple          # OWNER_USERS: bot owners that commands can never remove
    legacy_sudo: tuple          # SUDO_USERS: only read once, to migrate them into data/acl/global_sudo.json
    prefixes: tuple
    reply_message: str | None
    download_max_mb: int
    video_quality: str
    max_queue: int
    progress_every: int
    auto_leave_minutes: int     # leave when nobody else is in the voice chat this long (0 = never)
    user_parallel: int          # requests (/play, /download) one user may run at the same time
    search_max_seconds: int
    lyrics_max_seconds: int
    lyrics_tolerance: int
    lyrics_font: str
    lrclib_url: str
    data_dir: str
    download_dir: str

    @property
    def video_height(self) -> int:
        return QUALITY_HEIGHT[self.video_quality]

    @property
    def max_bytes(self) -> int:
        return self.download_max_mb * 1024 * 1024


def load() -> Settings:
    quality = _text("VIDEO_QUALITY", "SD_360p")
    if quality not in QUALITY_HEIGHT:
        raise SystemExit(f"[ERROR] - VIDEO_QUALITY={quality!r} is not valid, use one of: {', '.join(QUALITY_HEIGHT)}")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return Settings(
        api_id=int(_required("API_ID")),
        api_hash=_required("API_HASH"),
        phone=_text("PHONE_NUMBER") or None,
        bot_token=_text("BOT_TOKEN") or None,
        session_name=_text("SESSION_NAME", "user"),
        session_dir=_text("SESSION_DIR", "sessions"),
        root_owners=_ids("OWNER_USERS", "OWNERS"),
        legacy_sudo=_ids("SUDO_USERS", "SUDOERS"),
        prefixes=("/", "!", "."),
        reply_message=_text("REPLY_MESSAGE") or None,
        download_max_mb=_int("DOWNLOAD_MAX_MB", 1000),
        video_quality=quality,
        max_queue=_int("MAX_QUEUE", 10),
        progress_every=max(5, _int("PROGRESS_EVERY", 10)),
        auto_leave_minutes=max(0, _int("AUTO_LEAVE_MINUTES", 10)),
        user_parallel=max(1, _int("USER_PARALLEL", 2)),
        search_max_seconds=_int("SEARCH_MAX_MINUTES", 15) * 60,
        lyrics_max_seconds=_int("LYRICS_MAX_MINUTES", 15) * 60,
        lyrics_tolerance=_int("LYRICS_TOLERANCE", 10),
        lyrics_font=_text("LYRICS_FONT", "Vazirmatn"),
        lrclib_url=_text("LRCLIB_URL", "https://lrclib.net/api").rstrip("/"),
        data_dir=os.path.join(base, _text("DATA_DIR", "data")),
        download_dir=os.path.join(base, "downloads"),
    )


settings = load()
