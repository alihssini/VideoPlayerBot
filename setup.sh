#!/usr/bin/env bash
# Sets up the Python 3.12 virtualenv with all dependencies (Debian/Ubuntu).
set -euo pipefail
cd "$(dirname "$0")"
# ffmpeg (with libass: lyrics videos), fontconfig + a Persian/Arabic capable font (Vazirmatn) for the lyrics
apt-get install -y ffmpeg git curl fontconfig fonts-dejavu-core
if ! apt-get install -y fonts-vazirmatn; then  # not in every distribution release: download the font instead
    mkdir -p assets/fonts
    curl -fsSL -o assets/fonts/Vazirmatn-Regular.ttf https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Regular.ttf \
        || echo "[WARN] Could not get the Vazirmatn font: put any Persian-capable .ttf into assets/fonts and set LYRICS_FONT in .env"
fi
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
uv venv --python 3.12 .venv
. .venv/bin/activate
uv pip install -r requirements.txt
[ -f .env ] || cp .env.sample .env
echo "Done. Next: fill in .env (API_ID, API_HASH, SUDO_USERS, OWNER_USERS), then log in once: .venv/bin/python login.py"
