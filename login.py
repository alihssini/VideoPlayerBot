"""
One-time interactive login of the Telegram user account.

Run:  .venv/bin/python login.py
Telegram sends a login code to your Telegram app (or SMS); enter it here, plus your
2FA password if you have one. The session is saved in ./sessions (mode 0600) and reused by main.py.
"""

import os
from app.client import SESSION_FILE, make_client


def main():
    client, _ = make_client()
    print(f"[INFO] - {'Existing session found, verifying it' if os.path.isfile(SESSION_FILE) else 'Starting login. Telegram will send a code to your account'} ...")
    client.start()
    me = client.get_me()
    print(f"[OK] - Logged in as {me.first_name} (id {me.id}, @{me.username}). Session saved to {SESSION_FILE}")
    client.stop()
    for name in os.listdir(os.path.dirname(SESSION_FILE)):
        os.chmod(os.path.join(os.path.dirname(SESSION_FILE), name), 0o600)


if __name__ == "__main__":
    main()
