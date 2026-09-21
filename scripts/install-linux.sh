#!/usr/bin/env bash
# Debian/Ubuntu source installer. Run as your normal desktop user, not via sudo.
set -euo pipefail
voice_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
voice_env="${XDG_DATA_HOME:-$HOME/.local/share}/voice-type/venv"
if [[ $EUID -eq 0 ]]; then
    echo 'Run this script as your normal user; sudo is used only for system packages.' >&2
    exit 1
fi
if ! command -v apt-get >/dev/null || ! command -v sudo >/dev/null; then
    echo 'This installer requires Debian/Ubuntu with apt-get and sudo. See docs/usage.md.' >&2
    exit 1
fi
mapfile -t voice_apt_packages < <(sed '/^[[:space:]]*#/d; /^[[:space:]]*$/d' "$voice_root/scripts/requirements-apt.txt")
sudo apt-get update
sudo apt-get install --yes --no-install-recommends "${voice_apt_packages[@]}"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is required")'
cd -- "$voice_root"
if [[ ! -e "$voice_env" ]]; then
    python3 -m venv "$voice_env"
fi
if [[ ! -x "$voice_env/bin/python" ]]; then
    echo 'Existing user environment is not usable; repair it before installing.' >&2
    exit 1
fi
"$voice_env/bin/python" -m pip install -r requirements.txt
"$voice_env/bin/voice-type-app" --check-audio
printf 'Installed. Start the desktop app with: %q\n' "$voice_env/bin/voice-type-app"
