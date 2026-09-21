"""X11 passive grabs, owned by this connection and released on exit/crash.

An active X11 grab owns the keyboard/pointer until the trigger is released.
This is suitable for push-to-talk, not simultaneous typing while holding a key.
"""
from __future__ import annotations

import select
import threading
import time

from .triggers import MODIFIERS, parse_trigger


class X11Trigger:
    def __init__(self, trigger, emit, report, display_name=None):
        self.required = parse_trigger(trigger)
        self.emit, self.report = emit, report
        self.display_name = display_name
        self.display = None
        self.thread = None
        self.stopped = threading.Event()
        self.active = False
        self.bindings = []

    def start(self):
        from Xlib import X, XK, display
        from Xlib.keysymdef import xf86
        self.X = X
        self.display = display.Display(self.display_name)
        root = self.display.screen().root
        masks = {"ctrl": X.ControlMask, "shift": X.ShiftMask, "alt": X.Mod1Mask, "cmd": X.Mod4Mask}
        names = {"space": "space", "enter": "Return", "esc": "Escape", "tab": "Tab",
                 "backspace": "BackSpace", "delete": "Delete", "insert": "Insert",
                 "home": "Home", "end": "End", "page_up": "Prior", "page_down": "Next",
                 "left": "Left", "right": "Right", "up": "Up", "down": "Down",
                 "caps_lock": "Caps_Lock", "num_lock": "Num_Lock", "scroll_lock": "Scroll_Lock",
                 "pause": "Pause", "print_screen": "Print", "menu": "Menu", "alt_gr": "ISO_Level3_Shift",
                 "ctrl": "Control_L", "shift": "Shift_L", "alt": "Alt_L", "cmd": "Super_L",
                 "comma": "comma", "period": "period", "slash": "slash", "semicolon": "semicolon",
                 "apostrophe": "apostrophe", "bracket_left": "bracketleft",
                 "bracket_right": "bracketright", "backslash": "backslash", "grave": "grave",
                 "minus": "minus", "equal": "equal", "media_play": "XF86_AudioPlay",
                 "media_stop": "XF86_AudioStop", "media_record": "XF86_AudioRecord",
                 "media_play_pause": "XF86_AudioPlay", "media_previous": "XF86_AudioPrev",
                 "media_next": "XF86_AudioNext", "media_volume_mute": "XF86_AudioMute",
                 "media_volume_down": "XF86_AudioLowerVolume", "media_volume_up": "XF86_AudioRaiseVolume"}
        ordinary = self.required - MODIFIERS
        primaries = ordinary or self.required
        self.mouse = any(t.startswith("mouse:") for t in primaries)
        self.codes = set()
        errors = []
        try:
            for primary in primaries:
                modifier = sum(masks[t] for t in self.required - {primary})
                if primary.startswith("mouse:"):
                    name = primary.split(":", 1)[1]
                    code = {"left": 1, "middle": 2, "right": 3, "x1": 8, "x2": 9}.get(name)
                    if code is None:
                        code = int(name.removeprefix("button"))
                    codes = [code]
                else:
                    name = names.get(primary, primary.upper() if primary.startswith("f") and primary[1:].isdigit() else primary)
                    # python-xlib uses XF86_ names, unlike portal/XKB strings.
                    # Import statically so frozen apps also include these keysyms.
                    symbol = (getattr(xf86, "XK_" + name, 0) if name.startswith("XF86_")
                              else XK.string_to_keysym(name))
                    code = self.display.keysym_to_keycode(symbol)
                    if not code:
                        raise RuntimeError(f"当前键盘布局没有 {primary}，请重新录入。")
                    codes = [code]
                    if primary in MODIFIERS:
                        right = self.display.keysym_to_keycode(XK.string_to_keysym(name.replace("_L", "_R")))
                        if right:
                            codes.append(right)
                # Ignore Caps/Num/Scroll lock while respecting user modifiers.
                lock_masks = {0, X.LockMask}
                modifier_map = self.display.get_modifier_mapping()
                for symbol in ("Num_Lock", "Scroll_Lock"):
                    lock_code = self.display.keysym_to_keycode(XK.string_to_keysym(symbol))
                    for index, keycodes in enumerate(modifier_map):
                        if lock_code and lock_code in keycodes:
                            lock_masks |= {mask | (1 << index) for mask in list(lock_masks)}
                for code in set(codes):
                    self.codes.add(code)
                    for lock_mask in lock_masks:
                        mod = modifier | lock_mask
                        if self.mouse:
                            root.grab_button(code, mod, False, X.ButtonPressMask | X.ButtonReleaseMask,
                                             X.GrabModeAsync, X.GrabModeAsync, X.NONE, X.NONE,
                                             onerror=lambda error, request: errors.append(error))
                        else:
                            root.grab_key(code, mod, False, X.GrabModeAsync, X.GrabModeAsync,
                                          onerror=lambda error, request: errors.append(error))
                        self.bindings.append((code, mod))
            self.display.sync()
            if errors:
                raise RuntimeError("此录音键已被其他程序占用，请选择其他键或先停用冲突程序。")
            self.thread = threading.Thread(target=self._run, daemon=True, name="voice-type-x11")
            self.thread.start()
            self.report("X11 独占录音键已启用；按住期间占用该键盘/鼠标，松开恢复。")
        except Exception:
            self._close()
            raise

    def _run(self):
        X = self.X
        pending_release = None
        try:
            while not self.stopped.is_set():
                if not self.display.pending_events():
                    if pending_release and time.monotonic() >= pending_release[1]:
                        pending_release = None
                        self._active(False)
                    select.select([self.display.fileno()], [], [], .015)
                    continue
                event = self.display.next_event()
                if event.type not in (X.KeyPress, X.KeyRelease, X.ButtonPress, X.ButtonRelease):
                    continue
                if event.detail not in self.codes:
                    continue
                pressed = event.type in (X.KeyPress, X.ButtonPress)
                if pressed:
                    # X11 auto-repeat emits release/press pairs with the same timestamp.
                    if pending_release and pending_release[0] == event.time:
                        pending_release = None
                        continue
                    if pending_release:
                        self._active(False)
                        pending_release = None
                    self._active(True)
                elif self.mouse:
                    self._active(False)
                else:
                    pending_release = (event.time, time.monotonic() + .02)
        except Exception:
            self.report("X11 输入连接断开，请重新启用录音键。")
        finally:
            self._active(False)
            self._close()

    def _active(self, value):
        if value != self.active:
            self.active = value
            self.emit(value)

    def modifiers_down(self):
        state = self.display.screen().root.query_pointer().mask
        X = self.X
        return bool(state & (X.ShiftMask | X.ControlMask | X.Mod1Mask | X.Mod4Mask | X.Mod5Mask))

    def _close(self):
        if self.display:
            try:
                self.display.close()  # Server releases both passive and active grabs.
            finally:
                self.display = None

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(1)
        else:
            self._close()
