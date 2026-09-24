"""Check installed desktop entries without changing the user's desktop or packages."""
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux desktop installer')


@pytest.mark.parametrize('session', ['x11', 'wayland', 'headless'])
def test_desktop_install_is_repeatable_and_starts_only_in_session(tmp_path, monkeypatch, session):
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/install-desktop.py'))
    for kind in ('DATA', 'CONFIG', 'STATE'):
        monkeypatch.setenv(f'XDG_{kind}_HOME', str(tmp_path / kind.lower()))
    monkeypatch.delenv('DISPLAY', raising=False)
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    if session != 'headless':
        monkeypatch.setenv('DISPLAY' if session == 'x11' else 'WAYLAND_DISPLAY', ':isolated')
    calls = []
    popen = subprocess.Popen
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: calls.append((args, kwargs)))
    executable = tmp_path / 'path with spaces/voice-type-app'
    for _ in range(2):
        module['install'](executable)
    monkeypatch.setattr(subprocess, 'Popen', popen)
    entry = (tmp_path / 'data/applications/voice-type.desktop').read_text()
    autostart = (tmp_path / 'config/autostart/voice-type.desktop').read_text()
    assert f'Exec=/usr/bin/env "{executable}"\n' in entry
    assert f'Exec=/usr/bin/env "{executable}" --background\n' in autostart
    assert 'Terminal=false' in entry
    if shutil.which('desktop-file-validate'):
        result = subprocess.run(['desktop-file-validate',
                                 str(tmp_path / 'data/applications/voice-type.desktop'),
                                 str(tmp_path / 'config/autostart/voice-type.desktop')],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stdout
    assert len(calls) == (0 if session == 'headless' else 2)
    for args, kwargs in calls:
        assert args == ([str(executable), '--background'],)
        assert kwargs['start_new_session'] and kwargs['stdin'] == subprocess.DEVNULL
    assert len(list((tmp_path / 'config/autostart').iterdir())) == 1


def test_desktop_command_round_trips_special_path(tmp_path):
    # Let the desktop's actual GLib parser resolve Exec, rather than mirror its escaping.
    executable = tmp_path / 'space $cash `tick` "quote" %field% \\slash'
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/install-desktop.py'))
    marker = tmp_path / 'launched'
    executable.write_text('#!/usr/bin/python3\nfrom pathlib import Path\n' + f'Path({str(marker)!r}).write_text("launched")\n')
    executable.chmod(0o700)
    entry = tmp_path / 'voice-type.desktop'
    entry.write_text('[Desktop Entry]\nType=Application\nName=Test\nExec=/usr/bin/env ' + module['desktop_command'](executable) + '\n')
    # Ubuntu's system Python has PyGObject; skip this extra platform check elsewhere.
    probe = subprocess.run(['/usr/bin/python3', '-c', 'from gi.repository import Gio'], capture_output=True) if os.path.exists('/usr/bin/python3') else None
    if probe is None or probe.returncode:
        pytest.skip('GLib desktop parser is unavailable')
    result = subprocess.run(['/usr/bin/python3', '-c',
        'from gi.repository import Gio; import sys; app = Gio.DesktopAppInfo.new_from_filename(sys.argv[1]); app.launch([], None)',
        str(entry)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    deadline = time.monotonic() + 3
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.read_text() == 'launched'


def test_desktop_command_rejects_line_breaks():
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/install-desktop.py'))
    with pytest.raises(ValueError, match='line breaks'):
        module['desktop_command']('/tmp/invalid\nExec=other')


def test_make_install_reuses_environment_and_installed_system_packages(tmp_path):
    if os.name != 'posix' or not Path('/usr/bin/make').exists() or os.geteuid() == 0:
        pytest.skip('Requires make and a non-root POSIX user')
    root = Path(__file__).resolve().parents[1]
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    log = tmp_path / 'commands'
    env_dir = tmp_path / 'data/voice-type/venv/bin'
    env_dir.mkdir(parents=True)
    for path, body in [
        (binaries / 'dpkg-query', 'echo installed'),
        (binaries / 'sudo', 'exit 99'),
        (binaries / 'apt-get', 'exit 99'),
        (binaries / 'python3', 'exit 0'),
        (env_dir / 'python', 'printf "%s\\n" "$*" >> "$INSTALL_TEST_LOG"'),
        (env_dir / 'voice-type-app', 'printf "%s\\n" "$*" >> "$INSTALL_TEST_LOG"'),
    ]:
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o700)
    env = dict(os.environ, PATH=str(binaries) + os.pathsep + os.defpath,
               XDG_DATA_HOME=str(tmp_path / 'data'), INSTALL_TEST_LOG=str(log))
    result = subprocess.run(['make', 'install'], cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    commands = log.read_text().splitlines()
    assert commands[:2] == ['-m pip install -r requirements.txt', '--check-audio']
    assert commands[2] == f'{root}/scripts/install-desktop.py {env_dir}/voice-type-app'
