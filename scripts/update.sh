#!/usr/bin/env bash
# Updates yt-dlp in the venv (YouTube changes often), runs the tests, restarts the service.
#   ./scripts/update.sh          only yt-dlp
#   ./scripts/update.sh --all    every package of requirements.txt to its newest version (re-test before keeping it!)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
mkdir -p ~/backups && tar --exclude=.venv --exclude=downloads -czf ~/backups/VideoPlayerBot-$(date +%Y%m%d-%H%M%S)-pre-update.tar.gz .
if [ "${1:-}" = "--all" ]; then
    uv pip install --python .venv/bin/python -U -r <(sed -E 's/==.*//' requirements.txt)
else
    uv pip install --python .venv/bin/python -U "yt-dlp[default]"
fi
.venv/bin/python -m pytest -q tests
.venv/bin/python -c "import yt_dlp, pytgcalls; print('yt-dlp', yt_dlp.version.__version__, '· py-tgcalls', pytgcalls.__version__)"
systemctl restart videoplayerbot && sleep 5 && systemctl is-active videoplayerbot
