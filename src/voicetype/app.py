"""Qt desktop shell. Microphones and network connections open only on user action."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import os
import sys
from .devices import audio_backend, input_format, level, list_inputs, rescan_inputs, resolve_input
from .engine import Recording
from .settings import Credentials, Settings, config_path, load, save
from .triggers import GlobalTrigger, parse_trigger
from .ui import RecordingIndicator, build_interface

from PySide6.QtCore import QObject, QLockFile, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeyEvent, QMouseEvent
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QMainWindow, QMenu,
    QMessageBox, QStyle, QSystemTrayIcon, QVBoxLayout,
)

class Events(QObject):
    event = Signal(str, object)
    trigger = Signal(bool)


class TriggerDialog(QDialog):
    """Capture only inside this dialog, so configuring the key never starts recording."""

    def __init__(self, parent):
        super().__init__(parent)
        self.value = ""
        self.setWindowTitle("录入录音键")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("按下一个键（可搭配修饰键），或在下方点击鼠标按钮。\n完成后点确认；录入不会开始录音。"))
        self.label = QLabel("等待按键…")
        self.label.setMinimumSize(360, 100)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def _set(self, token, modifiers):
        prefixes = [name for flag, name in [
            (Qt.KeyboardModifier.ControlModifier, "cmd" if sys.platform == "darwin" else "ctrl"),
            (Qt.KeyboardModifier.MetaModifier, "ctrl" if sys.platform == "darwin" else "cmd"),
            (Qt.KeyboardModifier.AltModifier, "alt"), (Qt.KeyboardModifier.ShiftModifier, "shift")]
            if modifiers & flag and name != token]
        try:
            value = "+".join(prefixes + [token])
            parse_trigger(value)
            self.value = value
            self.label.setText(value)
        except ValueError as exc:
            self.label.setText(str(exc))

    def keyPressEvent(self, event: QKeyEvent):
        names = {Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
                 Qt.Key.Key_Escape: "esc", Qt.Key.Key_Tab: "tab", Qt.Key.Key_Backspace: "backspace",
                 Qt.Key.Key_Delete: "delete", Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
                 Qt.Key.Key_Insert: "insert", Qt.Key.Key_CapsLock: "caps_lock",
                 Qt.Key.Key_NumLock: "num_lock", Qt.Key.Key_ScrollLock: "scroll_lock",
                 Qt.Key.Key_Pause: "pause", Qt.Key.Key_Print: "print_screen",
                 Qt.Key.Key_Menu: "menu", Qt.Key.Key_AltGr: "alt_gr",
                 Qt.Key.Key_PageUp: "page_up", Qt.Key.Key_PageDown: "page_down",
                 Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right", Qt.Key.Key_Up: "up",
                 Qt.Key.Key_Down: "down", Qt.Key.Key_Shift: "shift", Qt.Key.Key_Alt: "alt",
                 Qt.Key.Key_Control: "cmd" if sys.platform == "darwin" else "ctrl",
                 Qt.Key.Key_Meta: "ctrl" if sys.platform == "darwin" else "cmd"}
        names.update({
            Qt.Key.Key_Comma: "comma", Qt.Key.Key_Period: "period", Qt.Key.Key_Slash: "slash",
            Qt.Key.Key_Semicolon: "semicolon", Qt.Key.Key_Apostrophe: "apostrophe",
            Qt.Key.Key_BracketLeft: "bracket_left", Qt.Key.Key_BracketRight: "bracket_right",
            Qt.Key.Key_Backslash: "backslash", Qt.Key.Key_QuoteLeft: "grave",
            Qt.Key.Key_Minus: "minus", Qt.Key.Key_Equal: "equal", Qt.Key.Key_Plus: "equal",
            Qt.Key.Key_Exclam: "1", Qt.Key.Key_At: "2", Qt.Key.Key_NumberSign: "3",
            Qt.Key.Key_Dollar: "4", Qt.Key.Key_Percent: "5", Qt.Key.Key_AsciiCircum: "6",
            Qt.Key.Key_Ampersand: "7", Qt.Key.Key_Asterisk: "8", Qt.Key.Key_ParenLeft: "9",
            Qt.Key.Key_ParenRight: "0", Qt.Key.Key_Underscore: "minus",
            Qt.Key.Key_Colon: "semicolon", Qt.Key.Key_QuoteDbl: "apostrophe",
            Qt.Key.Key_Less: "comma", Qt.Key.Key_Greater: "period", Qt.Key.Key_Question: "slash",
            Qt.Key.Key_Bar: "backslash", Qt.Key.Key_AsciiTilde: "grave",
            Qt.Key.Key_MediaPlay: "media_play", Qt.Key.Key_MediaStop: "media_stop",
            Qt.Key.Key_MediaRecord: "media_record", Qt.Key.Key_MediaTogglePlayPause: "media_play_pause",
            Qt.Key.Key_MediaPrevious: "media_previous", Qt.Key.Key_MediaNext: "media_next",
            Qt.Key.Key_VolumeMute: "media_volume_mute", Qt.Key.Key_VolumeDown: "media_volume_down",
            Qt.Key.Key_VolumeUp: "media_volume_up",
        })
        key = event.key()
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            token = f"f{key - Qt.Key.Key_F1 + 1}"
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            token = chr(key).lower()
        else:
            token = names.get(key, "")
        if token:
            self._set(token, event.modifiers())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        names = {Qt.MouseButton.LeftButton: "left", Qt.MouseButton.RightButton: "right",
                 Qt.MouseButton.MiddleButton: "middle", Qt.MouseButton.BackButton: "x1",
                 Qt.MouseButton.ForwardButton: "x2"}
        name = names.get(event.button())
        if name is None and sys.platform.startswith("linux"):
            # Qt ExtraButton1 is X11 button8; the legacy remap uses button13.
            name = next((f"button{number + 7}" for number in range(3, 25)
                         if event.button() == getattr(Qt.MouseButton, f"ExtraButton{number}")), None)
        if name:
            self._set("mouse:" + name, event.modifiers())
        event.accept()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Type · 语音输入")
        self.events = Events()
        self.events.event.connect(self.on_event)
        self.events.trigger.connect(self.on_trigger)
        self.recording = None
        self.manual_recording = False
        self.listener = None
        self.trigger_down = False
        self.paste_generation = 0
        self.preview_stream = None
        self.recording_settings = None
        self.quitting = False
        self.credentials = Credentials()
        self.settings_loaded = False
        try:
            self.settings = load()
            self.settings_loaded = config_path().is_file()
            initial = "选择麦克风、录音键并填写 API Key，然后启用语音输入。"
        except (ValueError, TypeError, OSError) as exc:
            self.settings = Settings()
            initial = f"无法加载设置（{type(exc).__name__}），请重新配置。原文件尚未覆盖。"
        build_interface(self, initial)
        self.indicator = RecordingIndicator(self)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(10000)
        self.preview_timer.timeout.connect(self.stop_test)
        self.pages.currentChanged.connect(lambda _: self.stop_test())
        self.device.currentIndexChanged.connect(lambda _: self.stop_test())
        self.refresh_devices()
        self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume), self)
        self.tray.setToolTip("Voice Type")
        menu = QMenu(self)
        show = QAction("打开 Voice Type", self)
        show.triggered.connect(self.show_window)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit)
        menu.addAction(show)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.quit_button.setVisible(not QSystemTrayIcon.isSystemTrayAvailable())
        self.tray.show()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.quit_button.setVisible(not QSystemTrayIcon.isSystemTrayAvailable())

    def start(self, background=False):
        if self.settings_loaded:
            self.enable_trigger(persist=False)
        else:
            self.pages.setCurrentIndex(1)
            self.navigation.button(1).setChecked(True)
        if not (background and self.listener and QSystemTrayIcon.isSystemTrayAvailable()):
            self.show_window()

    def refresh_devices(self, rescan=False):
        if self.recording:
            self.status.setText("请等待当前录音/识别结束后再刷新设备。")
            return
        selected = (self.device.currentData() if self.device.count() else
                    (self.settings.device_name, self.settings.host_api, self.settings.device_index))
        try:
            if rescan:
                self.stop_test()
            devices = rescan_inputs() if rescan else list_inputs()
        except Exception as exc:
            self.status.setText(str(exc) if isinstance(exc, RuntimeError) else "无法枚举麦克风，请检查音频服务与麦克风权限。")
            if self.device.count():
                return  # A transient enumeration failure must not change the selection.
            devices = []
        self.device.clear()
        self.device.addItem("跟随系统默认麦克风", ("", "", -1))
        duplicate_counts = {}
        for d in devices:
            duplicate_counts[(d.name, d.host_api)] = duplicate_counts.get((d.name, d.host_api), 0) + 1
        for d in devices:
            suffix = f" · 设备 {d.index}" if duplicate_counts[(d.name, d.host_api)] > 1 else ""
            self.device.addItem(d.label + suffix, (d.name, d.host_api, d.index))
        # Qt cannot reliably compare Python tuple userData via findData().
        index = next((i for i in range(self.device.count())
                      if self.device.itemData(i) == selected), -1)
        if index < 0 and selected and selected[0]:
            matches = [i for i in range(1, self.device.count())
                       if self.device.itemData(i)[:2] == selected[:2]]
            if len(matches) == 1:
                # Old configs and hotplug can change the PortAudio index.
                index = matches[0]
            else:
                label = "同名设备，请重新选择" if matches else "已断开"
                self.device.addItem(f"{label}：{selected[0]}", selected)
                index = self.device.count() - 1
        self.device.setCurrentIndex(max(0, index))

    def read_settings(self):
        name, api, device_index = self.device.currentData()
        settings = replace(self.settings, device_name=name, host_api=api, device_index=device_index,
                           trigger=self.trigger.text().strip().lower(), activation=self.activation.currentData(),
                           region=self.region.currentText(), model=self.model.text().strip(),
                           language=self.language.currentData(), auto_paste=self.paste.isChecked(),
                           hotwords=self.hotwords.toPlainText().strip(),
                           paste_shortcut=self.shortcut.currentData(), max_seconds=self.limit.value(),
                           indicator_position=self.indicator_position.currentData())
        settings.validate()
        return settings

    def capture_trigger(self):
        if self.recording:
            return
        self.disable_trigger()
        dialog = TriggerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.value:
            self.trigger.setText(dialog.value)

    def stop_test(self):
        self.preview_timer.stop()
        if self.preview_stream:
            self.preview_stream.close()
            self.preview_stream = None
            self.status.setText("麦克风测试已结束，设备已释放。")
        self.test.setText("测试麦克风")
        self.meter.setValue(0)

    def toggle_test(self):
        if self.preview_stream:
            self.stop_test()
            return
        if self.recording:
            return
        try:
            sd = audio_backend()
            d = resolve_input(*self.device.currentData())
            rate, channels = input_format(d)
            self.preview_stream = sd.InputStream(
                device=d.index, samplerate=rate, channels=channels, dtype="float32", blocksize=round(rate * .05),
                callback=lambda data, *args: self.events.event.emit("level", min(100, round(level(data) * 400))))
            self.preview_stream.start()
            self.preview_timer.start()
            self.test.setText("停止测试")
            self.status.setText(f"正在本地测试 {d.name}；10 秒后自动结束，不上传音频。")
        except Exception:
            self.stop_test()
            self.status.setText("无法打开麦克风，请检查设备权限或选择其他设备。")

    def enable_trigger(self, *, persist=True):
        if self.recording:
            return
        self.stop_test()
        try:
            settings = self.read_settings()
            resolve_input(settings.device_name, settings.host_api, settings.device_index)
            if self.key.text().strip():
                message = self.credentials.set(self.key.text(), self.remember.isChecked())
                self.key.clear()
            else:
                message = ""
            if not self.credentials.get():
                raise ValueError("请填写 API Key，或设置 DASHSCOPE_API_KEY 环境变量。")
            if persist:
                save(settings)
                self.settings_loaded = True
            self.settings = settings
            self.disable_trigger()
            self.listener = GlobalTrigger(settings.trigger, self.events.trigger.emit,
                                          lambda text: self.events.event.emit("state", message + text))
            try:
                self.listener.start()
            except Exception:
                self.disable_trigger()
                raise
        except Exception as exc:
            self.status.setText(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else
                                "启用失败，请检查设置和系统输入监控/辅助功能权限。")

    def disable_trigger(self):
        self.stop_test()
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.trigger_down = False
        if self.recording:
            self.stop_recording()
        self.status.setText("全局录音键已停用。")

    @Slot(bool)
    def on_trigger(self, pressed):
        if not self.listener or self.quitting:
            return
        self.trigger_down = pressed
        if self.settings.activation == "toggle":
            if pressed:
                self.stop_recording() if self.recording else self.start_recording(False)
        elif pressed:
            if not self.recording:
                self.start_recording(False)
        elif self.recording:
            self.stop_recording()

    def manual_record(self):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording(True)
        self.record.setChecked(self.recording is not None)

    def start_recording(self, manual):
        try:
            settings = self.read_settings() if manual else self.settings
            key = self.key.text().strip() or self.credentials.get()
            if not key:
                raise ValueError("请先填写 API Key。")
            self.stop_test()
            # The window button takes focus, so its results stay in the window.
            self.recording_settings = replace(settings, auto_paste=False) if manual else settings
            self.manual_recording = manual
            self.recording = Recording(settings, key, self.events.event.emit)
            self.paste_generation += 1
            self.result.clear()
            self.record.setText("结束录音")
            self.record.setChecked(True)
            self.enable.setEnabled(False)
            self.status.setText("正在打开麦克风…")
            if not manual:
                self.indicator.present("正在打开麦克风…", state="starting")
            self.recording.start()
        except (ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))
            if not manual:
                self.indicator.present(str(exc), dismiss_ms=5000, state="error")

    def stop_recording(self):
        if self.recording:
            self.recording.stop()
            self.record.setEnabled(False)
            self.status.setText("识别收尾中…")
            if not self.manual_recording:
                self.indicator.present("识别收尾中…", state="processing")

    @Slot(str, object)
    def on_event(self, kind, value):
        if self.quitting:
            return
        if kind in {"state", "error"}:
            self.status.setText(str(value))
            self.tray.setToolTip("Voice Type · " + str(value))
            if self.recording and not self.manual_recording:
                hint = ""
                if kind == "state" and str(value).startswith("录音中"):
                    hint = (f"\n松开 {self.settings.trigger} 结束" if self.settings.activation == "hold"
                            else f"\n再按一次 {self.settings.trigger} 结束")
                state = "error" if kind == "error" else "recording" if hint else "processing"
                self.indicator.present(str(value) + hint, dismiss_ms=5000 if kind == "error" else 0, state=state)
        elif kind == "level":
            self.meter.setValue(value)
            if self.recording and not self.manual_recording:
                self.indicator.set_level(value)
        elif kind in {"partial", "result"}:
            self.result.setPlainText(value)
            if kind == "result":
                if not self.manual_recording:
                    self.indicator.present("识别完成" if value else "没有识别到文字", dismiss_ms=2500,
                                           state="success" if value else "empty")
                self.status.setText("识别完成，可复制结果。" if value else "没有识别到文字。")
                if value and self.recording_settings.auto_paste:
                    QApplication.clipboard().setText(value)
                    if QApplication.activeWindow() is not None:
                        self.status.setText("结果已复制；请切换到目标输入框粘贴。")
                    else:
                        shortcut = self.recording_settings.paste_shortcut
                        generation = self.paste_generation
                        QTimer.singleShot(100, lambda: self.paste_result(shortcut, generation, value))
        elif kind == "finished":
            self.recording = None
            self.record.setEnabled(True)
            self.enable.setEnabled(True)
            self.record.setText("开始录音")
            self.record.setChecked(False)
            self.meter.setValue(0)
            if not self.indicator.dismiss.isActive():
                self.indicator.hide()

    def paste_result(self, shortcut, generation=None, expected=None, retries=30):
        if generation is not None and generation != self.paste_generation:
            return
        if self.quitting or self.recording or QApplication.activeWindow() is not None:
            self.status.setText("结果已复制；请在目标输入框手动粘贴。")
            return
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            self.status.setText("结果已复制；Wayland 下请在目标输入框手动粘贴。")
            return
        suspended = None
        try:
            if self.trigger_down or (self.listener and self.listener.modifiers_down()):
                if retries:
                    self.status.setText("等待松开录音键和修饰键后粘贴…")
                    QTimer.singleShot(100, lambda: self.paste_result(shortcut, generation, expected, retries - 1))
                else:
                    self.status.setText("按键仍未松开，结果已复制，请手动粘贴。")
                return
            if expected is not None and QApplication.clipboard().text() != expected:
                self.status.setText("剪贴板内容已变化，已取消自动粘贴；识别结果仍在窗口中。")
                return
            if sys.platform.startswith("linux") and self.listener:
                # X11 cannot reliably distinguish synthetic modifier events.
                # Release grabs until our Ctrl/Cmd+V has fully passed through.
                suspended = self.listener
                suspended.stop()
            from pynput.keyboard import Controller, Key
            if shortcut == "auto":
                shortcut = "cmd+v" if sys.platform == "darwin" else "ctrl+v"
            controller = Controller()
            keys = [getattr(Key, name) if name in {"ctrl", "shift", "cmd"} else name
                    for name in shortcut.split("+")]
            pressed = []
            try:
                for key in keys:
                    controller.press(key)
                    pressed.append(key)
            finally:
                for key in reversed(pressed):
                    controller.release(key)
            self.status.setText("已发送粘贴快捷键；若目标应用未接收，可手动粘贴。")
        except Exception:
            self.status.setText("自动粘贴不可用，结果已在剪贴板，请手动粘贴并检查辅助功能权限。")
        finally:
            if suspended:
                QTimer.singleShot(100, lambda: self.resume_trigger(suspended))

    def resume_trigger(self, listener):
        if self.listener is not listener or self.quitting:
            return
        try:
            listener.start()
        except Exception:
            self.listener = None
            self.status.setText("粘贴后恢复录音键失败，请重新启用全局录音键。")

    def hideEvent(self, event):
        self.stop_test()
        if self.recording and self.manual_recording and not self.quitting:
            self.stop_recording()
        super().hideEvent(event)

    def closeEvent(self, event: QCloseEvent):
        if self.quitting:
            event.accept()
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.stop_test()
            if self.recording and self.manual_recording:
                self.stop_recording()
            self.showMinimized()
            self.quit_button.show()
            self.status.setText("系统托盘不可用，已最小化并继续后台运行；需要停止时点击「退出」。")
        event.ignore()

    def quit(self):
        if self.quitting:
            return
        self.quitting = True
        self.indicator.hide()
        self.disable_trigger()
        self.stop_test()
        if self.recording:
            self.recording.cancel()
            self.recording.thread.join(1)
        self.tray.hide()
        QApplication.quit()


def notify_instance(name, background=False):
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(2000):
        return False
    socket.write(b"background\n" if background else b"show\n")
    sent = socket.waitForBytesWritten(2000)
    socket.disconnectFromServer()
    return sent


def accept_instance(server, window):
    while server.hasPendingConnections():
        socket = server.nextPendingConnection()
        socket.setParent(server)
        socket.disconnected.connect(socket.deleteLater)

        def receive(socket=socket):
            if socket.canReadLine():
                if bytes(socket.readLine(32)).strip() == b"show":
                    window.show_window()
                socket.disconnectFromServer()

        socket.readyRead.connect(receive)
        receive()


def main():
    if "--check-tls" in sys.argv or "--check-asr" in sys.argv:
        # Explicit diagnostics: no GUI, microphone or global input hooks.
        from .asr import QwenSession, check_tls
        session = None
        try:
            print(f"TLS OK: {check_tls()}")
            if "--check-asr" in sys.argv:
                key = Credentials().get()
                if not key:
                    print("ASR check failed: no saved API Key or DASHSCOPE_API_KEY", file=sys.stderr)
                    return 1
                session = QwenSession(load(), key, lambda _: None)
                session.start()
                print("ASR OK: session.updated (no audio sent)")
            return 0
        except Exception as exc:
            # Exception strings from dependencies can include credentials.
            print(f"Connection check failed ({type(exc).__name__})", file=sys.stderr)
            return 1
        finally:
            if session is not None:
                session.close()
    if "--check-audio" in sys.argv:
        # Validate the actual packaged backend, without a window, recording or network.
        try:
            backend = audio_backend()
            devices = list_inputs()
            print(f"PortAudio OK: {backend.get_portaudio_version()[1]}")
            print(f"Library: {getattr(backend, '_libname', 'unknown')}")
            print(f"Input devices: {len(devices)}")
            for device in devices:
                print(f"  {device.index}: {device.label}")
            return 0
        except Exception as exc:
            print(f"Audio check failed: {exc}", file=sys.stderr)
            if exc.__cause__:
                print(f"Cause: {exc.__cause__}", file=sys.stderr)
            return 1
    smoke = "--smoke-test" in sys.argv
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("VoiceType")
    app.setOrganizationName("VoiceType")
    path = config_path().parent
    path.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path / "app.lock"))
    server_name = "voice-type-" + hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
    if not lock.tryLock(0):
        if notify_instance(server_name, background="--background" in sys.argv):
            return 0
        QMessageBox.information(None, "Voice Type", "无法打开已运行的 Voice Type，请从系统托盘打开，或退出旧版本后重新启动。")
        return 1
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(server_name)  # Only the lock owner can remove a stale socket.
    if not server.listen(server_name):
        QMessageBox.critical(None, "Voice Type", "无法创建本地应用通信入口，请检查用户运行目录权限。")
        lock.unlock()
        return 1
    window = Window()
    server.newConnection.connect(lambda: accept_instance(server, window))
    if smoke:
        # Launch/render/exit only: no recording, credentials lookup, or global hooks.
        window.show()
        QTimer.singleShot(500, window.quit)
    else:
        QTimer.singleShot(0, lambda: window.start(background="--background" in sys.argv))
    try:
        return app.exec()
    finally:
        window.quit()
        server.close()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
