#!/usr/bin/env bash
# Debian/Ubuntu source installer. Run as your normal desktop user, not via sudo.
set -euo pipefail
voice_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $EUID -eq 0 ]]; then
    echo 'Run this script as your normal user; sudo is used only for system packages.' >&2
    exit 1
fi
if ! command -v apt-get >/dev/null || ! command -v sudo >/dev/null; then
    echo 'This installer requires Debian/Ubuntu with apt-get and sudo. See DESKTOP.md.' >&2
    exit 1
fi
mapfile -t voice_apt_packages < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$voice_root/requirements-apt.txt")
sudo apt-get update
sudo apt-get install --yes --no-install-recommends "${voice_apt_packages[@]}"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is required")'
cd -- "$voice_root"
if [[ ! -e .venv ]]; then
    python3 -m venv .venv
fi
if [[ ! -x .venv/bin/python ]]; then
    echo 'Existing .venv is not usable; select a clean checkout or repair the environment.' >&2
    exit 1
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/voice-type-app --check-audio
printf 'Installed. Start the desktop app with: %q\n' "$voice_root/.venv/bin/voice-type-app"
