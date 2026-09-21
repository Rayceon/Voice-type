"""The build wrapper stages input and leaves generated files outside the checkout."""
from pathlib import Path
import runpy
import subprocess
import sys

import platformdirs
import pytest


@pytest.mark.parametrize("fail", [0, 1, 4])
def test_build_uses_disposable_external_source(monkeypatch, tmp_path, fail):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "output"
    monkeypatch.setattr(platformdirs, "user_cache_path", lambda *a, **k: tmp_path / "cache")
    monkeypatch.setattr(sys, "argv", ["build.py", "--output", str(output)])
    monkeypatch.setenv("LD_LIBRARY_PATH", "build-only-libraries")
    calls = []

    def run(command, *, cwd, env, check):
        cwd = Path(cwd)
        calls.append((command, cwd))
        assert check and env["PYTHONDONTWRITEBYTECODE"] == "1"
        if len(calls) <= 2:
            assert cwd != root and cwd.is_relative_to(tmp_path)
            assert (cwd / "packaging/voice-type.spec").is_file()
            assert (cwd / "src/voicetype/app.py").is_file()
            assert not (cwd / ".venv").exists()
            assert not (cwd / "config.py").exists()
            assert not list(cwd.rglob("*.egg-info"))
        if len(calls) == 4:
            assert command[-1] == "--check-tls"
            assert "LD_LIBRARY_PATH" not in env
        if len(calls) == fail:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            runpy.run_path(str(root / "scripts/build.py"), run_name="__main__")
    else:
        runpy.run_path(str(root / "scripts/build.py"), run_name="__main__")
        assert len(calls) == 4
        assert str(output) in calls[0][0] and str(output) in calls[1][0]
        assert calls[2][1] == root
    assert not calls[0][1].exists()
