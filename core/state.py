"""One ChatState per chat (replaces the many module-level dicts of the old stream.py)."""

from core.models import ChatState


class StateStore:
    def __init__(self):
        self._chats: dict[int, ChatState] = {}

    def get(self, chat_id: int) -> ChatState:
        state = self._chats.get(chat_id)
        if state is None:
            state = self._chats[chat_id] = ChatState(chat_id)
        return state

    def peek(self, chat_id: int) -> ChatState | None:
        return self._chats.get(chat_id)

    def active(self) -> list[ChatState]:
        return [s for s in self._chats.values() if s.active]
