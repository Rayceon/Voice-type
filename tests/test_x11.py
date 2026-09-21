"""Run only against an explicitly provided isolated X11 server, never the user's desktop."""
import os
import time
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("VOICE_TYPE_TEST_DISPLAY"),
                                reason="requires isolated X11 test display")


@pytest.mark.parametrize("trigger,keysym", [
    ("f8", 0xffc5), ("mouse:x1", None), ("comma", 0x2c),
    ("media_play", 0x1008ff14), ("media_play_pause", 0x1008ff14),
    ("media_stop", 0x1008ff15), ("media_record", 0x1008ff1c),
    ("media_previous", 0x1008ff16), ("media_next", 0x1008ff17),
    ("media_volume_mute", 0x1008ff12), ("media_volume_down", 0x1008ff11),
    ("media_volume_up", 0x1008ff13),
])
def test_exclusive_press_release_and_cleanup(trigger, keysym):
    from Xlib import X, display
    from Xlib.ext import xtest
    from voicetype.x11_trigger import X11Trigger
    name = os.environ["VOICE_TYPE_TEST_DISPLAY"]
    probe = display.Display(name)
    root = probe.screen().root
    window = root.create_window(20, 20, 400, 200, 0, probe.screen().root_depth,
                                 X.InputOutput, X.CopyFromParent,
                                 event_mask=X.KeyPressMask | X.KeyReleaseMask | X.ButtonPressMask | X.ButtonReleaseMask)
    window.map()
    window.set_input_focus(X.RevertToParent, X.CurrentTime)
    probe.sync()
    events = []
    listener = X11Trigger(trigger, events.append, lambda *_: None, name)
    mouse = keysym is None
    code = 8 if mouse else probe.keysym_to_keycode(keysym)
    assert code, f"Isolated test keyboard has no mapping for {trigger}"
    down, up = (X.ButtonPress, X.ButtonRelease) if mouse else (X.KeyPress, X.KeyRelease)
    def click():
        xtest.fake_input(probe, X.MotionNotify, x=40, y=40)
        xtest.fake_input(probe, down, code)
        probe.sync()
        time.sleep(.08)
        xtest.fake_input(probe, up, code)
        probe.sync()
        time.sleep(.08)
    def target_events():
        received = []
        while probe.pending_events():
            event = probe.next_event()
            if event.type in (down, up):
                received.append(event.type)
        return received
    try:
        listener.start()
        conflict = X11Trigger(trigger, lambda *_: None, lambda *_: None, name)
        with pytest.raises(RuntimeError, match="占用"):
            conflict.start()
        click()
        assert events == [True, False]
        assert target_events() == []
        listener.stop()
        click()
        assert target_events() == [down, up]
    finally:
        listener.stop()
        window.destroy()
        probe.close()


@pytest.mark.parametrize("trigger,activation", [("f8", "hold"), ("mouse:x1", "hold"),
    ("ctrl", "hold"), ("ctrl+f8", "hold"), ("mouse:button13", "hold"), ("f2", "toggle")])
def test_desktop_input_into_separate_process(trigger, activation):
    env = dict(os.environ, DISPLAY=os.environ["VOICE_TYPE_TEST_DISPLAY"],
               QT_QPA_PLATFORM="xcb", XDG_SESSION_TYPE="x11")
    script = Path(__file__).with_name("x11_desktop_scenario.py")
    result = subprocess.run([sys.executable, str(script), trigger, activation], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_indicator_above_external_window_after_hiding_owner():
    from Xlib import X, display
    probe = display.Display(os.environ["VOICE_TYPE_TEST_DISPLAY"])
    try:
        wm = probe.screen().root.get_full_property(
            probe.intern_atom("_NET_SUPPORTING_WM_CHECK"), X.AnyPropertyType)
        if not wm:
            pytest.skip("Stacking verification needs a window manager; bare Xephyr has none")
    finally:
        probe.close()
    env = dict(os.environ, DISPLAY=os.environ["VOICE_TYPE_TEST_DISPLAY"],
               QT_QPA_PLATFORM="xcb", XDG_SESSION_TYPE="x11")
    script = Path(__file__).with_name("x11_indicator_scenario.py")
    result = subprocess.run([sys.executable, str(script)], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
