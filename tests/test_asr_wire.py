"""Exercise our wire client against a local server; no cloud credentials/audio."""
import base64
import json
import threading
import time

import pytest
from websockets.sync.server import serve
from websockets.exceptions import ConnectionClosed

from voicetype.asr import QwenSession
from voicetype.settings import ENDPOINTS, Settings


@pytest.mark.parametrize("fail", [False, True])
def test_wire_and_error_propagation(monkeypatch, fail):
    received = []
    failures = []
    def handler(ws):
        try:
            assert ws.request.headers["Authorization"] == "Bearer fake-key"
            assert ws.request.path.endswith("?model=qwen3-asr-flash-realtime")
            for raw in ws:
                event = json.loads(raw)
                received.append(event)
                if event["type"] == "session.update":
                    ws.send(json.dumps({"type": "session.updated", "session": {}}))
                elif event["type"] == "input_audio_buffer.commit":
                    if fail:
                        ws.send(json.dumps({"type": "error", "error": {"message": "secret-value"}}))
                    else:
                        ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.text",
                                            "item_id": "one", "stash": "第一句。第二句。"}))
                        ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.completed",
                                            "item_id": "one", "transcript": "第一句。第二句。"}))
        except ConnectionClosed:
            pass
        except Exception as exc:
            failures.append(exc)
    with serve(handler, "127.0.0.1", 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setitem(ENDPOINTS, "中国大陆", f"ws://127.0.0.1:{server.socket.getsockname()[1]}")
        partials = []
        session = QwenSession(Settings(), "fake-key", partials.append)
        try:
            session.start()
            session.feed(b"\x00\x00" * 3200)
            if fail:
                with pytest.raises(RuntimeError, match="ASR 服务拒绝请求") as error:
                    session.finish()
                assert "secret-value" not in str(error.value)
            else:
                assert session.finish() == "第一句。第二句。"
                assert partials[-1] == "第一句。第二句。"
            assert received[0]["session"]["turn_detection"] is None
            assert received[0]["session"]["input_audio_format"] == "pcm"
            assert received[0]["session"]["sample_rate"] == 16000
            assert received[0]["session"]["input_audio_transcription"] == {"language": "zh"}
            chunk = next(e for e in received if e["type"] == "input_audio_buffer.append")
            assert len(base64.b64decode(chunk["audio"])) == 6400
        finally:
            session.close()
            assert not session.reader.is_alive()
            server.shutdown()
            thread.join(2)
        assert not failures


@pytest.mark.parametrize("phase", ["handshake", "final"])
def test_cancel_interrupts_network_wait(monkeypatch, phase):
    waiting = threading.Event()
    errors = []
    def handler(ws):
        try:
            for raw in ws:
                event = json.loads(raw)
                if event["type"] == "session.update":
                    if phase == "handshake":
                        waiting.set()
                    else:
                        ws.send(json.dumps({"type": "session.updated"}))
                elif event["type"] == "input_audio_buffer.commit":
                    waiting.set()  # Deliberately never return a final.
        except ConnectionClosed:
            pass
    with serve(handler, "127.0.0.1", 0) as server:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        monkeypatch.setitem(ENDPOINTS, "中国大陆", f"ws://127.0.0.1:{server.socket.getsockname()[1]}")
        session = QwenSession(Settings(), "fake-key", lambda _: None)
        def work():
            try:
                session.start()
                if phase == "final":
                    session.feed(b"\0\0" * 3200)
                    session.finish()
            except RuntimeError as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        try:
            assert waiting.wait(2)
            started = time.monotonic()
            session.close()
            worker.join(1)
            assert not worker.is_alive()
            assert not session.reader.is_alive()
            assert errors == ["识别已取消。"]
            assert time.monotonic() - started < 1
        finally:
            session.close()
            server.shutdown()
            server_thread.join(2)


def test_connect_errors_never_expose_credentials(monkeypatch):
    from voicetype import asr
    def fail(*args, **kwargs):
        raise OSError("Authorization: Bearer secret-key")
    monkeypatch.setattr(asr.websocket, "create_connection", fail)
    session = QwenSession(Settings(), "secret-key", lambda _: None)
    with pytest.raises(RuntimeError) as error:
        session.start()
    assert "secret-key" not in str(error.value)
    assert session.api_key == ""
    session.close()
