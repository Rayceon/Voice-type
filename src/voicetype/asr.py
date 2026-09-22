"""Self-contained Qwen realtime ASR session; one key-hold = one manual commit."""
from __future__ import annotations

import base64
from collections import OrderedDict
import json
import threading
from urllib.parse import urlencode
from uuid import uuid4

import certifi
import websocket

from .settings import ENDPOINTS, Settings


def check_tls() -> str:
    """Offline check of the real TLS extension and bundled trust store."""
    try:
        import ssl
        ssl.create_default_context(cafile=certifi.where())
        return ssl.OPENSSL_VERSION
    except Exception:
        raise RuntimeError("TLS 加密组件或证书加载失败，请重新安装完整程序；这不是 API Key 错误。") from None


class Transcript:
    """Keep all items in server order and replace partials with authoritative finals."""

    def __init__(self):
        self.items: OrderedDict[str, str] = OrderedDict()
        self.finalized: set[str] = set()
        self.sequence = 0

    def update(self, event: dict) -> str:
        kind = event.get("type", "")
        item = event.get("item_id") or f"anonymous-{self.sequence}"
        if kind.endswith(".completed"):
            self.items[item] = event.get("transcript") or ""
            self.finalized.add(item)
            if not event.get("item_id"):
                self.sequence += 1
        elif item not in self.finalized:
            self.items[item] = (event.get("text") or "") + (event.get("stash") or "")
        return self.text

    @property
    def text(self) -> str:
        return "".join(self.items.values()).strip()


class QwenSession:
    def __init__(self, settings: Settings, api_key: str, partial):
        self.settings = settings
        self.partial = partial
        self.ready = threading.Event()
        self.done = threading.Event()
        self.transcript = Transcript()
        self.lock = threading.Lock()
        self.error = ""
        self.closing = False
        self.api_key = api_key
        self.ws = None
        self.reader = None
        self.lifecycle = threading.Lock()

    def on_close(self, *args):
        if not self.closing and not self.done.is_set():
            self.error = "识别连接意外断开，请检查网络后重试。"
            self.ready.set()
            self.done.set()

    def on_event(self, event: dict):
        if self.closing:
            return
        kind = event.get("type", "")
        if kind == "session.updated":
            self.ready.set()
        elif kind in {"error", "conversation.item.input_audio_transcription.failed"}:
            # Do not propagate provider error bodies: they may contain request credentials.
            self.error = "ASR 服务拒绝请求，请检查 API Key、服务区域、模型和账户额度。"
            self.ready.set()
            self.done.set()
        elif kind in {"conversation.item.input_audio_transcription.text",
                      "conversation.item.input_audio_transcription.completed"}:
            with self.lock:
                text = self.transcript.update(event)
            self.partial(text)
            if kind.endswith(".completed"):
                self.done.set()

    def start(self):
        self.check_error()
        try:
            check_tls()
        except RuntimeError:
            self.api_key = ""
            raise
        url = ENDPOINTS[self.settings.region] + "?" + urlencode({"model": self.settings.model})
        try:
            ws = websocket.create_connection(
                url, header={"Authorization": "Bearer " + self.api_key},
                timeout=8, enable_multithread=True, redirect_limit=0,
                http_proxy_timeout=8, sslopt={"ca_certs": certifi.where()},
            )
        except Exception:
            raise RuntimeError("ASR 连接失败，请检查网络、API Key 和服务区域。") from None
        finally:
            self.api_key = ""
        with self.lifecycle:
            if self.closing:
                ws.shutdown()
                raise RuntimeError("识别已取消。")
            self.ws = ws
            self.reader = threading.Thread(target=self._receive, args=(ws,), daemon=True,
                                           name="voice-type-asr")
            self.reader.start()
        transcription = {"language": self.settings.language}
        if self.settings.hotwords.strip():
            transcription["corpus"] = {"text": self.settings.hotwords.strip()}
        self._send("session.update", session={
            "modalities": ["text"], "input_audio_format": "pcm", "sample_rate": 16000,
            "input_audio_transcription": transcription,
            "turn_detection": None,
        })
        if not self.ready.wait(8):
            raise RuntimeError("ASR 握手超时，请检查网络和服务区域。")
        self.check_error()

    def check_error(self):
        if self.closing:
            raise RuntimeError("识别已取消。")
        if self.error:
            raise RuntimeError(self.error)

    def _receive(self, ws):
        try:
            while not self.closing:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue  # Silence while holding the key is normal.
                if not raw:
                    break
                event = json.loads(raw)
                if not isinstance(event, dict):
                    raise ValueError("Invalid ASR event")
                self.on_event(event)
        except Exception:
            # Neither transport exceptions nor response bodies may expose secrets.
            pass
        finally:
            self.on_close()

    def _send(self, kind, **payload):
        self.check_error()
        try:
            self.ws.send(json.dumps({"event_id": "event_" + uuid4().hex,
                                     "type": kind, **payload}))
        except Exception:
            raise RuntimeError("ASR 发送失败，请检查网络后重试。") from None

    def feed(self, pcm: bytes):
        self._send("input_audio_buffer.append", audio=base64.b64encode(pcm).decode("ascii"))

    def finish(self) -> str:
        self._send("input_audio_buffer.commit")
        if not self.done.wait(10):
            raise RuntimeError("最终识别结果超时。已收到的文字保留在窗口，可手动复制。")
        self.check_error()
        with self.lock:
            return self.transcript.text

    def close(self):
        with self.lifecycle:
            self.closing = True
            ws, self.ws = self.ws, None
        self.api_key = ""
        self.ready.set()
        self.done.set()
        try:
            if ws is not None:
                # Wake recv without destroying its descriptor. Closing it before
                # the reader exits can remove the wakeup from macOS kqueue.
                ws.abort()
            if self.reader and self.reader is not threading.current_thread():
                self.reader.join(1)
        finally:
            if ws is not None:
                ws.shutdown()
