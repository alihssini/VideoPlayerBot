"""
One-time interactive login of the Telegram user account.

Run:  .venv/bin/python login.py
Telegram sends a login code to your Telegram app (or SMS); enter it here, plus your
2FA password if you have one. The session is saved in ./sessions and reused by main.py.
"""

import os
from helpers.user import User, SESSION_FILE


def main():
    if os.path.isfile(SESSION_FILE):
        print(f"[INFO] - Existing session found ({SESSION_FILE}), verifying it ...")
    else:
        print("[INFO] - Starting login. Telegram will send a code to your account.")
    User.start()
    me = User.get_me()
    print(f"[OK] - Logged in as {me.first_name} (id {me.id}, @{me.username}). Session saved to {SESSION_FILE}")
    User.stop()


if __name__ == "__main__":
    main()
