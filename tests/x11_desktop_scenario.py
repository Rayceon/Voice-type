"""Child-process GUI fixture. Only called with an isolated test DISPLAY.

Real X11 hook, Qt clipboard, and simulated paste into a separate Qt process;
microphone and ASR are fake. Never run against a user's active desktop.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication, QPlainTextEdit

EXPECTED = "第一句。第二句。"


def target():
    class Editor(QPlainTextEdit):
        def event(self, event):
            if ((event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                 and event.key() in (Qt.Key.Key_F8, Qt.Key.Key_F2))
                    or (event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease)
                        and event.button() in (Qt.MouseButton.BackButton, Qt.MouseButton.ExtraButton6))):
                print(json.dumps({"leaked": True}), flush=True)
            return super().event(event)
    app = QApplication([])
    editor = Editor()
    editor.resize(500, 250)
    editor.show()
    editor.setFocus()
    editor.textChanged.connect(lambda: print(json.dumps({"text": editor.toPlainText()}), flush=True))
    print(json.dumps({"window": int(editor.winId())}), flush=True)
    QTimer.singleShot(12000, app.quit)
    app.exec()


def driver(trigger, activation="hold"):
    assert os.environ.get("VOICE_TYPE_TEST_DISPLAY") == os.environ.get("DISPLAY")
    from Xlib import X, XK, display
    from Xlib.ext import xtest
    from voicetype import app as desktop
    from voicetype.devices import InputDevice
    from voicetype.settings import Settings
    app = QApplication([])
    desktop.load = lambda: Settings(trigger=trigger, activation=activation)
    desktop.save = lambda _: None
    desktop.list_inputs = lambda: [InputDevice(0, "Fixture", "Test", 16000, 1)]
    desktop.resolve_input = lambda *_: InputDevice(0, "Fixture", "Test", 16000, 1)
    recorded = []
    class FakeRecording:
        thread = SimpleNamespace(join=lambda _: None)
        def __init__(self, settings, key, emit):
            self.emit = emit
        def start(self):
            recorded.append("start")
            self.emit("state", "录音中 · Fixture")
            self.emit("partial", "第一句。")
        def stop(self):
            recorded.append("stop")
            QTimer.singleShot(0, self.finish)
        def finish(self):
            self.emit("result", EXPECTED)
            self.emit("finished", None)
        def cancel(self):
            pass
    desktop.Recording = FakeRecording
    window = desktop.Window()
    window.credentials.session_key = "test-key-not-used"
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "target"],
                              stdout=subprocess.PIPE, text=True)
    messages = queue.Queue()
    reader = threading.Thread(target=lambda: [messages.put(line) for line in child.stdout], daemon=True)
    reader.start()
    probe = display.Display(os.environ["DISPLAY"])
    original_map = probe.get_pointer_mapping()
    if trigger == "mouse:button13":
        # The XTEST device has fewer than 13 physical buttons. Reproduce the
        # user's real mapping: physical button8 delivers logical button13.
        mapped = list(original_map)
        if 13 in mapped:
            mapped[mapped.index(13)] = mapped[7]
        mapped[7] = 13
        assert probe.set_pointer_mapping(mapped) == X.MappingSuccess
        probe.sync()
    received = []
    started = False
    timer = QTimer()
    result = {"success": False, "modifier_released": False, "indicator": False, "focus": False}
    target_window = None
    def send(pressed):
        mouse = trigger.startswith("mouse:")
        name = "Control_L" if trigger == "ctrl" else "F2" if trigger == "f2" else "F8"
        code = 8 if mouse else probe.keysym_to_keycode(XK.string_to_keysym(name))
        if trigger == "ctrl+f8" and pressed:
            xtest.fake_input(probe, X.KeyPress, probe.keysym_to_keycode(XK.string_to_keysym("Control_L")))
        kind = (X.ButtonPress if pressed else X.ButtonRelease) if mouse else (X.KeyPress if pressed else X.KeyRelease)
        xtest.fake_input(probe, kind, code)
        probe.sync()
    def tick():
        nonlocal started, target_window
        if recorded == ["start"] and window.indicator.isVisible():
            result["indicator"] = "录音中" in window.indicator.text()
            result["focus"] = probe.get_input_focus().focus.id == target_window
        while not messages.empty():
            message = json.loads(messages.get_nowait())
            received.append(message)
            if "window" in message and not started:
                started = True
                target_window = message["window"]
                window.enable_trigger()
                probe.create_resource_object("window", message["window"]).set_input_focus(X.RevertToParent, X.CurrentTime)
                xtest.fake_input(probe, X.MotionNotify, x=100, y=100)
                probe.sync()
                QTimer.singleShot(100, lambda: send(True))
                QTimer.singleShot(250, lambda: send(False))
                if activation == "toggle":
                    QTimer.singleShot(450, lambda: send(True))
                    QTimer.singleShot(550, lambda: send(False))
                if trigger == "ctrl+f8":
                    # Keep Ctrl down after the primary release: paste must wait.
                    def release_modifier():
                        assert not any(m.get("text") for m in received)
                        result["modifier_released"] = True
                        xtest.fake_input(probe, X.KeyRelease, probe.keysym_to_keycode(XK.string_to_keysym("Control_L")))
                        probe.sync()
                    QTimer.singleShot(650, release_modifier)
            if message.get("text") == EXPECTED:
                result["success"] = True
                # Leave time for a leaked key release to arrive as well.
                QTimer.singleShot(100, app.quit)
    timer.timeout.connect(tick)
    timer.start(10)
    QTimer.singleShot(7000, app.quit)
    try:
        app.exec()
        tick()
        assert result["success"], (received, recorded, window.status.text())
        assert recorded == ["start", "stop"], recorded
        assert result["indicator"], "Recording feedback was not visible"
        assert result["focus"], "Recording feedback stole input focus"
        if trigger == "ctrl+f8":
            assert result["modifier_released"], "Pasted before the physical modifier was released"
        assert not any(m.get("leaked") for m in received)
        assert window.result.toPlainText() == EXPECTED
        print("Desktop hook -> result -> clipboard -> external editor: passed", trigger)
    finally:
        timer.stop()
        window.quit()
        if trigger == "mouse:button13":
            probe.set_pointer_mapping(original_map)
        probe.close()
        child.terminate()
        child.wait(timeout=3)
        reader.join(1)


if __name__ == "__main__":
    if sys.argv[1] == "target":
        target()
    else:
        driver(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "hold")
