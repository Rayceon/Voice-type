import ctypes.util
import runpy
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("platform,present", [("linux", True), ("linux", False), ("darwin", True)])
def test_frozen_portaudio_lookup(monkeypatch, tmp_path, platform, present):
    library = tmp_path / "libportaudio.so.2"
    if present:
        library.touch()
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    original = lambda name: "system:" + name
    monkeypatch.setattr(ctypes.util, "find_library", original)
    hook = Path(__file__).resolve().parents[1] / "pyi_rth_portaudio.py"
    runpy.run_path(str(hook))
    expected = str(library) if platform == "linux" and present else "system:portaudio"
    assert ctypes.util.find_library("portaudio") == expected
    assert ctypes.util.find_library("other") == "system:other"


def test_audio_check_does_not_open_window_or_record(monkeypatch, capsys):
    from types import SimpleNamespace
    from voicetype import app
    monkeypatch.setattr(sys, "argv", ["VoiceType", "--check-audio"])
    monkeypatch.setattr(app, "QApplication", lambda *_: pytest.fail("must not open a GUI"))
    backend = SimpleNamespace(get_portaudio_version=lambda: (1, "test PortAudio"), _libname="bundled.so")
    monkeypatch.setattr(app, "audio_backend", lambda: backend)
    monkeypatch.setattr(app, "list_inputs", lambda: [])
    assert app.main() == 0  # A headless machine may legitimately have no microphone.
    assert "Input devices: 0" in capsys.readouterr().out


def test_audio_check_failure_is_nonzero(monkeypatch, capsys):
    from voicetype import app
    monkeypatch.setattr(sys, "argv", ["VoiceType", "--check-audio"])
    monkeypatch.setattr(app, "QApplication", lambda *_: pytest.fail("must not open a GUI"))
    def unavailable():
        raise RuntimeError("missing audio library")
    monkeypatch.setattr(app, "audio_backend", unavailable)
    assert app.main() == 1
    assert "missing audio library" in capsys.readouterr().err
