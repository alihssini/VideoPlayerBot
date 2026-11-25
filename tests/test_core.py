import asyncio
import json
import os
import time

import pytest

from core.acl import AclService, Role
from core.errors import UserError
from core.files import FileStore
from core.models import AUDIO, VIDEO, MediaItem, Requester
from core.player import Player, PAUSED, PLAYING, SKIPPED, STOPPED
from core.state import StateStore
from core.timeparse import parse_jump
from ui.card import CaptionData, build_caption


# ------------------------------------------------------------------------------------------------ fakes

class FakeVoice:
    def __init__(self):
        self.calls, self.playing = [], set()

    async def play(self, chat_id, source, kind, start=0, volume=100, timeout=90):
        self.calls.append(("play", chat_id, source, kind, int(start), volume))
        self.playing.add(chat_id)

    async def pause(self, chat_id):
        self.calls.append(("pause", chat_id))
        return chat_id in self.playing

    async def resume(self, chat_id):
        self.calls.append(("resume", chat_id))
        return chat_id in self.playing

    async def leave(self, chat_id):
        self.calls.append(("leave", chat_id))
        self.playing.discard(chat_id)

    async def in_call(self, chat_id):
        return chat_id in self.playing


class FakeEvents:
    def __init__(self):
        self.log = []

    async def started(self, state, item, replaced, by=None):
        self.log.append(("started", item.title, replaced, by.name if by else None))

    async def changed(self, state, label, by=None):
        self.log.append(("changed", label, by.name if by else None))

    async def finished(self, state, label, by=None):
        self.log.append(("finished", label, by.name if by else None))

    async def failed(self, state, item, error):
        self.log.append(("failed", item.title))


def run(coro):
    return asyncio.run(coro)


def make_player(tmp_path, max_queue=3):
    files = FileStore(str(tmp_path / "dl"))
    voice, events = FakeVoice(), FakeEvents()
    return Player(voice, StateStore(), files, events, max_queue), voice, events, files


def item(title, kind=AUDIO, duration=100.0, **kw):
    return MediaItem(kind=kind, source=f"/src/{title}", title=title, duration=duration, **kw)


ALI = Requester(1, "Ali")


# ---------------------------------------------------------------------------------------------- tests

def test_parse_jump():
    assert parse_jump("30") == ("delta", 30)
    assert parse_jump("+2m") == ("delta", 120)
    assert parse_jump("-10") == ("delta", -10)
    assert parse_jump("-40s") == ("delta", -40)
    assert parse_jump("1h") == ("delta", 3600)
    assert parse_jump("1:30") == ("to", 90)
    assert parse_jump("01:02:03") == ("to", 3723)
    assert parse_jump("0") == ("to", 0)
    assert parse_jump("abc") is None


def test_caption_has_requester_bold_and_no_command_list():
    text = build_caption(CaptionData(label=PLAYING, by=None, kind=AUDIO, lyrics=False, live=False, name="Artist - Song",
                                     link=None, pos=30, dur=120, requester="Ali*", loop=True, volume=120,
                                     next_name="Next one", more=2, where=None))
    assert "**Artist - Song**" in text
    assert "👤 Requested by **Ali**" in text           # markdown characters of names are removed
    assert "🔁 Loop" in text and "🔊 120" in text
    assert "⏭ Next: Next one (+2 more)" in text
    assert "/pause" not in text
    assert len(text) <= 1024


def test_caption_live():
    text = build_caption(CaptionData(label=PAUSED, by="Sara", kind=VIDEO, lyrics=False, live=True, name="Radio",
                                     link="https://x", pos=65, dur=None, requester=None, loop=False, volume=100,
                                     next_name=None, more=0, where="Group"))
    assert text.startswith("⏸ Paused by **Sara** · 🎬 Video · Group")
    assert "🔴 **LIVE** · `01:05`" in text


def test_filestore_refcount_and_shared_name(tmp_path):
    files = FileStore(str(tmp_path / "dl"))
    path = files.path(-100, "yt_abc_a", "mp3")
    assert path == files.path(-100, "yt_abc_a", "mp3")            # same media, same chat: same file
    assert path != files.path(-200, "yt_abc_a", "mp3")            # other chat: own file
    open(path, "w").write("x")
    files.acquire(path)
    files.acquire(path)                                           # queued twice
    files.release(path)
    assert os.path.exists(path)
    files.release(path)
    assert not os.path.exists(path)
    assert os.path.basename(os.path.dirname(path)) == "chat_-100"
    assert not os.path.exists(os.path.dirname(path))              # empty chat folder removed
    files.drop_unused("/etc/passwd")                              # outside the store: never touched
    assert os.path.exists("/etc/passwd")


def test_acl_roles_files_and_reload(tmp_path):
    errors = []
    acl = AclService(str(tmp_path), [10], on_error=errors.append)
    assert acl.role(10, -1) == Role.BOT_OWNER
    assert acl.role(20, -1) is None
    assert acl.group_owners(-1).add(20, "Owner", 10)
    assert acl.group_sudo(-1).add(30, "Sudo", 20)
    assert not acl.group_sudo(-1).add(30, "Sudo", 20)             # no duplicates
    assert acl.role(20, -1) == Role.GROUP_OWNER and acl.role(20, -2) is None
    assert acl.role(30, -1) == Role.SUDO
    assert acl.migrate_legacy_sudo([40, 41]) == 2 and acl.role(40, -99) == Role.SUDO
    assert acl.migrate_legacy_sudo([50]) == 0                      # only once
    path = os.path.join(acl.groups_dir, "-1.json")
    data = json.load(open(path, encoding="utf-8"))
    assert [e["id"] for e in data["sudo"]] == [30]
    assert oct(os.stat(path).st_mode)[-3:] == "600"
    # hand edit (plain ids are accepted) is picked up without restart
    time.sleep(0.01)
    data["sudo"].append(31)
    json.dump(data, open(path, "w"))
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 10_000_000))
    assert acl.role(31, -1) == Role.SUDO
    # a broken file keeps the last good version
    open(path, "w").write("{ broken")
    os.utime(path, ns=(time.time_ns(), time.time_ns() + 20_000_000))
    assert acl.role(31, -1) == Role.SUDO and errors
    acl.bot_owners.add(60, "Bot owner", 10)
    assert acl.is_bot_owner(60) and not acl.is_root(60)


def test_player_queue_skip_stop(tmp_path):
    async def scenario():
        player, voice, events, _ = make_player(tmp_path)
        assert await player.enqueue(-1, "G", item("a")) == 0
        assert await player.enqueue(-1, "G", item("b")) == 1
        assert await player.enqueue(-1, "G", item("c")) == 2
        assert await player.enqueue(-1, "G", item("d")) == 3
        with pytest.raises(UserError):
            await player.enqueue(-1, "G", item("e"))                  # full (max 3)
        nxt = await player.skip(-1, ALI)
        assert nxt.title == "b"
        assert ("started", "b", SKIPPED, "Ali") in events.log
        kind, dropped = await player.stop(-1, ALI)
        assert dropped == 2 and ("finished", STOPPED, "Ali") in events.log
        assert ("leave", -1) in voice.calls
        with pytest.raises(UserError):
            await player.stop(-1, ALI)
    run(scenario())


def test_player_pause_resume_seek_volume(tmp_path):
    async def scenario():
        player, voice, events, _ = make_player(tmp_path)
        await player.enqueue(-1, "G", item("a", duration=300))
        await player.pause(-1, ALI)
        with pytest.raises(UserError):
            await player.pause(-1, ALI)                               # already paused
        to, length = await player.seek(-1, to=90)
        assert (to, length) == (90, 300)
        assert voice.calls[-2][:5] == ("play", -1, "/src/a", AUDIO, 90) and voice.calls[-1] == ("pause", -1)  # stays paused
        with pytest.raises(UserError):
            await player.seek(-1, to=400)                             # past the end
        await player.resume(-1, ALI)
        assert await player.set_volume(-1, 150, ALI) is True
        assert voice.calls[-1][5] == 150
        state = player.store.get(-1)
        assert state.volume == 150 and 89 <= state.playback.position() <= 92
    run(scenario())


def test_stream_end_advances_and_loop(tmp_path):
    async def scenario():
        player, voice, events, _ = make_player(tmp_path)
        await player.enqueue(-1, "G", item("a"))
        await player.enqueue(-1, "G", item("b"))
        state = player.store.get(-1)
        await player.on_stream_end(-1, {"audio"})
        assert state.playback.item.title == "a"                      # within 3 s: late event of a replaced stream
        state.started_at -= 10
        await player.set_loop(-1, True, ALI)
        await player.on_stream_end(-1, {"audio"})
        assert state.playback.item.title == "a"                      # loop: same media again
        state.started_at -= 10
        await player.set_loop(-1, False, ALI)
        await player.on_stream_end(-1, {"audio"})
        assert state.playback.item.title == "b"
        state.started_at -= 10
        await player.on_stream_end(-1, {"audio"})
        assert not state.active and events.log[-1][0] == "finished"
    run(scenario())


def test_short_media_end_is_not_ignored(tmp_path):
    async def scenario():
        player, voice, events, _ = make_player(tmp_path)
        await player.enqueue(-1, "G", item("beep", duration=2))
        await player.on_stream_end(-1, {"audio"})
        assert not player.store.get(-1).active
    run(scenario())


def test_failed_queue_item_is_skipped_and_files_released(tmp_path):
    async def scenario():
        player, voice, events, files = make_player(tmp_path)
        await player.enqueue(-1, "G", item("a"))

        async def broken(it):
            raise RuntimeError("gone")
        path = files.path(-1, "k", "jpg")
        open(path, "w").write("x")
        bad = item("bad", prepare=broken)
        bad.files.append(files.acquire(path))
        await player.enqueue(-1, "G", bad)
        await player.enqueue(-1, "G", item("c"))
        await asyncio.sleep(0)                                         # prefetch task of "bad" runs and fails
        player.store.get(-1).started_at -= 10
        await player.on_stream_end(-1, {"audio"})
        assert ("failed", "bad") in events.log and player.store.get(-1).playback.item.title == "c"
        assert not os.path.exists(path)
    run(scenario())


def test_caption_volume_only_while_playing():
    base = dict(by=None, kind=AUDIO, lyrics=False, live=False, name="Song", link=None, pos=1, dur=100, requester=None,
                loop=False, volume=100, next_name=None, more=0, where=None)
    assert "🔊 100" in build_caption(CaptionData(label=PLAYING, **base))
    assert "🔊 100" in build_caption(CaptionData(label=PAUSED, **base))
    assert "🔊" not in build_caption(CaptionData(label="✅ Finished", **base))
