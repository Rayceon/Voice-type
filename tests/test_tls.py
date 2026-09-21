"""TLS diagnostics must fail closed without recording, networking or leaking keys."""
import builtins
import sys

import pytest

from voicetype import app, asr
from voicetype.settings import Settings


@pytest.mark.parametrize("failure", ["import", "certificate"])
def test_tls_failure_is_distinct_and_prevents_connection(monkeypatch, failure):
    if failure == "import":
        original = builtins.__import__
        def import_module(name, *args, **kwargs):
            if name == "ssl":
                raise ImportError("OPENSSL symbol missing: private-detail")
            return original(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", import_module)
    else:
        monkeypatch.setattr(asr.certifi, "where", lambda: "/nonexistent-voice-type-ca.pem")
    monkeypatch.setattr(asr.websocket, "create_connection", lambda *a, **k: pytest.fail("no network"))
    session = asr.QwenSession(Settings(), "private-key", lambda _: None)
    with pytest.raises(RuntimeError, match="TLS 加密组件") as error:
        session.start()
    assert "private-detail" not in str(error.value)
    assert session.api_key == ""


@pytest.mark.parametrize("failure", [False, True])
def test_offline_tls_cli(monkeypatch, capsys, failure):
    monkeypatch.setattr(sys, "argv", ["VoiceType", "--check-tls"])
    monkeypatch.setattr(app, "QApplication", lambda *_: pytest.fail("no GUI"))
    monkeypatch.setattr(app, "Credentials", lambda: pytest.fail("no credential access"))
    monkeypatch.setattr(asr.websocket, "create_connection", lambda *a, **k: pytest.fail("no network"))
    if failure:
        monkeypatch.setattr(asr.certifi, "where", lambda: "/nonexistent-voice-type-ca.pem")
    assert app.main() == int(failure)
    output = capsys.readouterr()
    assert ("Connection check failed" in output.err) if failure else ("TLS OK" in output.out)


@pytest.mark.parametrize("outcome", ["success", "missing", "error"])
def test_asr_cli_only_handshakes_and_closes(monkeypatch, capsys, outcome):
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(sys, "argv", ["VoiceType", "--check-asr"])
    monkeypatch.setattr(app, "QApplication", lambda *_: pytest.fail("no GUI"))
    monkeypatch.setattr(app, "audio_backend", lambda: pytest.fail("no microphone"))
    monkeypatch.setattr(app, "Credentials", lambda: SimpleNamespace(get=lambda: "" if outcome == "missing" else "private-key"))
    monkeypatch.setattr(app, "load", Settings)

    class Session:
        def __init__(self, settings, key, partial):
            assert key == "private-key"
        def start(self):
            calls.append("start")
            if outcome == "error":
                raise RuntimeError("private-key")
        def close(self):
            calls.append("close")

    monkeypatch.setattr(asr, "QwenSession", Session)
    assert app.main() == int(outcome != "success")
    assert calls == ([] if outcome == "missing" else ["start", "close"])
    output = capsys.readouterr()
    assert "private-key" not in output.out + output.err
