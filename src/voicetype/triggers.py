"""Global trigger matching, independent of GUI and audio callback threads."""
from __future__ import annotations

import os
import re
import sys

MODIFIERS = {"ctrl", "alt", "shift", "cmd"}
ALIASES = {"control": "ctrl", "super": "cmd", "win": "cmd", "meta": "cmd",
           "return": "enter", "escape": "esc", "spacebar": "space",
           ",": "comma", ".": "period", "/": "slash", ";": "semicolon",
           "'": "apostrophe", "[": "bracket_left", "]": "bracket_right",
           "\\": "backslash", "`": "grave", "-": "minus", "=": "equal",
           "mouse:button8": "mouse:x1", "mouse:button9": "mouse:x2"}
SPECIAL = {"space", "enter", "esc", "tab", "backspace", "delete", "insert",
           "home", "end", "page_up", "page_down", "up", "down", "left", "right",
           "caps_lock", "num_lock", "scroll_lock", "pause", "print_screen",
           "menu", "alt_gr", "comma", "period", "slash", "semicolon", "apostrophe",
           "bracket_left", "bracket_right", "backslash", "grave", "minus", "equal",
           "media_play", "media_stop", "media_record", "media_play_pause", "media_previous",
           "media_next", "media_volume_mute", "media_volume_down", "media_volume_up",
           *MODIFIERS}


def parse_trigger(value: str) -> frozenset[str]:
    tokens = [ALIASES.get(t.strip().lower(), t.strip().lower()) for t in value.split("+")]
    if not tokens or any(not t for t in tokens) or len(set(tokens)) != len(tokens):
        raise ValueError("录音键格式无效，例如 f8、ctrl+shift+space、mouse:x1。")
    for token in tokens:
        if (token not in SPECIAL and not re.fullmatch(r"[a-z0-9]|f(?:[1-9]|1[0-9]|2[0-4])", token)
                and token not in {"mouse:left", "mouse:right", "mouse:middle", "mouse:x1", "mouse:x2"}
                and not re.fullmatch(r"mouse:button(?:[8-9]|[12][0-9]|3[01])", token)):
            raise ValueError(f"不支持的按键：{token}。可使用按键录入按钮。")
    if sum(t not in MODIFIERS for t in tokens) > 1:
        raise ValueError("请选择一个普通按键或鼠标键，可搭配 Ctrl/Alt/Shift/Cmd。")
    return frozenset(tokens)


def key_token(key) -> str:
    name = getattr(key, "name", None)
    if name:
        return re.sub(r"_(l|r)$", "", name)
    char = getattr(key, "char", None)
    if char:
        if len(char) == 1 and 1 <= ord(char) <= 26:
            return chr(ord(char) + 96)
        return ALIASES.get(char.lower(), char.lower())
    return ""


def mouse_token(button) -> str:
    name = getattr(button, "name", "")
    return "mouse:" + {"button8": "x1", "button9": "x2"}.get(name, name)


class TriggerState:
    """Debounce auto-repeat and emit release even if a modifier is released first."""

    def __init__(self, trigger: str, emit):
        self.required = parse_trigger(trigger)
        self.emit = emit
        self.down: set[str] = set()
        self.active = False

    def event(self, token: str, pressed: bool) -> None:
        if pressed:
            self.down.add(token)
        else:
            self.down.discard(token)
        active = self.required <= self.down
        if active != self.active:
            self.active = active
            self.emit(active)


class GlobalTrigger:
    def __init__(self, trigger: str, emit, report):
        self.state = TriggerState(trigger, emit)
        self.report = report
        self.listeners = []
        self.native = None

    def start(self) -> None:
        if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
            from .portal_trigger import PortalTrigger
            self.native = PortalTrigger("+".join(self.state.required), self.state.emit, self.report)
            self.native.start()
            return
        if sys.platform.startswith("linux"):
            from .x11_trigger import X11Trigger
            self.native = X11Trigger("+".join(self.state.required), self.state.emit, self.report)
            self.native.start()
            return
        from .native_trigger import NativeTrigger
        self.native = NativeTrigger("+".join(self.state.required), self.state.emit, self.report)
        self.native.start()

    def stop(self) -> None:
        if self.native:
            self.native.stop()
            self.native = None
        for listener in self.listeners:
            listener.stop()
        self.listeners = []
        self.state.down.clear()
        if self.state.active:
            self.state.active = False
            self.state.emit(False)

    def modifiers_down(self):
        if self.native is None:
            return False
        if hasattr(self.native, "modifiers_down"):
            return self.native.modifiers_down()
        selector = getattr(self.native, "selector", None)
        if selector:
            with selector.lock:
                return bool(selector.state.down & MODIFIERS)
        return False
