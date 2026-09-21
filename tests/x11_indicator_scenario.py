"""Non-recording overlay probe with a separate foreground application.

Use an isolated DISPLAY by default; --desktop-probe explicitly permits a brief
probe on the user's desktop. No audio, credentials, clipboard or key injection.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget


def target():
    app = QApplication([])
    label = QLabel("Voice Type 浮窗验证\n无录音、无音频上传；测试后自动关闭")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("background: #eeeeee; color: #333333; font-size: 24px")
    area = (app.screenAt(QCursor.pos()) or app.primaryScreen()).availableGeometry()
    label.setGeometry(area)
    label.show()
    print(int(label.winId()), flush=True)
    app.exec()


def probe():
    from Xlib import X, display, protocol
    from voicetype.settings import Settings
    from voicetype.ui import RecordingIndicator

    assert "--desktop-probe" in sys.argv or os.environ["DISPLAY"] == os.environ["VOICE_TYPE_TEST_DISPLAY"]
    app = QApplication([])
    connection = display.Display()
    root = connection.screen().root
    focus = connection.get_input_focus().focus
    owner = QWidget()
    owner.settings = Settings()
    owner.setWindowTitle("Voice Type overlay test owner")
    owner.show()
    indicator = RecordingIndicator(owner)
    child = None
    try:
        indicator.present("录音提示测试 · 不采集音频")
        QTest.qWait(150)
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "target"],
                                 stdout=subprocess.PIPE, text=True)
        target_id = int(child.stdout.readline())
        target_window = connection.create_resource_object("window", target_id)

        def foreground():
            root.send_event(protocol.event.ClientMessage(
                window=target_id, client_type=connection.intern_atom("_NET_ACTIVE_WINDOW"),
                data=(32, [2, X.CurrentTime, 0, 0, 0])),
                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            target_window.configure(stack_mode=X.Above)
            connection.sync()
            QTest.qWait(150)
            target_window.set_input_focus(X.RevertToParent, X.CurrentTime)
            connection.sync()
            QTest.qWait(250)

        for state in ("external foreground", "owner hidden", "owner minimized", "external fullscreen"):
            if state == "owner hidden":
                owner.hide()
            elif state == "owner minimized":
                owner.showMinimized()
            elif state == "external fullscreen":
                root.send_event(protocol.event.ClientMessage(
                    window=target_id, client_type=connection.intern_atom("_NET_WM_STATE"),
                    data=(32, [1, connection.intern_atom("_NET_WM_STATE_FULLSCREEN"), 0, 2, 0])),
                    event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                connection.sync()
            foreground()
            if state == "external foreground":
                indicator.present("录音提示测试 · 不采集音频")
            QTest.qWait(200)
            native = connection.create_resource_object("window", int(indicator.winId()))
            mapped = native.get_attributes().map_state == X.IsViewable
            rect = indicator.geometry()
            screen = app.screenAt(rect.center()) or app.primaryScreen()
            # QScreen.grabWindow(0) uses coordinates relative to that screen.
            origin = screen.geometry().topLeft()
            pixel = screen.grabWindow(0, rect.left() - origin.x() + 12,
                                      rect.top() - origin.y() + 12, 1, 1).toImage().pixelColor(0, 0)
            above = pixel.name() == "#163c38"
            kept_focus = connection.get_input_focus().focus.id == target_id
            result = dict(state=state, mapped=mapped, visible_above_other_app=above, focus_preserved=kept_focus)
            print(json.dumps(result), flush=True)
            assert mapped and above and kept_focus, result
    finally:
        indicator.hide()
        owner.close()
        if child:
            child.terminate()
            child.wait(timeout=3)
        try:
            if hasattr(focus, "set_input_focus"):
                focus.set_input_focus(X.RevertToParent, X.CurrentTime)
                connection.sync()
        finally:
            connection.close()


if __name__ == "__main__":
    target() if "target" in sys.argv else probe()
