"""The py-tgcalls (ntgcalls) voice chat engine bound to the user-account client."""

from pytgcalls import PyTgCalls
from helpers.user import User

call_py = PyTgCalls(User)
