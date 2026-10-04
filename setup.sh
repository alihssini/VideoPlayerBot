#!/usr/bin/env bash
# Sets up the Python 3.12 virtualenv with all dependencies (Debian/Ubuntu).
set -euo pipefail
cd "$(dirname "$0")"
apt-get install -y ffmpeg git curl
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
uv venv --python 3.12 .venv
. .venv/bin/activate
uv pip install -r requirements.txt
[ -f .env ] || cp .env.sample .env
echo "Done. Next: fill in .env (API_ID, API_HASH, SUDO_USERS), then log in once: .venv/bin/python login.py"
