"""Exercise the real spec's notice collection without building binaries."""
import runpy
import sys
import sysconfig
from pathlib import Path

import pytest
from PyInstaller.utils import hooks


@pytest.fixture
def spec_notices(monkeypatch, tmp_path):
    prefix, stdlib = tmp_path / "python", tmp_path / "stdlib"
    prefix.mkdir()
    stdlib.mkdir()
    monkeypatch.setattr(sys, "base_prefix", str(prefix))
    monkeypatch.setattr(sysconfig, "get_path", lambda name: str(stdlib))
    for name in ("collect_data_files", "collect_submodules", "copy_metadata"):
        monkeypatch.setattr(hooks, name, lambda *args, **kwargs: [])

    class Collected(Exception):
        pass

    def analysis(*args, **kwargs):
        raise Collected(kwargs["datas"])

    def collect():
        spec = Path(__file__).resolve().parents[1] / "voice-type.spec"
        with pytest.raises(Collected) as captured:
            runpy.run_path(str(spec), init_globals={"Analysis": analysis})
        return captured.value.args[0]

    return prefix, stdlib, collect


@pytest.mark.parametrize("location,name", [
    (0, "LICENSE.txt"), (0, "LICENSE_PYTHON.txt"), (1, "LICENSE.txt"),
])
def test_python_notice_collected_from_runtime_layout(spec_notices, location, name):
    notice = spec_notices[location] / name
    notice.write_text("test Python license", encoding="utf-8")
    assert (str(notice), "licenses/python") in spec_notices[2]()


def test_missing_python_notice_blocks_bundle(spec_notices):
    with pytest.raises(RuntimeError, match="Python license"):
        spec_notices[2]()


def test_copyleft_notice_directory_is_bundled(spec_notices):
    (spec_notices[0] / "LICENSE.txt").write_text("test Python license", encoding="utf-8")
    assert ("licenses", "licenses") in spec_notices[2]()


def test_missing_linux_portaudio_blocks_build(spec_notices, monkeypatch):
    from types import SimpleNamespace
    (spec_notices[0] / "LICENSE.txt").write_text("test Python license", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "linux")
    spec = Path(__file__).resolve().parents[1] / "voice-type.spec"
    with pytest.raises(RuntimeError, match="PortAudio"):
        runpy.run_path(str(spec), init_globals={
            "Analysis": lambda *args, **kwargs: SimpleNamespace(binaries=[]),
        })


@pytest.mark.parametrize("filename,contents", [
    (".env", b"example"), ("settings.json", b"{}"), (".venv/file", b""),
    ("voice_type.py", b""), ("audio.wav", b""), ("__pycache__/file.pyc", b""),
    ("../escape", b""), ("/absolute", b""),
    ("config.txt", b"sk-" + b"x" * 32),
    ("config.txt", b"/home/" + b"example/private"),
])
def test_release_audit_rejects_local_or_private_files(filename, contents):
    audit = runpy.run_path(str(Path(__file__).with_name("check_distribution.py")))["audit"]
    files = {"voicetype/app.py": b"", "example.dist-info/METADATA": b"# Voice Type",
             "example.dist-info/licenses/LICENSE": b"MIT"}
    audit(files, source=False)
    with pytest.raises(AssertionError):
        audit({**files, filename: contents}, source=False)


def test_public_usage_and_security_docs_are_bundled(spec_notices):
    (spec_notices[0] / "LICENSE.txt").write_text("test Python license", encoding="utf-8")
    notices = spec_notices[2]()
    for name in ("README.md", "DESKTOP.md", "LEGACY.md", "SECURITY.md", "THIRD_PARTY.md"):
        assert (name, ".") in notices
