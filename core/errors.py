"""Exceptions that carry a message for the user. Handlers raise them, the command wrapper (ui/replies.py) answers."""


class UserError(Exception):
    """Something the user can fix; the text (markdown) is shown as it is, prefixed with ❌."""


class Silent(Exception):
    """Stop handling without any answer (e.g. a stranger used a command in a group)."""


class NoVoiceChat(UserError):
    def __init__(self):
        super().__init__("**There is no active voice chat in this group**, start one first!")
