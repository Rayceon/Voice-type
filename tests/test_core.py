import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from voicetype.asr import Transcript
from voicetype import devices
from voicetype.engine import Recording
from voicetype.settings import Settings, load, save
from voicetype.triggers import TriggerState, key_token, parse_trigger


def test_settings_roundtrip_and_no_secret(tmp_path):
    path = tmp_path / "config" / "settings.json"
    settings = Settings(device_name="中文 USB 麦克风", host_api="WASAPI", trigger="ctrl+shift+space")
    save(settings, path)
    assert load(path) == settings
    data = json.loads(path.read_text(encoding="utf-8"))
    assert not any("key" in name for name in data)
    assert len(list(path.parent.iterdir())) == 1


def test_corrupt_settings_not_overwritten(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken")
    with pytest.raises(ValueError):
        load(path)
    assert path.read_text() == "{broken"


def test_unknown_settings_fields_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"future_field": true, "trigger": "f9"}')
    assert load(path).trigger == "f9"


@pytest.mark.parametrize("position", ["bottom_center", "bottom_left", "bottom_right",
                                     "top_center", "top_left", "top_right"])
def test_indicator_position_persists(tmp_path, position):
    path = tmp_path / "settings.json"
    save(Settings(indicator_position=position), path)
    assert load(path).indicator_position == position


def test_indicator_old_config_default_and_invalid_value(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"trigger":"f2"}')
    assert load(path).indicator_position == "bottom_center"
    with pytest.raises(ValueError, match="悬浮提示"):
        Settings(indicator_position="outside").validate()


@pytest.mark.parametrize("field,value", [("model", 123), ("auto_paste", "false"),
                                       ("max_seconds", True), ("device_name", []),
                                       ("trigger", None), ("region", {})])
def test_invalid_settings_types_rejected(field, value):
    settings = Settings()
    setattr(settings, field, value)
    with pytest.raises(ValueError, match="类型无效"):
        settings.validate()


@pytest.mark.parametrize("trigger", ["", "ctrl++space", "ctrl+ctrl", "a+b", "notakey", "mouse:button999"])
def test_invalid_triggers(trigger):
    with pytest.raises(ValueError):
        parse_trigger(trigger)


@pytest.mark.parametrize("trigger", ["f8", "ctrl+shift+space", "mouse:x1", "alt+mouse:middle", "mouse:button13",
                                     "cmd", "ctrl+comma", "shift+slash", "media_volume_down"])
def test_configurable_triggers(trigger):
    assert parse_trigger(trigger)


def test_modifier_release_and_repeat():
    calls = []
    state = TriggerState("ctrl+space", calls.append)
    for token, pressed in [("ctrl", True), ("space", True), ("space", True),
                           ("ctrl", False), ("space", False)]:
        state.event(token, pressed)
    assert calls == [True, False]


def test_native_suppression_keeps_modifier_releases_and_unrelated_keys():
    from voicetype.native_trigger import SelectiveState
    calls = []
    state = SelectiveState("ctrl+mouse:x1", calls.append)
    assert not state.event("ctrl", True)
    assert state.event("mouse:x1", True)
    assert not state.event("a", True)
    assert not state.event("a", False)
    assert not state.event("ctrl", False)
    assert state.event("mouse:x1", False)
    assert not state.event("mouse:x1", True)
    assert calls == [True, False]


def test_native_repeat_swallowed_until_release():
    from voicetype.native_trigger import SelectiveState
    calls = []
    state = SelectiveState("f8", calls.append)
    assert state.event("f8", True)
    assert state.event("f8", True)
    assert state.event("f8", False)
    assert calls == [True, False]


def test_native_combo_requires_new_primary_press():
    from voicetype.native_trigger import SelectiveState
    calls = []
    state = SelectiveState("ctrl+space", calls.append)
    assert not state.event("space", True)
    assert not state.event("ctrl", True)
    assert not state.event("space", True)  # Auto-repeat of an already delivered key.
    assert not state.event("space", False)
    assert calls == []
    assert state.event("space", True)
    assert state.event("space", False)
    assert calls == [True, False]


def test_native_dual_modifiers_release_independently():
    from voicetype.native_trigger import SelectiveState
    calls = []
    state = SelectiveState("ctrl+f8", calls.append)
    assert not state.event("ctrl", True, "left-ctrl")
    assert not state.event("ctrl", True, "right-ctrl")
    assert state.event("f8", True)
    assert not state.event("ctrl", False, "left-ctrl")
    assert calls == [True]
    assert not state.event("ctrl", False, "right-ctrl")
    assert state.event("f8", False)
    assert calls == [True, False]


def test_ctrl_character_normalizes():
    assert key_token(SimpleNamespace(char="\x01")) == "a"
    assert key_token(SimpleNamespace(name="ctrl_l")) == "ctrl"
    assert key_token(SimpleNamespace(char=",")) == "comma"
    assert key_token(SimpleNamespace(char="/")) == "slash"


def test_all_asr_segments_and_final_correction():
    transcript = Transcript()
    prefix = "conversation.item.input_audio_transcription."
    transcript.update({"type": prefix + "text", "item_id": "1", "stash": "错字很多。"})
    transcript.update({"type": prefix + "completed", "item_id": "1", "transcript": "第一句。"})
    transcript.update({"type": prefix + "text", "item_id": "2", "stash": "第二"})
    transcript.update({"type": prefix + "completed", "item_id": "2", "transcript": "第二句。"})
    transcript.update({"type": prefix + "text", "item_id": "1", "stash": "迟到的旧 partial"})
    transcript.update({"type": prefix + "completed", "item_id": "2", "transcript": "第二句。"})
    assert transcript.text == "第一句。第二句。"


def test_anonymous_asr_segments():
    transcript = Transcript()
    for text in ["第一句。", "第二句。"]:
        transcript.update({"type": "asr.text", "stash": text})
        transcript.update({"type": "asr.completed", "transcript": text})
    assert transcript.text == "第一句。第二句。"


def test_device_index_can_change(monkeypatch):
    backend = SimpleNamespace(default=SimpleNamespace(device=(9, 1)))
    monkeypatch.setattr(devices, "audio_backend", lambda: backend)
    mic = devices.InputDevice(9, "USB mic", "WASAPI", 48000, 2)
    monkeypatch.setattr(devices, "list_inputs", lambda: [mic])
    assert devices.resolve_input("USB mic", "WASAPI", 9).index == 9
    assert devices.resolve_input().index == 9
    monkeypatch.setattr(devices, "list_inputs", lambda: [
        devices.InputDevice(4, "USB mic", "WASAPI", 48000, 2)])
    assert devices.resolve_input("USB mic", "WASAPI", 9).index == 4
    monkeypatch.setattr(devices, "list_inputs", lambda: [mic])
    with pytest.raises(RuntimeError, match="断开"):
        devices.resolve_input("disconnected mic", "WASAPI")


def test_duplicate_device_name_requires_saved_index(monkeypatch):
    backend = SimpleNamespace(default=SimpleNamespace(device=(3, 1)))
    monkeypatch.setattr(devices, "audio_backend", lambda: backend)
    monkeypatch.setattr(devices, "list_inputs", lambda: [
        devices.InputDevice(3, "USB mic", "ALSA", 48000, 1),
        devices.InputDevice(7, "USB mic", "ALSA", 48000, 1),
    ])
    with pytest.raises(RuntimeError, match="名称重复"):
        devices.resolve_input("USB mic", "ALSA")
    assert devices.resolve_input("USB mic", "ALSA", 7).index == 7
    with pytest.raises(RuntimeError, match="名称重复"):
        devices.resolve_input("USB mic", "ALSA", 9)


def test_native_sample_rate_fallback(monkeypatch):
    class PortAudioError(Exception):
        pass
    def check(**kwargs):
        if (kwargs["samplerate"], kwargs["channels"]) != (44100, 2):
            raise PortAudioError()
    monkeypatch.setattr(devices, "audio_backend", lambda: SimpleNamespace(
        PortAudioError=PortAudioError, check_input_settings=check))
    assert devices.input_format(devices.InputDevice(0, "mic", "ALSA", 44100, 2)) == (44100, 2)


def test_rescan_reinitializes_cached_device_list(monkeypatch):
    calls = []
    cached = [devices.InputDevice(0, "old", "ALSA", 48000, 1)]
    def terminate():
        calls.append("terminate")
        backend._initialized = 0
    def initialize():
        assert backend._initialized == 0
        calls.append("initialize")
        cached[:] = [devices.InputDevice(3, "new USB", "ALSA", 44100, 2)]
        backend._initialized = 1
    backend = SimpleNamespace(_initialized=1, _initialize=initialize, _terminate=terminate)
    monkeypatch.setattr(devices, "audio_backend", lambda: backend)
    monkeypatch.setattr(devices, "list_inputs", lambda: list(cached))
    assert devices.rescan_inputs()[0].name == "new USB"
    assert calls == ["terminate", "initialize"]
    assert backend._initialized == 1


def test_rescan_retries_after_failed_initialization_without_extra_terminate(monkeypatch):
    calls = []
    backend = SimpleNamespace(_initialized=0, _initialize=lambda: calls.append("initialize"),
                              _terminate=lambda: calls.append("terminate"))
    monkeypatch.setattr(devices, "audio_backend", lambda: backend)
    monkeypatch.setattr(devices, "list_inputs", lambda: [])
    assert devices.rescan_inputs() == []
    assert calls == ["initialize"]


def test_audio_callback_does_not_capture_after_release():
    recording = Recording(Settings(), "fake", lambda *_: None)
    block = np.ones((320, 1), dtype=np.float32)
    recording._callback(block, 320, None, None)
    recording.stop()
    recording._callback(block, 320, None, None)
    assert recording.audio.qsize() == 1


def test_pcm_little_endian_clips():
    raw = Recording._pcm(np.array([-2, 0, 2], dtype=np.float32))
    assert np.frombuffer(raw, dtype="<i2").tolist() == [-32767, 0, 32767]


def test_recording_failure_cleans_up(monkeypatch):
    from voicetype import engine
    def broken():
        raise RuntimeError("microphone error")
    monkeypatch.setattr(engine, "audio_backend", broken)
    events = []
    recording = Recording(Settings(), "fake-secret", lambda *event: events.append(event))
    recording.start()
    recording.thread.join(2)
    assert events == [("error", "microphone error"), ("finished", None)]
    assert recording.key == ""


def test_recording_pipeline_retains_audio_and_final(monkeypatch):
    from voicetype import engine
    events = []
    chunks = []
    recording = None
    class Stream:
        active = True
        closed = False
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
        def start(self):
            for _ in range(10):
                self.callback(np.full((960, 2), .2, dtype=np.float32), 960, None, None)
            recording.stop()
        def stop(self):
            self.active = False
        def close(self):
            Stream.closed = True
    class Session:
        closed = False
        def __init__(self, settings, key, partial):
            self.partial = partial
        def start(self):
            self.partial("第一句")
        def feed(self, chunk):
            chunks.append(chunk)
        def check_error(self):
            pass
        def finish(self):
            assert Stream.closed, "Release the microphone before waiting on cloud ASR"
            return "第一句。第二句。"
        def close(self):
            Session.closed = True
    monkeypatch.setattr(engine, "audio_backend", lambda: SimpleNamespace(InputStream=Stream))
    monkeypatch.setattr(engine, "resolve_input", lambda *_: SimpleNamespace(name="Test", index=2))
    monkeypatch.setattr(engine, "input_format", lambda _: (48000, 2))
    recording = Recording(Settings(), "fake", lambda *event: events.append(event), Session)
    recording.start()
    recording.thread.join(3)
    assert not recording.thread.is_alive()
    assert sum(map(len, chunks)) == 3200 * 2
    assert ("result", "第一句。第二句。") in events
    assert Stream.closed and Session.closed
    assert events[-1] == ("finished", None)
