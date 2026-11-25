import asyncio
import pytest

from core.errors import UserError
from core.models import AUDIO, Requester
from core.session import SessionFile
from plugins.common import UserLimiter
from services.resolver import is_playlist
from tests.test_core import ALI, item, make_player, run


def test_queue_remove_move_shuffle_clear(tmp_path):
    async def scenario():
        player, voice, events, _ = make_player(tmp_path, max_queue=5)
        for name in "abcde":
            await player.enqueue(-1, "G", item(name))
        state = player.store.get(-1)
        assert [i.title for i in state.queue] == list("bcde")
        assert (await player.queue_move(-1, 4, 1)).title == "e"
        assert [i.title for i in state.queue] == list("ebcd")
        assert (await player.queue_remove(-1, 2)).title == "b"
        with pytest.raises(UserError):
            await player.queue_remove(-1, 9)
        assert await player.queue_shuffle(-1) == 3
        assert sorted(i.title for i in state.queue) == list("cde")
        assert await player.queue_clear(-1) == 3 and state.playback.item.title == "a"
        with pytest.raises(UserError):
            await player.queue_clear(-1)
    run(scenario())


def test_session_save_and_take_once(tmp_path):
    async def scenario():
        player, *_ = make_player(tmp_path)
        a = item("a", origin={"url": "https://youtu.be/xxxxxxxxxxx", "kind": AUDIO}, requested_by=ALI)
        b = item("b", origin={"chat": -5, "msg": 7, "kind": AUDIO})
        c = item("c")                                     # no origin: cannot be restored, not saved
        for it in (a, b, c):
            await player.enqueue(-1, "Group", it)
        player.store.get(-1).volume = 120
        player.store.get(-2).volume = 80                  # idle chat with a volume: saved too
        session = SessionFile(str(tmp_path / "session.json"))
        assert session.save(player.store) == 2
        chats = {c["chat"]: c for c in session.take()}
        assert chats[-1]["volume"] == 120 and len(chats[-1]["items"]) == 2
        assert chats[-1]["items"][0]["requested_by"] == {"id": 1, "name": "Ali"}
        assert chats[-2]["items"] == [] and chats[-2]["volume"] == 80
        assert session.take() == []                       # only once
    run(scenario())


def test_user_limiter():
    async def scenario():
        limiter = UserLimiter(1)
        async with limiter.slot(5):
            with pytest.raises(UserError):
                async with limiter.slot(5):
                    pass
            async with limiter.slot(5, exempt=True):     # bot owners
                pass
            async with limiter.slot(6):                   # other user
                pass
        async with limiter.slot(5):
            pass
    run(scenario())


def test_playlist_links():
    assert is_playlist("https://www.youtube.com/playlist?list=PL123")
    assert not is_playlist("https://www.youtube.com/watch?v=abcdefghijk&list=PL123")   # one video of a playlist
    assert not is_playlist("https://youtu.be/abcdefghijk?list=PL1")


def test_card_buttons():
    from core.models import ChatState, Playback
    from ui.buttons import keyboard
    state = ChatState(-100123)
    assert keyboard(state) is None                              # nothing plays: no buttons
    state.playback = Playback(item("a"))
    rows = keyboard(state).inline_keyboard
    assert rows[0][0].text == "⏸" and rows[0][0].callback_data == "vpb:pp:-100123"
    assert all(len(b.callback_data.encode()) <= 64 for row in rows for b in row)   # Telegram limit
    state.playback.pause()
    state.loop, state.volume = True, 140
    rows = keyboard(state).inline_keyboard
    assert rows[0][0].text == "▶️" and rows[0][3].text == "🔁 on" and rows[1][1].text == "🔊 140"
    state.playback = Playback(item("live", duration=None))
    assert not any(b.callback_data.startswith("vpb:l:") for b in keyboard(state).inline_keyboard[0])   # no loop for live
