"""Install XDG launchers and start Voice Type in the current desktop session."""
import os
from pathlib import Path
import subprocess
import sys


def desktop_command(executable):
    # Desktop Entry Exec uses its own quoting, not shell quoting.
    value = str(executable).replace('%', '%%')
    if '\n' in value or '\r' in value:
        raise ValueError('The installation path must not contain line breaks.')
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, '\\' + character)
    return '"' + value.replace('\\', '\\\\') + '"'


def install(executable):
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'voice-type'
    command = '/usr/bin/env ' + desktop_command(executable)
    entry = (
        '[Desktop Entry]\nType=Application\nName=Voice Type\n'
        'Comment=Desktop voice dictation\nIcon=audio-input-microphone\n'
        'Terminal=false\nCategories=AudioVideo;Audio;\n'
    )
    for target, arguments in (
        (data / 'applications/voice-type.desktop', ''),
        (config / 'autostart/voice-type.desktop', ' --background'),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry + f'Exec={command}{arguments}\n', encoding='utf-8')
    print('Installed application menu entry and login autostart.')
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        print('No desktop session detected. Voice Type will start at the next desktop login.')
        return
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'app.log').open('ab') as log:
        subprocess.Popen([str(executable), '--background'], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True, cwd=Path.home())
    print(f'Voice Type launch requested. Log: {state / "app.log"}')


if __name__ == '__main__':
    install(Path(sys.argv[1]).resolve())
