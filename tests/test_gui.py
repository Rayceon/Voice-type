import os
import sys
from types import SimpleNamespace
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QProgressBar

from voicetype import app as desktop
from voicetype.devices import InputDevice
from voicetype.settings import Settings


@pytest.mark.parametrize("key,token", [
    (Qt.Key.Key_Insert, "insert"), (Qt.Key.Key_CapsLock, "caps_lock"),
    (Qt.Key.Key_NumLock, "num_lock"), (Qt.Key.Key_ScrollLock, "scroll_lock"),
    (Qt.Key.Key_Pause, "pause"), (Qt.Key.Key_Print, "print_screen"),
    (Qt.Key.Key_Menu, "menu"), (Qt.Key.Key_AltGr, "alt_gr"),
])
def test_special_key_capture(key, token):
    app = QApplication.instance() or QApplication([])
    dialog = desktop.TriggerDialog(None)
    try:
        dialog.show()
        QTest.keyClick(dialog, key)
        assert dialog.value == token
    finally:
        dialog.reject()


def test_first_run_device_selection_and_key_capture(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings())
    monkeypatch.setattr(desktop, "list_inputs", lambda: [InputDevice(7, "USB mic", "ALSA", 48000, 1)])
    window = desktop.Window()
    assert window.listener is None
    assert window.recording is None
    assert window.device.count() == 2
    assert window.device.currentData() == ("", "", -1)
    window.device.setCurrentIndex(1)
    assert window.read_settings().device_name == "USB mic"
    assert window.read_settings().device_index == 7
    dialog = desktop.TriggerDialog(window)
    dialog.show()
    QTest.keyClick(dialog, Qt.Key.Key_F9)
    assert dialog.value == "f9"
    QTest.keyClick(dialog, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert dialog.value == ("cmd+shift+space" if sys.platform == "darwin" else "ctrl+shift+space")
    QTest.keyClick(dialog, Qt.Key.Key_Comma)
    assert dialog.value == "comma"
    QTest.keyClick(dialog, Qt.Key.Key_Exclam, Qt.KeyboardModifier.ShiftModifier)
    assert dialog.value == "shift+1"
    dialog.reject()
    window.quitting = True
    window.tray.hide()
    window.close()


def test_missing_saved_device_is_not_silently_replaced(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings(device_name="missing", host_api="ALSA"))
    monkeypatch.setattr(desktop, "list_inputs", lambda: [])
    window = desktop.Window()
    assert window.device.currentData() == ("missing", "ALSA", -1)
    assert "已断开" in window.device.currentText()
    window.quitting = True
    window.tray.hide()
    window.close()


@pytest.mark.parametrize("saved_index", [-1, 3])
def test_unique_saved_device_rebinds_in_picker(monkeypatch, saved_index):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings(
        device_name="USB mic", host_api="ALSA", device_index=saved_index))
    monkeypatch.setattr(desktop, "list_inputs", lambda: [
        InputDevice(7, "USB mic", "ALSA", 48000, 1)])
    window = desktop.Window()
    try:
        assert window.device.currentData() == ("USB mic", "ALSA", 7)
        assert window.device.count() == 2
        assert window.read_settings().device_index == 7
        monkeypatch.setattr(desktop, "rescan_inputs", lambda: [
            InputDevice(9, "USB mic", "ALSA", 48000, 1)])
        window.refresh_devices(rescan=True)
        assert window.device.currentData() == ("USB mic", "ALSA", 9)
        assert "已断开" not in window.device.currentText()
    finally:
        window.quitting = True
        window.tray.hide()
        window.close()


@pytest.mark.parametrize("saved_index", [-1, 3, 7])
def test_duplicate_device_picker_never_guesses(monkeypatch, saved_index):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings(
        device_name="USB mic", host_api="ALSA", device_index=saved_index))
    monkeypatch.setattr(desktop, "list_inputs", lambda: [
        InputDevice(7, "USB mic", "ALSA", 48000, 1),
        InputDevice(9, "USB mic", "ALSA", 48000, 1)])
    window = desktop.Window()
    try:
        assert window.device.currentData() == ("USB mic", "ALSA", saved_index)
        if saved_index != 7:
            assert "同名设备" in window.device.currentText()
            assert "重新选择" in window.device.currentText()
        else:
            assert "设备 7" in window.device.currentText()
        assert window.device.itemText(1) != window.device.itemText(2)
        window.device.setCurrentIndex(2)
        assert window.read_settings().device_index == 9
    finally:
        window.quitting = True
        window.tray.hide()
        window.close()


def test_saved_device_never_rebinds_to_another_host_api(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings(
        device_name="USB mic", host_api="ALSA", device_index=7))
    monkeypatch.setattr(desktop, "list_inputs", lambda: [
        InputDevice(7, "USB mic", "Other API", 48000, 1)])
    window = desktop.Window()
    try:
        assert window.device.currentData() == ("USB mic", "ALSA", 7)
        assert "已断开" in window.device.currentText()
    finally:
        window.quitting = True
        window.tray.hide()
        window.close()


def test_refresh_closes_preview_and_preserves_selection_on_failure(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings(device_name="USB mic", host_api="ALSA"))
    monkeypatch.setattr(desktop, "list_inputs", lambda: [InputDevice(2, "USB mic", "ALSA", 48000, 1)])
    window = desktop.Window()
    calls = []
    selected = window.device.currentData()
    window.preview_stream = SimpleNamespace(close=lambda: calls.append("close"))
    def rescan():
        assert calls == ["close"]
        raise RuntimeError("temporary enumeration failure")
    monkeypatch.setattr(desktop, "rescan_inputs", rescan)
    window.refresh_devices(rescan=True)
    assert window.preview_stream is None
    assert window.device.currentData() == selected
    assert "temporary" in window.status.text()
    window.recording = object()
    window.refresh_devices(rescan=True)
    assert "当前录音" in window.status.text()
    assert calls == ["close"]
    window.recording = None
    window.quitting = True
    window.tray.hide()
    window.close()


def test_initial_device_error_preserves_saved_choice(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings(device_name="USB mic", host_api="ALSA"))
    def fail():
        raise RuntimeError("no audio service")
    monkeypatch.setattr(desktop, "list_inputs", fail)
    window = desktop.Window()
    assert window.device.currentData() == ("USB mic", "ALSA", -1)
    assert window.status.text() == "no audio service"
    window.quitting = True
    window.tray.hide()
    window.close()


@pytest.fixture
def ui_window(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(desktop, "load", lambda: Settings())
    monkeypatch.setattr(desktop, "list_inputs", lambda: [
        InputDevice(7, "USB mic " * 30, "ALSA", 48000, 1)])
    window = desktop.Window()
    window.show()
    app.processEvents()
    yield window
    window.recording = None
    window.indicator.hide()
    window.quitting = True
    window.tray.hide()
    window.close()


def test_hotwords_load_save_and_recording_snapshot(monkeypatch, tmp_path):
    from voicetype.settings import load, save
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "settings.json"
    save(Settings(hotwords="旧热词", trigger="f9"), path)
    monkeypatch.setattr(desktop, "load", lambda: load(path))
    monkeypatch.setattr(desktop, "save", lambda settings: save(settings, path))
    monkeypatch.setattr(desktop, "list_inputs", lambda: [])
    monkeypatch.setattr(desktop, "resolve_input", lambda *args: None)
    monkeypatch.setattr(desktop, "GlobalTrigger", lambda *args: SimpleNamespace(
        start=lambda: None, stop=lambda: None))
    sessions = []
    def recording(settings, *args):
        sessions.append(settings)
        return SimpleNamespace(start=lambda: None, stop=lambda: None)
    monkeypatch.setattr(desktop, "Recording", recording)
    window = desktop.Window()
    monkeypatch.setattr(window.credentials, "get", lambda: "fake-key")
    try:
        assert window.hotwords.toPlainText() == "旧热词"
        window.hotwords.setPlainText(" 星尘智能\nVoice Type ")
        window.enable_trigger()
        assert load(path).hotwords == "星尘智能\nVoice Type"
        assert load(path).trigger == "f9"
        window.hotwords.setPlainText("未保存的词")
        window.start_recording(False)
        assert sessions[-1].hotwords == "星尘智能\nVoice Type"
        window.on_event("finished", None)
        window.start_recording(True)
        assert sessions[-1].hotwords == "未保存的词"
        window.hotwords.setPlainText("录音中的修改")
        assert sessions[-1].hotwords == "未保存的词"
        window.on_event("finished", None)
        window.hotwords.clear()
        window.enable_trigger()
        assert load(path).hotwords == ""
    finally:
        window.recording = None
        window.quitting = True
        window.tray.hide()
        window.close()


def test_hotwords_over_limit_rejected_before_save(ui_window, monkeypatch):
    from voicetype.settings import HOTWORDS_MAX_CHARS
    saved = []
    monkeypatch.setattr(desktop, "save", saved.append)
    ui_window.hotwords.setPlainText("词" * (HOTWORDS_MAX_CHARS + 1))
    ui_window.enable_trigger()
    assert "热词最多" in ui_window.status.text()
    assert not saved
    assert ui_window.listener is None


def test_page_navigation_preserves_draft_without_side_effects(ui_window):
    w = ui_window
    original = w.read_settings()
    w.key.setText("test-key-not-a-real-secret")
    assert w.pages.currentIndex() == 0
    w.navigation.button(1).click()
    assert w.pages.currentIndex() == 1
    assert w.key.echoMode() == QLineEdit.EchoMode.Password
    assert w.read_settings() == original
    w.trigger.setText("f9")
    w.navigation.button(0).click()
    assert w.read_settings().trigger == "f9"
    assert w.settings.trigger == original.trigger
    assert w.key.text() == "test-key-not-a-real-secret"
    assert w.listener is None and w.recording is None and w.preview_stream is None


def test_result_count_and_copy_follow_text(ui_window):
    w = ui_window
    assert not w.copy_result.isEnabled()
    w.on_event("partial", "第一句。第二句。")
    assert w.character_count.text() == "8 字符"
    assert w.copy_result.isEnabled()
    w.result.setPlainText("编辑后的文字")
    clipboard = QApplication.clipboard()
    previous = clipboard.text()
    try:
        w.copy_result.click()
        assert clipboard.text() == "编辑后的文字"
    finally:
        clipboard.setText(previous)
    w.result.clear()
    assert not w.copy_result.isEnabled()
    assert w.character_count.text() == "0 字符"


def test_small_window_settings_scroll_and_meter(ui_window):
    w = ui_window
    w.resize(660, 620)
    w.navigation.button(1).click()
    QApplication.processEvents()
    assert w.width() == 660
    assert w.settings_scroll.horizontalScrollBar().maximum() == 0
    assert w.settings_scroll.verticalScrollBar().maximum() > 0
    w.settings_scroll.ensureWidgetVisible(w.limit)
    QApplication.processEvents()
    viewport = w.settings_scroll.viewport()
    assert viewport.rect().contains(w.limit.mapTo(viewport, w.limit.rect().center()))
    assert w.enable.isVisible() and w.disable.isVisible() and w.status.isVisible()
    w.on_event("level", 42)
    assert all(meter.value() == 42 for meter in w.findChildren(QProgressBar))
    w.navigation.button(0).click()
    QApplication.processEvents()
    assert w.result.isVisible() and w.result.height() >= 90
    assert w.record.isVisible()


def test_record_button_failed_start_and_finished_state(ui_window, monkeypatch):
    w = ui_window
    monkeypatch.setattr(w.credentials, "get", lambda: "")
    w.record.click()
    assert not w.record.isChecked()
    assert w.recording is None
    assert "API Key" in w.status.text()
    w.record.setText("结束录音")
    w.record.setChecked(True)
    w.record.setEnabled(False)
    w.on_event("finished", None)
    assert w.record.text() == "开始录音"
    assert not w.record.isChecked()
    assert w.record.isEnabled()


@pytest.mark.parametrize("action", ["page", "hide", "device", "disable"])
def test_preview_released_when_leaving_test(ui_window, action):
    w = ui_window
    w.pages.setCurrentIndex(1)
    calls = []
    w.preview_stream = SimpleNamespace(close=lambda: calls.append("close"))
    w.test.setText("停止测试")
    if action == "page":
        w.pages.setCurrentIndex(0)
    elif action == "hide":
        w.hide()
    elif action == "device":
        w.device.setCurrentIndex(1)
    else:
        w.disable_trigger()
    assert calls == ["close"]
    assert w.preview_stream is None
    assert w.test.text() == "测试麦克风"


def test_preview_timeout_releases_device(ui_window, monkeypatch):
    w = ui_window
    calls = []
    monkeypatch.setattr(desktop, "resolve_input", lambda *_: SimpleNamespace(index=1, name="mic"))
    monkeypatch.setattr(desktop, "input_format", lambda _: (48000, 1))
    monkeypatch.setattr(desktop, "audio_backend", lambda: SimpleNamespace(
        InputStream=lambda **_: SimpleNamespace(start=lambda: None, close=lambda: calls.append("close"))))
    w.toggle_test()
    assert w.preview_timer.isActive()
    w.preview_timer.timeout.emit()
    assert calls == ["close"]
    assert w.preview_stream is None
    assert not w.preview_timer.isActive()


@pytest.mark.parametrize("manual", [True, False])
def test_hiding_window_stops_manual_but_not_global_recording(ui_window, manual):
    w = ui_window
    calls = []
    w.manual_recording = manual
    w.recording = SimpleNamespace(stop=lambda: calls.append("stop"))
    w.hide()
    assert calls == (["stop"] if manual else [])


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="X11 button numbering")
@pytest.mark.parametrize("number", [3, 6, 24])
def test_capture_extra_mouse_buttons(number):
    app = QApplication.instance() or QApplication([])
    dialog = desktop.TriggerDialog(None)
    try:
        dialog.show()
        QTest.mouseClick(dialog, getattr(Qt.MouseButton, f"ExtraButton{number}"))
        assert dialog.value == f"mouse:button{number + 7}"
        QTest.mouseClick(dialog, getattr(Qt.MouseButton, f"ExtraButton{number}"), Qt.KeyboardModifier.ControlModifier)
        assert dialog.value == f"ctrl+mouse:button{number + 7}"
    finally:
        dialog.reject()


@pytest.mark.parametrize("activation,hint", [("hold", "松开 f2"), ("toggle", "再按一次 f2")])
def test_global_f2_feedback_lifecycle(ui_window, monkeypatch, activation, hint):
    w = ui_window
    calls = []
    class FakeRecording:
        def __init__(self, settings, key, emit):
            self.emit = emit
        def start(self):
            calls.append("start")
        def stop(self):
            calls.append("stop")
    monkeypatch.setattr(desktop, "Recording", FakeRecording)
    monkeypatch.setattr(w.credentials, "get", lambda: "test-key")
    w.settings = Settings(trigger="f2", activation=activation, auto_paste=False)
    w.listener = SimpleNamespace(stop=lambda: None)
    w.hide()
    w.on_trigger(True)
    assert calls == ["start"]
    assert w.indicator.isVisible()
    w.on_event("state", "录音中 · USB mic")
    assert hint in w.indicator.text()
    assert w.indicator.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    w.on_trigger(False)
    if activation == "toggle":
        assert calls == ["start"]
        w.on_trigger(True)
    assert calls == ["start", "stop"]
    assert "收尾" in w.indicator.text()
    w.on_event("result", "第一句。第二句。")
    w.on_event("finished", None)
    assert "识别完成" in w.indicator.text()
    assert w.result.toPlainText() == "第一句。第二句。"
    w.indicator.dismiss.timeout.emit()
    assert not w.indicator.isVisible()


def test_global_record_error_is_visible(ui_window, monkeypatch):
    w = ui_window
    monkeypatch.setattr(w.credentials, "get", lambda: "")
    w.key.clear()
    w.hide()
    w.start_recording(False)
    assert w.indicator.isVisible()
    assert "API Key" in w.indicator.text()
    assert w.indicator.dismiss.isActive()


@pytest.mark.parametrize("position", ["bottom_center", "bottom_left", "bottom_right",
                                     "top_center", "top_left", "top_right"])
def test_indicator_position_preview_is_safe(ui_window, position):
    from PySide6.QtGui import QCursor
    w = ui_window
    w.indicator_position.setCurrentIndex(w.indicator_position.findData(position))
    assert w.read_settings().indicator_position == position
    assert w.settings.indicator_position == "bottom_center"
    w.preview_indicator.click()
    QApplication.processEvents()
    assert w.indicator.isVisible()
    assert w.recording is None and w.listener is None and w.preview_stream is None
    area = (QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()).availableGeometry()
    geometry = w.indicator.geometry()
    assert area.contains(geometry)
    assert (geometry.center().y() < area.center().y()) == position.startswith("top")
    if position.endswith("left"):
        assert geometry.left() == area.left() + 24
    elif position.endswith("right"):
        assert geometry.right() == area.right() - 24
    else:
        assert abs(geometry.center().x() - area.center().x()) <= 1
    assert w.indicator.dismiss.interval() == 3000


def test_indicator_independent_of_main_window(ui_window):
    w = ui_window
    assert w.indicator.parentWidget() is None
    assert w.indicator.windowType() == Qt.WindowType.Tool
    w.indicator.present("录音中")
    w.hide()
    QApplication.processEvents()
    assert w.indicator.isVisible()
    w.showMinimized()
    QApplication.processEvents()
    assert w.indicator.isVisible()
    w.indicator.hide()


@pytest.mark.parametrize("name", ["device", "activation", "region", "language", "shortcut", "indicator_position", "limit"])
@pytest.mark.parametrize("focused", [False, True])
def test_settings_wheel_scrolls_page_without_changing_value(ui_window, name, focused):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QComboBox
    w = ui_window
    w.pages.setCurrentIndex(1)
    widget = getattr(w, name)
    if isinstance(widget, QComboBox):
        widget.setCurrentIndex(1)
        value = widget.currentIndex
    else:
        value = widget.value
    w.settings_scroll.ensureWidgetVisible(widget)
    widget.setFocus() if focused else w.enable.setFocus()
    QApplication.processEvents()
    bar = w.settings_scroll.verticalScrollBar()
    before_scroll, before_value = bar.value(), value()
    delta = 120 if before_scroll else -120
    QTest.wheelEvent(w.windowHandle(), widget.mapTo(w, widget.rect().center()), QPoint(0, delta))
    QApplication.processEvents()
    assert value() == before_value
    assert bar.value() != before_scroll


@pytest.mark.parametrize('tray_available', [True, False])
def test_close_keeps_global_service_until_explicit_quit(ui_window, monkeypatch, tray_available):
    w = ui_window
    calls = []
    monkeypatch.setattr(desktop.QSystemTrayIcon, 'isSystemTrayAvailable', lambda: tray_available)
    w.listener = SimpleNamespace(stop=lambda: calls.append('stop'))
    assert not w.close()
    QApplication.processEvents()
    assert not w.quitting and w.listener is not None
    assert calls == []
    assert not w.isVisible() if tray_available else w.isMinimized()
    w.show_window()
    assert w.isVisible() and not w.isMinimized()
    w.tray.contextMenu().actions()[-1].trigger()
    assert w.quitting and w.listener is None and not w.tray.isVisible()
    assert calls == ['stop']


@pytest.mark.parametrize('condition', ['saved', 'first_run', 'missing_key', 'hook_failure'])
def test_background_start_restores_only_saved_setup(ui_window, monkeypatch, condition):
    w = ui_window
    w.hide()
    calls = []
    w.settings_loaded = condition != 'first_run'
    monkeypatch.setattr(desktop.QSystemTrayIcon, 'isSystemTrayAvailable', lambda: True)
    monkeypatch.setattr(w.credentials, 'get', lambda: '' if condition == 'missing_key' else 'fake-key')
    monkeypatch.setattr(desktop, 'resolve_input', lambda *args: None)
    monkeypatch.setattr(desktop, 'save', lambda *_: pytest.fail('Startup must not rewrite settings'))
    def start():
        calls.append('start')
        if condition == 'hook_failure':
            raise RuntimeError('hook unavailable')
    monkeypatch.setattr(desktop, 'GlobalTrigger', lambda *args: SimpleNamespace(
        start=start, stop=lambda: calls.append('stop')))
    w.start(background=True)
    assert (w.listener is not None) == (condition == 'saved')
    assert w.isVisible() == (condition != 'saved')
    assert calls == ({'saved': ['start'], 'hook_failure': ['start', 'stop']}.get(condition, []))
    if condition == 'hook_failure':
        assert 'hook unavailable' in w.status.text()
    w.quit()


def test_selector_keyboard_and_popup_still_work(ui_window):
    w = ui_window
    w.pages.setCurrentIndex(1)
    w.language.setCurrentIndex(0)
    w.settings_scroll.ensureWidgetVisible(w.language)
    w.language.setFocus()
    QTest.keyClick(w.language, Qt.Key.Key_Down)
    assert w.language.currentIndex() == 1
    w.language.showPopup()
    QApplication.processEvents()
    assert w.language.view().isVisible()
    QTest.keyClick(w.language.view(), Qt.Key.Key_Down)
    QTest.keyClick(w.language.view(), Qt.Key.Key_Return)
    assert w.language.currentIndex() == 2


def test_indicator_audio_clock_and_animation_lifecycle(ui_window):
    w = ui_window
    w.recording = object()
    w.manual_recording = False
    w.on_event('state', '录音中 · Test microphone')
    assert w.indicator.state == 'recording'
    assert w.indicator.motion.isActive()
    w.indicator.record_clock = SimpleNamespace(elapsed=lambda: 65000, isValid=lambda: True)
    w.on_event('level', 81)
    w.indicator.tick()
    assert w.indicator.elapsed_label.text() == '01:05'
    assert max(w.indicator.bars) > 0
    # Repeated status messages must not reset the recording clock.
    w.on_event('state', '录音中 · Test microphone')
    w.indicator.tick()
    assert w.indicator.elapsed_label.text() == '01:05'
    w.on_event('state', '识别收尾中…')
    assert w.indicator.state == 'processing'
    w.on_event('level', 99)
    assert not any(w.indicator.levels)
    w.on_event('error', '<connection failed>')
    assert w.indicator.state == 'error'
    assert w.indicator.detail.text() == '<connection failed>'
    assert w.indicator.detail.textFormat() == Qt.TextFormat.PlainText
    assert not w.indicator.motion.isActive()
    w.indicator.hide()
    assert not w.indicator.motion.isActive() and not w.indicator.dismiss.isActive()
    w.indicator.set_level(100)
    assert not any(w.indicator.levels)


def test_indicator_preview_never_uses_microphone_levels(ui_window):
    w = ui_window
    w.preview_indicator.click()
    w.on_event('level', 100)
    assert w.indicator.state == 'preview'
    assert not any(w.indicator.levels)
    w.indicator.tick()
    assert max(w.indicator.bars) > 0
    assert '不使用麦克风' in w.indicator.detail.text()
    assert w.recording is None
    w.indicator.hide()
    assert not w.indicator.motion.isActive()
