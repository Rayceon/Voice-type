"""Portable settings; API keys never enter the settings JSON."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile

from platformdirs import user_config_path

ENDPOINTS = {
    "中国大陆": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
    "国际站": "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
}

INDICATOR_POSITIONS = {
    "bottom_center": "底部中央", "bottom_left": "左下角", "bottom_right": "右下角",
    "top_center": "顶部中央", "top_left": "左上角", "top_right": "右上角",
}

# Product limit, deliberately below the provider's 10,000-token context budget.
HOTWORDS_MAX_CHARS = 2000


@dataclass
class Settings:
    version: int = 1
    device_name: str = ""
    host_api: str = ""
    device_index: int = -1
    trigger: str = "f8"
    activation: str = "hold"
    auto_paste: bool = True
    paste_shortcut: str = "auto"
    region: str = "中国大陆"
    model: str = "qwen3-asr-flash-realtime"
    language: str = "zh"
    hotwords: str = ""
    max_seconds: int = 120
    indicator_position: str = "bottom_center"

    def validate(self) -> None:
        for field in fields(self):
            if type(getattr(self, field.name)) is not type(field.default):
                raise ValueError(f"设置字段 {field.name} 的类型无效。")
        if self.version != 1:
            raise ValueError("设置文件版本不兼容，请使用更新的 Voice Type。")
        if type(self.device_index) is not int or self.device_index < -1:
            raise ValueError("输入设备索引无效，请重新选择麦克风。")
        if self.region not in ENDPOINTS:
            raise ValueError("请选择有效的 ASR 服务区域。")
        if self.activation not in {"hold", "toggle"}:
            raise ValueError("录音模式无效。")
        if self.indicator_position not in INDICATOR_POSITIONS:
            raise ValueError("请选择有效的悬浮提示位置。")
        if self.paste_shortcut not in {"auto", "ctrl+v", "ctrl+shift+v", "cmd+v"}:
            raise ValueError("粘贴快捷键无效。")
        if not self.model.strip() or not 5 <= self.max_seconds <= 600:
            raise ValueError("模型不能为空，录音上限须为 5–600 秒。")
        if len(self.hotwords) > HOTWORDS_MAX_CHARS:
            raise ValueError(f"自定义热词最多 {HOTWORDS_MAX_CHARS} 个字符，请精简后重试。")
        from .triggers import parse_trigger
        parse_trigger(self.trigger)


def config_path() -> Path:
    return user_config_path("VoiceType", appauthor=False) / "settings.json"


def load(path: Path | None = None) -> Settings:
    path = path or config_path()
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("设置文件应为 JSON 对象。")
    allowed = {f.name for f in fields(Settings)}
    settings = Settings(**{k: v for k, v in data.items() if k in allowed})
    settings.validate()
    return settings


def save(settings: Settings, path: Path | None = None) -> None:
    settings.validate()
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Credentials:
    """Use OS keychain when available; otherwise the key stays in this process."""

    def __init__(self) -> None:
        self.session_key = ""

    def get(self) -> str:
        if self.session_key:
            return self.session_key
        if os.environ.get("DASHSCOPE_API_KEY"):
            return os.environ["DASHSCOPE_API_KEY"]
        try:
            import keyring
            return keyring.get_password("VoiceType", "dashscope") or ""
        except Exception:
            return ""

    def set(self, value: str, remember: bool) -> str:
        self.session_key = value.strip()
        if not remember:
            return "API Key 仅在本次运行使用。"
        try:
            import keyring
            keyring.set_password("VoiceType", "dashscope", self.session_key)
            return "API Key 已存入系统凭据库。"
        except Exception:
            return "系统凭据库不可用，API Key 仅保留在本次运行中。"
