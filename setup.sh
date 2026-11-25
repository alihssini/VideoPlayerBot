#!/usr/bin/env bash
# Sets up the Python 3.12 virtualenv with all dependencies (Debian/Ubuntu).
set -euo pipefail
cd "$(dirname "$0")"
# build-essential: tgcrypto has no wheel for Python 3.12 and is compiled
# ffmpeg (with libass: lyrics videos), fontconfig + a Persian/Arabic capable font (Vazirmatn) for the lyrics
apt-get update
apt-get install -y build-essential ffmpeg git curl fontconfig fonts-dejavu-core libfribidi0 libharfbuzz0b libraqm0 moreutils jq || apt-get install -y build-essential ffmpeg git curl fontconfig fonts-dejavu-core libfribidi0 libharfbuzz0b moreutils jq
if ! apt-get install -y fonts-vazirmatn; then  # not in every distribution release: download the font instead
    mkdir -p assets/fonts
    curl -fsSL -o assets/fonts/Vazirmatn-Regular.ttf https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Regular.ttf \
        || echo "[WARN] Could not get the Vazirmatn font: put any Persian-capable .ttf into assets/fonts and set LYRICS_FONT in .env"
fi
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
uv venv --allow-existing --python 3.12 .venv   # re-runnable
. .venv/bin/activate
uv pip install -r requirements.txt
[ -f .env ] || cp .env.sample .env
chmod 600 .env
mkdir -p data/acl/groups sessions && chmod 700 data data/acl sessions
if [ "${1:-}" = "--with-service" ]; then
    sed "s#/root/VideoPlayerBot#$(pwd)#g" deploy/videoplayerbot.service > /etc/systemd/system/videoplayerbot.service
    systemctl daemon-reload && systemctl enable videoplayerbot
fi
echo "Done. Next: fill in .env (API_ID, API_HASH, OWNER_USERS), then log in once: .venv/bin/python login.py"
