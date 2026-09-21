"""Exercise native callback adapters without installing system-wide hooks.

These are wire-shape unit tests, not a substitute for Windows/macOS acceptance.
"""
import ctypes
from enum import Enum
import sys
import threading
import time
from types import SimpleNamespace

from voicetype.native_trigger import NativeTrigger
import pytest


class Suppressed(Exception):
    pass


class Listener:
    def __init__(self, **callbacks):
        self.callbacks = callbacks

    def suppress_event(self):
        raise Suppressed()


def swallowed(callback, *args):
    try:
        assert callback(*args) is False
        return False
    except Suppressed:
        return True


def test_windows_callback_suppresses_only_physical_trigger(monkeypatch):
    keys = Enum("Key", {"ctrl_l": SimpleNamespace(vk=162), "ctrl_r": SimpleNamespace(vk=163),
                        "f8": SimpleNamespace(vk=119)})
    keyboard = SimpleNamespace(Key=keys, Listener=Listener)
    mouse = SimpleNamespace(Listener=Listener)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(
        VkKeyScanW=lambda char: ord(chr(char).upper()))), raising=False)
    events = []
    native = NativeTrigger("ctrl+f8", events.append, lambda _: None)
    native._windows(keyboard, mouse)
    hook = native.keyboard.callbacks["win32_event_filter"]
    def key(vk, down=True, flags=0):
        return swallowed(hook, 0x100 if down else 0x101, SimpleNamespace(vkCode=vk, flags=flags))
    assert not key(162)
    assert not key(163)
    assert not key(119, flags=0x10)  # Injected paste/automation input is ignored.
    assert events == []
    assert key(119)
    assert key(119)  # Auto-repeat remains swallowed.
    assert not key(ord("A"))
    assert not key(162, False)
    assert events == [True]
    assert not key(163, False)
    assert key(119, False)
    assert events == [True, False]


def test_windows_xbutton_mapping_and_injected_click(monkeypatch):
    keyboard = SimpleNamespace(Key=Enum("Key", {}), Listener=Listener)
    mouse = SimpleNamespace(Listener=Listener)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(
        VkKeyScanW=lambda char: char)), raising=False)
    events = []
    native = NativeTrigger("mouse:button8", events.append, lambda _: None)
    native._windows(keyboard, mouse)
    hook = native.mouse.callbacks["win32_event_filter"]
    assert not swallowed(hook, 0x20B, SimpleNamespace(mouseData=1 << 16, flags=1))
    assert not swallowed(hook, 0x20B, SimpleNamespace(mouseData=2 << 16, flags=0))
    assert swallowed(hook, 0x20B, SimpleNamespace(mouseData=1 << 16, flags=0))
    assert swallowed(hook, 0x20C, SimpleNamespace(mouseData=1 << 16, flags=0))
    assert events == [True, False]


def test_windows_common_punctuation_mapping(monkeypatch):
    keyboard = SimpleNamespace(Key=Enum("Key", {}), Listener=Listener)
    mouse = SimpleNamespace(Listener=Listener)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(
        VkKeyScanW=lambda char: char)), raising=False)
    events = []
    native = NativeTrigger("comma", events.append, lambda _: None)
    native._windows(keyboard, mouse)
    hook = native.keyboard.callbacks["win32_event_filter"]
    assert swallowed(hook, 0x100, SimpleNamespace(vkCode=ord(","), flags=0))
    assert swallowed(hook, 0x101, SimpleNamespace(vkCode=ord(","), flags=0))
    assert events == [True, False]


def mac_environment(monkeypatch):
    quartz = SimpleNamespace(
        kCGEventFlagMaskControl=1, kCGEventFlagMaskAlternate=2,
        kCGEventFlagMaskShift=4, kCGEventFlagMaskCommand=8,
        kCGEventSourceUnixProcessID="pid", kCGKeyboardEventKeycode="key",
        kCGMouseEventButtonNumber="button", CGEventGetFlags=lambda event: event.get("flags", 0),
        CGEventGetIntegerValueField=lambda event, field: event.get(field, 0))
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    keys = Enum("Key", {"ctrl_l": SimpleNamespace(vk=59), "ctrl_r": SimpleNamespace(vk=62),
                        "f8": SimpleNamespace(vk=100)})
    return SimpleNamespace(Key=keys, Listener=Listener), SimpleNamespace(Listener=Listener)


def test_mac_aggregate_modifier_flags_and_selective_swallow(monkeypatch):
    keyboard, mouse = mac_environment(monkeypatch)
    events = []
    native = NativeTrigger("ctrl+f8", events.append, lambda _: None)
    native._mac(keyboard, mouse)
    callbacks = native.listeners[0].callbacks
    def event(key, pressed, flags, injected=False):
        # pynput runs this callback before darwin_intercept.
        callbacks["on_press" if pressed else "on_release"](key, injected)
        kind = 12 if key.name.startswith("ctrl") else (10 if pressed else 11)
        raw = {"key": key.value.vk, "flags": flags, "pid": 1 if injected else 0}
        return callbacks["darwin_intercept"](kind, raw) is None
    assert not event(keyboard.Key.ctrl_l, True, 1)
    assert not event(keyboard.Key.ctrl_r, True, 1)
    assert not event(keyboard.Key.f8, True, 1, injected=True)
    assert event(keyboard.Key.f8, True, 1)
    # Releasing left Ctrl while right is down is reported as on_press by pynput.
    assert not event(keyboard.Key.ctrl_l, True, 1)
    assert events == [True]
    assert not event(keyboard.Key.ctrl_r, False, 0)
    assert event(keyboard.Key.f8, False, 0)
    assert events == [True, False]


def test_mac_raw_mouse_side_button_does_not_collapse_to_middle(monkeypatch):
    keyboard, mouse = mac_environment(monkeypatch)
    events = []
    native = NativeTrigger("mouse:x1", events.append, lambda _: None)
    native._mac(keyboard, mouse)
    hook = native.listeners[1].callbacks["darwin_intercept"]
    middle = {"button": 2}
    assert hook(25, middle) is middle
    assert hook(26, middle) is middle
    assert hook(25, {"button": 3}) is None
    assert hook(26, {"button": 3}) is None
    assert events == [True, False]


@pytest.mark.parametrize("alive", [True, False])
def test_native_startup_wait_is_bounded(alive):
    listener = SimpleNamespace(_ready=False, is_alive=lambda: alive)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="启动失败或超时"):
        NativeTrigger._wait_ready(listener, timeout=.02)
    assert time.monotonic() - started < .3


def test_hook_failure_releases_active_recording():
    events, reports = [], []
    trigger = NativeTrigger("f8", events.append, reports.append)
    stopped = threading.Event()
    trigger.listeners = [SimpleNamespace(is_alive=lambda: False, stop=stopped.set, ident=None)]
    assert trigger.selector.event("f8", True)
    trigger._monitor()
    assert stopped.is_set()
    assert events == [True, False]
    assert "监听已停止" in reports[-1]
