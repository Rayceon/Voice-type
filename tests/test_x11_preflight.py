"""Preflight must reject missing ELF dependencies even when ldd exits successfully."""
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("scenario", ["success", "missing-library", "ldd-error", "plugin-error", "missing-plugin"])
def test_x11_preflight(monkeypatch, tmp_path, capsys, scenario):
    script = Path(__file__).resolve().parents[1] / "scripts/check_x11.py"
    module = runpy.run_path(str(script))
    (tmp_path / "platforms").mkdir()
    if scenario != "missing-plugin":
        (tmp_path / "platforms/libqxcb.so").touch()
    monkeypatch.setattr(module["QLibraryInfo"], "path", lambda _: str(tmp_path))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "ldd":
            return SimpleNamespace(returncode=int(scenario == "ldd-error"), stderr="",
                                   stdout="libxcb-icccm.so.4 => not found" if scenario == "missing-library" else "")
        assert kwargs["env"]["QT_QPA_PLATFORM"] == "xcb"
        assert kwargs["env"]["QT_DEBUG_PLUGINS"] == "1"
        return SimpleNamespace(returncode=-6 if scenario == "plugin-error" else 0,
                               stdout="", stderr="plugin loader details")

    monkeypatch.setattr(module["subprocess"], "run", run)
    assert module["main"]() == int(scenario != "success")
    assert len(calls) == (0 if scenario == "missing-plugin" else 1 if scenario in {"missing-library", "ldd-error"} else 2)
    output = capsys.readouterr()
    if scenario == "missing-library":
        assert "libxcb-icccm.so.4 => not found" in output.err
    if scenario == "plugin-error":
        assert "plugin loader details" in output.err
