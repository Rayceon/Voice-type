"""Selective native hook adapters for Windows and macOS.

Only the triggering key/button is swallowed. Modifiers already delivered to the
target are allowed through on release so applications do not get stuck modifiers.
"""
from __future__ import annotations

import sys
import threading
import time

from .triggers import MODIFIERS, TriggerState, key_token


class SelectiveState:
    def __init__(self, trigger, emit):
        self.state = TriggerState(trigger, emit)
        self.primaries = self.state.required - MODIFIERS or self.state.required
        self.captured = set()
        self.held = {}
        self.owner = None
        self.lock = threading.Lock()

    def event(self, token, pressed, identity=None):
        identity = token if identity is None else identity
        with self.lock:
            captured = identity in self.captured
            repeated = identity in self.held
            if pressed:
                self.held[identity] = token
            else:
                self.held.pop(identity, None)
            self.state.down = set(self.held.values())
            matches = self.state.required <= self.state.down
            if self.state.active:
                if not matches or (not pressed and identity == self.owner):
                    self.state.active = False
                    self.state.emit(False)
            elif pressed and not repeated and token in self.primaries and matches:
                # Only a fresh primary press may start a combo. A key already
                # delivered to the target must not become a trigger on repeat.
                self.owner = identity
                self.captured.add(identity)
                captured = self.state.active = True
                self.state.emit(True)
            if not pressed:
                self.captured.discard(identity)
            return captured


class NativeTrigger:
    def __init__(self, trigger, emit, report):
        self.selector = SelectiveState(trigger, emit)
        self.report = report
        self.listeners = []
        self.stopped = threading.Event()
        self.monitor = None

    def start(self):
        from pynput import keyboard, mouse
        if sys.platform == "win32":
            if any(t.startswith("mouse:button") for t in self.selector.state.required):
                raise RuntimeError("Windows 标准输入后端仅支持左右/中键及 x1/x2 侧键。")
            self._windows(keyboard, mouse)
        elif sys.platform == "darwin":
            self._mac(keyboard, mouse)
        else:
            raise RuntimeError("没有可用的原生输入后端。")
        try:
            for listener in self.listeners:
                listener.start()
                self._wait_ready(listener)
                if not getattr(listener, "IS_TRUSTED", True):
                    raise RuntimeError("请在系统设置中授权 Voice Type 的辅助功能和输入监控权限。")
                if not listener.is_alive():
                    raise RuntimeError("无法启动全局按键监听，请检查系统权限。")
        except Exception:
            self.stop()
            raise
        self.report("原生录音键拦截已启用；请在目标应用输入框测试录音和粘贴。")
        self.monitor = threading.Thread(target=self._monitor, daemon=True, name="voice-type-hook-watch")
        self.monitor.start()

    @staticmethod
    def _wait_ready(listener, timeout=3):
        # pynput.wait() has no timeout and may never return if the native thread
        # fails before _mark_ready(). This private flag is present in pynput 1.8.
        deadline = time.monotonic() + timeout
        while not getattr(listener, "_ready", False):
            if not listener.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError("全局输入监听启动失败或超时，请检查系统权限后重新启用。")
            time.sleep(.01)

    def _monitor(self):
        while not self.stopped.wait(.1):
            if any(not listener.is_alive() for listener in self.listeners):
                self.report("系统输入监听已停止，请检查权限后重新启用录音键。")
                self.stop()
                break

    def _windows(self, keyboard, mouse):
        import ctypes
        vk_tokens = {}
        for name, key in keyboard.Key.__members__.items():
            if getattr(key.value, "vk", None) is not None:
                vk_tokens[key.value.vk] = key_token(key)
        for char in "abcdefghijklmnopqrstuvwxyz0123456789":
            vk = ctypes.windll.user32.VkKeyScanW(ord(char))
            if vk != -1:
                vk_tokens[vk & 0xff] = char
        for char, token in {",": "comma", ".": "period", "/": "slash", ";": "semicolon",
                            "'": "apostrophe", "[": "bracket_left", "]": "bracket_right",
                            "\\": "backslash", "`": "grave", "-": "minus", "=": "equal"}.items():
            vk = ctypes.windll.user32.VkKeyScanW(ord(char))
            if vk != -1:
                vk_tokens[vk & 0xff] = token

        def key_filter(msg, data):
            if self.stopped.is_set() or data.flags & 0x10 or msg not in (0x100, 0x101, 0x104, 0x105):
                return False
            token = vk_tokens.get(data.vkCode, "")
            if token and self.selector.event(token, msg in (0x100, 0x104), ("key", data.vkCode)):
                self.keyboard.suppress_event()
            return False  # Already processed in the hook; no asynchronous callback needed.

        mouse_messages = {0x201: ("mouse:left", True), 0x202: ("mouse:left", False),
                          0x204: ("mouse:right", True), 0x205: ("mouse:right", False),
                          0x207: ("mouse:middle", True), 0x208: ("mouse:middle", False)}

        def mouse_filter(msg, data):
            if self.stopped.is_set() or data.flags & 1:
                return False
            event = mouse_messages.get(msg)
            if msg in (0x20B, 0x20C):
                event = ("mouse:x1" if data.mouseData >> 16 == 1 else "mouse:x2", msg == 0x20B)
            if event and self.selector.event(*event):
                self.mouse.suppress_event()
            return False

        self.keyboard = keyboard.Listener(win32_event_filter=key_filter)
        self.mouse = mouse.Listener(win32_event_filter=mouse_filter)
        self.listeners = [self.keyboard, self.mouse]

    def _mac(self, keyboard, mouse):
        import Quartz
        decisions = {"keyboard": False}
        modifier_keys = {key.value.vk: key_token(key) for key in keyboard.Key
                         if key_token(key) in MODIFIERS}
        modifier_flags = {"ctrl": Quartz.kCGEventFlagMaskControl, "alt": Quartz.kCGEventFlagMaskAlternate,
                          "shift": Quartz.kCGEventFlagMaskShift, "cmd": Quartz.kCGEventFlagMaskCommand}

        def key_event(key, pressed, injected=False):
            if self.stopped.is_set() or key_token(key) in MODIFIERS:
                decisions["keyboard"] = False
                return  # Quartz flags represent both left/right modifiers together.
            physical = getattr(getattr(key, "value", key), "vk", None)
            identity = ("key", physical) if physical is not None else key_token(key)
            decisions["keyboard"] = False if injected else self.selector.event(key_token(key), pressed, identity)

        def keyboard_intercept(kind, event):
            if self.stopped.is_set():
                return event
            if kind == 12 and not Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID):
                physical = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                token = modifier_keys.get(physical)
                if token:
                    pressed = bool(Quartz.CGEventGetFlags(event) & modifier_flags[token])
                    decisions["keyboard"] = self.selector.event(token, pressed)
            return None if kind in (10, 11, 12) and decisions["keyboard"] else event

        def mouse_intercept(kind, event):
            # pynput's macOS mouse enum collapses ALL extra buttons to middle.
            # Read the actual Quartz button number so x1/x2 remain distinguishable.
            if self.stopped.is_set() or kind not in (1, 2, 3, 4, 25, 26):
                return event
            if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID):
                return event
            number = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber)
            token = {0: "mouse:left", 1: "mouse:right", 2: "mouse:middle",
                     3: "mouse:x1", 4: "mouse:x2"}.get(number, f"mouse:button{number + 1}")
            return None if self.selector.event(token, kind in (1, 3, 25)) else event

        self.listeners = [keyboard.Listener(on_press=lambda k, injected=False: key_event(k, True, injected),
                                            on_release=lambda k, injected=False: key_event(k, False, injected),
                                            darwin_intercept=keyboard_intercept),
                          mouse.Listener(darwin_intercept=mouse_intercept)]

    def stop(self):
        self.stopped.set()
        listeners, self.listeners = self.listeners, []
        for listener in listeners:
            try:
                listener.stop()
                if listener.ident is not None and listener is not threading.current_thread():
                    listener.join(.2)
            except Exception:
                pass
        with self.selector.lock:
            self.selector.held.clear()
            self.selector.captured.clear()
            if self.selector.state.active:
                self.selector.state.active = False
                self.selector.state.emit(False)
