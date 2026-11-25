"""What played when the app stopped (systemctl restart, /restart), so it can go on after the start.
Saved to data/session.json (0600) on shutdown, read once at start and then deleted."""

import os
import json
import time
import tempfile
from core.models import MediaItem
from core.state import StateStore

MAX_AGE = 24 * 3600


def _record(item: MediaItem) -> dict | None:
    if not item.origin:
        return None
    by = item.requested_by
    return {"origin": item.origin, "reply_chat": item.reply_chat,
            "requested_by": {"id": by.id, "name": by.name} if by else None}


class SessionFile:
    def __init__(self, path: str):
        self.path = path

    def save(self, store: StateStore) -> int:
        chats = []
        for state in store._chats.values():
            items = []
            if state.playback:
                items.append(_record(state.playback.item))
            items += [_record(i) for i in state.queue]
            items = [i for i in items if i]
            if not items and state.volume == 100:
                continue
            pb = state.playback
            chats.append({"chat": state.chat_id, "title": state.title, "volume": state.volume, "loop": state.loop,
                          "position": pb.position() if pb and pb.item.origin else 0, "paused": bool(pb and pb.paused),
                          "items": items})
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix=".session-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"saved_at": time.time(), "chats": chats}, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
        return len(chats)

    def take(self) -> list[dict]:
        """The saved chats (once): the file is removed, so a crash loop does not replay it again and again."""
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, ValueError):
            return []
        finally:
            try:
                os.remove(self.path)
            except OSError:
                pass
        if time.time() - data.get("saved_at", 0) > MAX_AGE:
            return []
        return data.get("chats") or []
