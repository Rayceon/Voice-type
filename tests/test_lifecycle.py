"""Exercise actual process startup, singleton activation, and tray shutdown."""
import os
from pathlib import Path
import subprocess
import sys


def test_background_process_reopens_and_exits_from_tray(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', VOICE_TYPE_TEST_CONFIG=str(tmp_path),
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    scenario = r'''
import subprocess
import sys
import os
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from voicetype import app as desktop

desktop.config_path = lambda: Path(os.environ['VOICE_TYPE_TEST_CONFIG']) / 'settings.json'
path = desktop.config_path()
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text('{}')
desktop.list_inputs = lambda: []
desktop.resolve_input = lambda *args: None
desktop.Credentials.get = lambda self: 'fake-key'
desktop.QSystemTrayIcon.isSystemTrayAvailable = lambda: True
calls = []
desktop.GlobalTrigger = lambda *args: SimpleNamespace(
    start=lambda: calls.append('start'), stop=lambda: calls.append('stop'))
failures = []
original = desktop.Window

def create_window():
    window = original()
    def exercise():
        try:
            assert not desktop.QApplication.instance().quitOnLastWindowClosed()
            assert not window.isVisible() and window.listener is not None
            for arguments, visible in [([], True), (['--background'], False), ([], True)]:
                client = ('import os; from pathlib import Path; from voicetype import app; '
                          'app.config_path = lambda: Path(os.environ["VOICE_TYPE_TEST_CONFIG"]) / "settings.json"; '
                          'raise SystemExit(app.main())')
                result = subprocess.run([sys.executable, '-c', client, *arguments],
                                        capture_output=True, text=True, timeout=5)
                assert result.returncode == 0, result.stderr
                QTest.qWait(50)
                assert window.isVisible() == visible
                window.close()
                assert not window.quitting and window.listener is not None
            window.tray.contextMenu().actions()[-1].trigger()
            assert window.quitting and window.listener is None
        except BaseException as exc:
            failures.append(repr(exc))
            window.quit()
    QTimer.singleShot(50, exercise)
    return window

desktop.Window = create_window
sys.argv = ['voice-type-app', '--background']
assert desktop.main() == 0
assert not failures, failures
assert calls == ['start', 'stop'], calls
assert not (path.parent / 'app.lock').exists()
'''
    result = subprocess.run([sys.executable, '-c', scenario], env=env, capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 0, result.stderr
