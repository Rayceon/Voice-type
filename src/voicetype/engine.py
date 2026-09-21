"""Bounded audio queue + worker-owned ASR; callbacks never perform network I/O."""
from __future__ import annotations

import queue
import threading
import time

import numpy as np
import soxr

from .asr import QwenSession
from .devices import audio_backend, input_format, level, resolve_input
from .settings import Settings


class Recording:
    def __init__(self, settings: Settings, key: str, emit, session_factory=QwenSession):
        self.settings, self.key, self.emit = settings, key, emit
        self.session_factory = session_factory
        self.stop_event = threading.Event()
        self.cancel_event = threading.Event()
        self.audio: queue.Queue = queue.Queue(maxsize=500)  # 10 seconds at 20 ms/block
        self.overflow = threading.Event()
        self.deadline = float("inf")
        self.session = None
        self.session_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True, name="voice-type-recording")

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def cancel(self):
        self.cancel_event.set()
        self.stop_event.set()
        with self.session_lock:
            session = self.session
        if session is not None:
            session.close()

    def _callback(self, data, frames, timing, status):
        if time.monotonic() >= self.deadline:
            self.stop_event.set()
        if self.stop_event.is_set():
            return
        if status:
            self.overflow.set()
        try:
            self.audio.put_nowait(data.copy())
        except queue.Full:
            self.overflow.set()

    def _run(self):
        stream = session = None
        try:
            sd = audio_backend()
            device = resolve_input(self.settings.device_name, self.settings.host_api,
                                   self.settings.device_index)
            rate, channels = input_format(device)
            converter = soxr.ResampleStream(rate, 16000, 1, dtype="float32")
            stream = sd.InputStream(device=device.index, samplerate=rate, channels=channels,
                                    dtype="float32", blocksize=max(1, round(rate * .02)),
                                    callback=self._callback)
            self.deadline = time.monotonic() + self.settings.max_seconds
            stream.start()
            self.emit("state", f"录音中 · {device.name}")
            session = self.session_factory(self.settings, self.key,
                                           lambda text: self.emit("partial", text))
            with self.session_lock:
                self.session = session
            if self.cancel_event.is_set():
                return
            session.start()
            samples_sent = 0
            capture_stopped = False
            while not self.cancel_event.is_set():
                if self.overflow.is_set():
                    raise RuntimeError("录音缓冲区溢出或设备丢帧，请检查网络/设备后重试。")
                if time.monotonic() >= self.deadline:
                    self.stop_event.set()
                if self.stop_event.is_set() and not capture_stopped:
                    stream.stop()
                    stream.close()  # ALSA stop alone still owns the exclusive device.
                    stream = None
                    capture_stopped = True
                    self.emit("state", "识别收尾中…")
                try:
                    block = self.audio.get(timeout=.05)
                except queue.Empty:
                    if capture_stopped:
                        break
                    if not stream.active:
                        raise RuntimeError("麦克风停止工作，请检查连接并重新选择设备。")
                    session.check_error()
                    continue
                mono = np.mean(block, axis=1, dtype=np.float32)
                self.emit("level", min(100, round(level(mono) * 400)))
                samples = converter.resample_chunk(mono)
                if len(samples):
                    session.feed(self._pcm(samples))
                    samples_sent += len(samples)
            if self.cancel_event.is_set():
                return
            tail = converter.resample_chunk(np.empty(0, dtype=np.float32), last=True)
            if len(tail):
                session.feed(self._pcm(tail))
                samples_sent += len(tail)
            if samples_sent < 1600:
                raise RuntimeError("录音不足 0.1 秒，请按住录音键说完再松开。")
            text = session.finish()
            if not self.cancel_event.is_set():
                self.emit("result", text)
        except Exception as exc:
            if not self.cancel_event.is_set():
                # Only our own RuntimeErrors are intended for display.
                if type(exc).__name__ == "PortAudioError" and -9985 in exc.args:
                    message = "麦克风不可用，可能被旧版 Voice Type 或其他程序占用。请结束另一处录音/麦克风测试后重试。"
                else:
                    message = str(exc) if isinstance(exc, RuntimeError) else f"录音/连接失败（{type(exc).__name__}），请检查设备、权限和网络。"
                self.emit("error", message.replace(self.key, "[redacted]") if self.key else message)
        finally:
            with self.session_lock:
                self.session = None
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass
            self.key = ""
            self.emit("finished", None)

    @staticmethod
    def _pcm(samples):
        return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
