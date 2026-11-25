"""Files in downloads/<chat_id>/<key>.<ext> with reference counting.

The same media in the same chat has the same name, so queueing it several times keeps ONE file.
A file is deleted when nothing (now playing / queued item / an upload in progress) holds it any more.
"""

import os
import time
import shutil
import asyncio
from collections import Counter


class FileStore:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._refs: Counter = Counter()
        self._locks: dict[str, asyncio.Lock] = {}
        os.makedirs(self.root, exist_ok=True)

    def path(self, chat_id: int, key: str, ext: str) -> str:
        folder = os.path.join(self.root, str(chat_id))
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"{key}.{ext.lstrip('.')}")

    def lock(self, path: str) -> asyncio.Lock:
        """One download per file at a time: a second request waits and re-uses the file."""
        return self._locks.setdefault(path, asyncio.Lock())

    def owns(self, path) -> bool:
        if not path:
            return False
        try:
            return os.path.commonpath([os.path.abspath(path), self.root]) == self.root
        except ValueError:
            return False

    def acquire(self, path) -> str | None:
        if self.owns(path):
            path = os.path.abspath(path)
            self._refs[path] += 1
            return path
        return None

    def release(self, path) -> None:
        if not self.owns(path):
            return
        path = os.path.abspath(path)
        if self._refs[path] > 1:
            self._refs[path] -= 1
            return
        self._refs.pop(path, None)
        self._locks.pop(path, None)
        self._remove(path)

    def in_use(self, path) -> bool:
        return self._refs.get(os.path.abspath(path), 0) > 0

    def drop_unused(self, path) -> None:
        """Delete a file that was made but never acquired (e.g. a failed request)."""
        if self.owns(path) and not self.in_use(path):
            self._remove(os.path.abspath(path))

    @staticmethod
    def _remove(path: str) -> None:
        try:
            os.remove(path)
        except OSError:
            pass

    def wipe(self) -> None:
        """Startup: nothing plays, everything left over is stale."""
        for name in os.listdir(self.root):
            target = os.path.join(self.root, name)
            shutil.rmtree(target, ignore_errors=True) if os.path.isdir(target) else self._remove(target)

    def sweep(self, max_age: int) -> None:
        """Delete unused files older than max_age seconds (aborted downloads, old thumbnails)."""
        cutoff = time.time() - max_age
        for folder, _dirs, names in os.walk(self.root):
            for name in names:
                path = os.path.join(folder, name)
                try:
                    if not self.in_use(path) and os.path.getmtime(path) < cutoff:
                        os.remove(path)
                except OSError:
                    pass

    async def sweeper(self, every: int = 1800, max_age: int = 6 * 3600) -> None:
        while True:
            await asyncio.sleep(every)
            self.sweep(max_age)
