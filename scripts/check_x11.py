"""Linux CI preflight: report missing Qt libraries, then load xcb on an isolated X server."""
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QLibraryInfo


def main():
    plugin = Path(QLibraryInfo.path(QLibraryInfo.PluginsPath)) / "platforms/libqxcb.so"
    if not plugin.is_file():
        print(f"Qt xcb plugin missing: {plugin}", file=sys.stderr)
        return 1
    result = subprocess.run(["ldd", str(plugin)], capture_output=True, text=True, timeout=15)
    if result.returncode or "not found" in result.stdout + result.stderr:
        print(result.stdout + result.stderr, file=sys.stderr)
        print("Install scripts/requirements-apt.txt before X11 tests.", file=sys.stderr)
        return 1
    # Qt's generic cursor warning can hide another missing library. Preserve the
    # plugin loader's real error instead of repeating it for every input test.
    env = dict(os.environ, QT_QPA_PLATFORM="xcb", QT_DEBUG_PLUGINS="1")
    result = subprocess.run([
        sys.executable, "-c",
        "from PySide6.QtWidgets import QApplication; "
        "app = QApplication([]); assert app.platformName() == 'xcb'",
    ], env=env, capture_output=True, text=True, timeout=15)
    if result.returncode:
        print(result.stdout + result.stderr, file=sys.stderr)
        return 1
    print("Qt xcb preflight OK: libraries resolved and platform initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
