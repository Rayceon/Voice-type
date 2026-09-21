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
        spec = Path(__file__).resolve().parents[1] / "packaging/voice-type.spec"
        with pytest.raises(Collected) as captured:
            runpy.run_path(str(spec), init_globals={"Analysis": analysis, "SPECPATH": str(spec.parent)})
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


def test_stdlib_notice_preferred_over_distributor_license(spec_notices):
    prefix, stdlib, collect = spec_notices
    (prefix / "LICENSE.txt").write_text("distributor license", encoding="utf-8")
    notice = stdlib / "LICENSE.txt"
    notice.write_text("Python license", encoding="utf-8")
    assert (str(notice), "licenses/python") in collect()


def test_copyleft_notice_directory_is_bundled(spec_notices):
    (spec_notices[0] / "LICENSE.txt").write_text("test Python license", encoding="utf-8")
    assert (str(Path(__file__).resolve().parents[1] / "licenses"), "licenses") in spec_notices[2]()


def test_missing_linux_portaudio_blocks_build(spec_notices, monkeypatch):
    from types import SimpleNamespace
    (spec_notices[0] / "LICENSE.txt").write_text("test Python license", encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "linux")
    spec = Path(__file__).resolve().parents[1] / "packaging/voice-type.spec"
    with pytest.raises(RuntimeError, match="PortAudio"):
        runpy.run_path(str(spec), init_globals={
            "Analysis": lambda *args, **kwargs: SimpleNamespace(binaries=[]),
            "SPECPATH": str(spec.parent),
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
    root = Path(__file__).resolve().parents[1]
    for name in ("README.md", "SECURITY.md"):
        assert (str(root / name), ".") in notices
    assert (str(root / "docs"), "docs") in notices


def test_linux_bundle_pins_interpreter_openssl(spec_notices, monkeypatch):
    from types import SimpleNamespace
    from PyInstaller.depend import bindepend
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(bindepend, "get_imports", lambda _: {
        ("libssl.so.3", "/runtime/libssl.so.3"),
        ("libcrypto.so.3", "/runtime/libcrypto.so.3"),
    })
    (spec_notices[0] / "LICENSE.txt").write_text("Python license", encoding="utf-8")
    captured = {}

    def analysis(*args, **kwargs):
        captured["inputs"] = kwargs["binaries"]
        return SimpleNamespace(pure=[], scripts=[], datas=[], binaries=[
            ("libssl.so.3", "/system/libssl.so.3", "BINARY"),
            ("libcrypto.so.3", "/system/libcrypto.so.3", "BINARY"),
            ("libportaudio.so.2", "/system/libportaudio.so.2", "BINARY"),
        ])

    def collect(exe, binaries, datas, **kwargs):
        captured["outputs"] = binaries

    spec = Path(__file__).resolve().parents[1] / "packaging/voice-type.spec"
    runpy.run_path(str(spec), init_globals={
        "SPECPATH": str(spec.parent), "Analysis": analysis,
        "PYZ": lambda *a, **k: None, "EXE": lambda *a, **k: None, "COLLECT": collect,
    })
    assert set(captured["inputs"]) == {("/runtime/libssl.so.3", "."), ("/runtime/libcrypto.so.3", ".")}
    assert captured["outputs"][:2] == [
        ("libssl.so.3", "/runtime/libssl.so.3", "BINARY"),
        ("libcrypto.so.3", "/runtime/libcrypto.so.3", "BINARY"),
    ]


def test_unresolved_tls_dependency_blocks_build(spec_notices, monkeypatch):
    from PyInstaller.depend import bindepend
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(bindepend, "get_imports", lambda _: {("libssl.so.3", None)})
    (spec_notices[0] / "LICENSE.txt").write_text("Python license", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Cannot resolve Python TLS"):
        spec_notices[2]()
