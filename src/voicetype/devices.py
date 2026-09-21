"""Discover and resolve input devices without trusting stale PortAudio indices."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def audio_backend():
    try:
        import sounddevice
        return sounddevice
    except (ImportError, OSError) as exc:
        raise RuntimeError("音频组件不可用：Linux 请安装 libportaudio2；Windows/macOS 请重新安装 sounddevice。") from exc


@dataclass(frozen=True)
class InputDevice:
    index: int
    name: str
    host_api: str
    default_rate: int
    channels: int

    @property
    def label(self) -> str:
        return f"{self.name} · {self.host_api}"


def list_inputs() -> list[InputDevice]:
    sd = audio_backend()
    apis = sd.query_hostapis()
    return [InputDevice(i, d["name"], apis[d["hostapi"]]["name"],
                        round(d["default_samplerate"]), d["max_input_channels"])
            for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def rescan_inputs() -> list[InputDevice]:
    """Rebuild PortAudio's device cache. Caller must have closed ALL app streams.

    sounddevice 0.5 has no public hotplug rescan API. Keep the private lifecycle
    dependency confined here and fail clearly if a future version changes it.
    The GUI never invokes this while a Recording worker is active.
    """
    sd = audio_backend()
    if (not callable(getattr(sd, "_initialize", None))
            or not callable(getattr(sd, "_terminate", None))
            or getattr(sd, "_initialized", None) not in (0, 1)):
        raise RuntimeError("当前音频组件不支持安全刷新，请重启 Voice Type 重新检测设备。")
    try:
        if sd._initialized:
            sd._terminate()
        sd._initialize()
        return list_inputs()
    except Exception:
        raise RuntimeError("重新检测音频设备失败，请检查音频服务并重启 Voice Type。") from None


def resolve_input(name: str = "", host_api: str = "", index: int = -1) -> InputDevice:
    sd = audio_backend()
    devices = list_inputs()
    if name:
        matches = [d for d in devices if d.name == name and d.host_api == host_api]
        if len(matches) == 1:
            return matches[0]
        if index >= 0:
            indexed = [d for d in matches if d.index == index]
            if len(indexed) == 1:
                return indexed[0]
        if not matches or len(matches) > 1:
            raise RuntimeError("所选麦克风已断开或名称重复，请刷新设备并重新选择。")
    default = sd.default.device[0]
    for d in devices:
        if d.index == default:
            return d
    raise RuntimeError("系统没有可用的默认麦克风，请在设置中选择输入设备。")


def input_format(device: InputDevice) -> tuple[int, int]:
    sd = audio_backend()
    for rate in dict.fromkeys([device.default_rate, 48000, 44100, 32000, 16000, 8000]):
        for channels in dict.fromkeys([1, min(2, device.channels)]):
            try:
                sd.check_input_settings(device=device.index, samplerate=rate,
                                        channels=channels, dtype="float32")
                return rate, channels
            except sd.PortAudioError:
                continue
    raise RuntimeError("麦克风不支持可用的录音格式，请检查权限或换一个输入设备。")


def level(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
