"""Desktop presentation; recording and input behavior stay in app.Window."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .settings import ENDPOINTS, INDICATOR_POSITIONS


class RecordingIndicator(QLabel):
    """Global recording feedback without activating a window or taking input."""

    def __init__(self, parent):
        # A parented Tooltip is tied to the owner's activation/minimization by
        # desktop window managers. Dictation feedback must outlive that state.
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        if QApplication.platformName() == "xcb":
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        super().__init__(None, flags)
        self.owner = parent  # Read settings without native transient-parent ownership.
        self.setWindowTitle("Voice Type · 录音提示")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setFixedWidth(340)
        self.setStyleSheet("QLabel { background: #163c38; color: white; border: 1px solid #397c70;"
                           "border-radius: 12px; padding: 18px; font-size: 16px; }")
        self.dismiss = QTimer(self)
        self.dismiss.setSingleShot(True)
        self.dismiss.timeout.connect(self.hide)

    def present(self, text, dismiss_ms=0, position=None):
        self.dismiss.stop()
        self.setText(text)
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if position is None:
            parent = self.owner
            position = parent.settings.indicator_position if parent else "bottom_center"
        vertical, horizontal = position.split("_")
        x = {"left": area.left() + 24, "center": area.center().x() - self.width() // 2,
             "right": area.right() - self.width() - 23}[horizontal]
        y = area.top() + 24 if vertical == "top" else area.bottom() - self.height() - 35
        self.move(max(area.left(), min(x, area.right() - self.width() + 1)),
                  max(area.top(), min(y, area.bottom() - self.height() + 1)))
        self.show()
        self.raise_()
        if dismiss_ms:
            self.dismiss.start(dismiss_ms)


STYLE = """
QMainWindow, QWidget#shell { background: #f4f6f8; }
QWidget { color: #253641; font-size: 14px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 20px; font-weight: 700; }
QLabel#monogram { background: #116d66; color: white; border-radius: 12px;
                  font-size: 17px; font-weight: 700; }
QLabel#eyebrow { color: #537d78; font-size: 11px; font-weight: 700; }
QLabel#heading { font-size: 28px; font-weight: 700; color: #182e38; }
QLabel#sectionTitle { font-size: 16px; font-weight: 600; }
QLabel#muted { color: #657682; font-size: 12px; }
QFrame#card { background: #ffffff; border: 1px solid #dfe6e9; border-radius: 16px; }
QFrame#recorder { background: #e7f2ee; border: 1px solid #c9e2d9; border-radius: 16px; }
QPushButton { background: #ffffff; border: 1px solid #cfd9de; border-radius: 8px;
              padding: 9px 16px; font-weight: 500; }
QPushButton:hover { background: #eef4f3; border-color: #81aaa3; }
QPushButton:pressed { background: #dcebe7; }
QPushButton:focus { border: 1px solid #167d72; }
QPushButton:disabled { color: #93a1a8; background: #f0f3f5; border-color: #e3e9ed; }
QPushButton#primary { background: #116d66; color: white; border-color: #116d66; }
QPushButton#primary:hover { background: #0c5b54; }
QPushButton#primary:disabled { background: #a7bfbb; border-color: #a7bfbb; color: #f5f8f7; }
QPushButton#record { background: #116d66; color: white; border-color: #116d66;
                    padding: 12px 24px; font-size: 15px; }
QPushButton#record:hover { background: #0c5b54; }
QPushButton#record:checked { background: #ac433d; border-color: #ac433d; }
QPushButton#record:disabled { background: #92aaa6; border-color: #92aaa6; }
QPushButton#nav { background: transparent; border: 1px solid transparent; color: #657682; }
QPushButton#nav:checked { background: white; border-color: #dbe4e7; color: #116d66; }
QPushButton#nav:focus { border-color: #167d72; }
QLineEdit, QComboBox, QSpinBox { background: #fafcfd; border: 1px solid #cfd9de;
    border-radius: 7px; padding: 8px 10px; min-height: 20px; selection-background-color: #c5e7df;
    selection-color: #182e38; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #167d72; }
QComboBox QAbstractItemView { background: white; color: #253641;
    selection-background-color: #d9eee8; selection-color: #153c36; }
QPlainTextEdit { background: white; border: none; font-size: 17px; padding: 4px;
    selection-background-color: #c5e7df; selection-color: #182e38; }
QPlainTextEdit:focus { border: none; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QProgressBar { background: #d5e4df; border: none; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: #218979; border-radius: 3px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 0; }
QScrollBar::handle:vertical { background: #c7d3d8; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #253641; color: white; border: none; padding: 6px; }
"""


def label(text, role=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if role:
        widget.setObjectName(role)
    return widget


def card(parent_layout, title=None, subtitle=None, name="card", stretch=0):
    frame = QFrame()
    frame.setObjectName(name)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(12)
    if title:
        layout.addWidget(label(title, "sectionTitle"))
    if subtitle:
        layout.addWidget(label(subtitle, "muted"))
    parent_layout.addWidget(frame, stretch)
    return layout


def field(layout, title, widget):
    caption = label(title)
    caption.setBuddy(widget)
    widget.setAccessibleName(title)
    layout.addWidget(caption)
    layout.addWidget(widget)


def build_interface(window, initial):
    w = window
    w.resize(880, 800)
    w.setMinimumSize(660, 620)
    font = QFont()
    font.setFamilies(["Inter", "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC"])
    w.setFont(font)
    w.setStyleSheet(STYLE)
    root = QWidget()
    root.setObjectName("shell")
    w.setCentralWidget(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(28, 24, 28, 20)
    layout.setSpacing(18)

    header = QHBoxLayout()
    logo = label("VT", "monogram")
    logo.setFixedSize(42, 42)
    logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    header.addWidget(logo)
    header.addSpacing(4)
    header.addWidget(label("Voice Type", "brand"))
    header.addStretch()
    w.pages = QStackedWidget()
    w.navigation = QButtonGroup(w)
    for index, title in enumerate(["听写", "设置"]):
        button = QPushButton(title)
        button.setObjectName("nav")
        button.setCheckable(True)
        button.setChecked(index == 0)
        w.navigation.addButton(button, index)
        header.addWidget(button)
    w.navigation.idClicked.connect(w.pages.setCurrentIndex)
    layout.addLayout(header)
    layout.addWidget(w.pages, 1)

    workspace = QWidget()
    work = QVBoxLayout(workspace)
    work.setContentsMargins(0, 4, 0, 0)
    work.setSpacing(16)
    work.addWidget(label("VOICE TO TEXT", "eyebrow"))
    work.addWidget(label("把想法，说成文字。", "heading"))
    work.addWidget(label("专注表达，文字随后。首次使用请先到「设置」配置麦克风与识别服务。", "muted"))
    recorder = card(work, name="recorder")
    row = QHBoxLayout()
    text = QVBoxLayout()
    text.addWidget(label("窗口听写", "sectionTitle"))
    text.addWidget(label("点击开始，再次点击结束。结果留在下方，不自动粘贴。", "muted"))
    row.addLayout(text, 1)
    w.record = QPushButton("开始录音")
    w.record.setObjectName("record")
    w.record.setCheckable(True)
    # Checked state follows the recording lifecycle, not mouse clicks.
    w.record.clicked.connect(w.manual_record)
    row.addWidget(w.record)
    recorder.addLayout(row)
    w.meter = QProgressBar()
    w.meter.setAccessibleName("麦克风输入音量")
    w.meter.setRange(0, 100)
    w.meter.setValue(0)
    w.meter.setTextVisible(False)
    recorder.addWidget(w.meter)
    result = card(work, stretch=1)
    row = QHBoxLayout()
    row.addWidget(label("识别结果", "sectionTitle"))
    w.character_count = label("0 字符", "muted")
    row.addWidget(w.character_count)
    row.addStretch()
    w.copy_result = QPushButton("复制文字")
    w.copy_result.setEnabled(False)
    row.addWidget(w.copy_result)
    result.addLayout(row)
    w.result = QPlainTextEdit()
    w.result.setAccessibleName("识别结果，可编辑")
    w.result.setPlaceholderText("你的下一段文字，从开口开始。\n\n识别结果会显示在这里，可以编辑后复制。")
    w.result.setMinimumHeight(90)
    result.addWidget(w.result, 1)
    w.copy_result.clicked.connect(lambda: QApplication.clipboard().setText(w.result.toPlainText()))

    def update_result_summary():
        text = w.result.toPlainText()
        w.character_count.setText(f"{len(text)} 字符")
        w.copy_result.setEnabled(bool(text))

    w.result.textChanged.connect(update_result_summary)
    work.addWidget(label("云端识别 · 仅录音时上传音频 · 不自动发送消息", "muted"))
    w.pages.addWidget(workspace)

    w.settings_scroll = QScrollArea()
    w.settings_scroll.setWidgetResizable(True)
    settings_page = QWidget()
    settings_page.setObjectName("shell")
    settings_layout = QVBoxLayout(settings_page)
    settings_layout.setContentsMargins(0, 4, 12, 4)
    settings_layout.setSpacing(16)
    settings_layout.addWidget(label("让听写适合你的习惯", "heading"))
    settings_layout.addWidget(label("修改后点击底部「保存并启用」。窗口听写会直接使用当前填写的设置。", "muted"))
    audio = card(settings_layout, "01  /  麦克风与录音键")
    w.device = QComboBox()
    w.device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    w.device.setMinimumContentsLength(12)
    field(audio, "输入设备", w.device)
    row = QHBoxLayout()
    refresh = QPushButton("刷新设备")
    refresh.clicked.connect(lambda: w.refresh_devices(rescan=True))
    w.test = QPushButton("测试麦克风")
    w.test.clicked.connect(w.toggle_test)
    row.addWidget(refresh)
    row.addWidget(w.test)
    # Same input level on both pages; no second audio stream.
    test_meter = QProgressBar()
    test_meter.setAccessibleName("麦克风测试音量")
    test_meter.setRange(0, 100)
    test_meter.setValue(0)
    test_meter.setTextVisible(False)
    w.meter.valueChanged.connect(test_meter.setValue)
    row.addWidget(test_meter, 1)
    audio.addLayout(row)
    audio.addWidget(label("麦克风测试仅在本地进行，不上传音频。", "muted"))
    audio.addWidget(label("全局录音键"))
    row = QHBoxLayout()
    w.trigger = QLineEdit(w.settings.trigger)
    w.trigger.setAccessibleName("全局录音键")
    capture = QPushButton("录入按键…")
    capture.clicked.connect(w.capture_trigger)
    row.addWidget(w.trigger, 1)
    row.addWidget(capture)
    audio.addLayout(row)
    w.activation = QComboBox()
    w.activation.addItem("按住录音，松开结束", "hold")
    w.activation.addItem("按一下开始，再按一下结束", "toggle")
    w.activation.setCurrentIndex(w.activation.findData(w.settings.activation))
    field(audio, "触发方式", w.activation)

    cloud = card(settings_layout, "02  /  识别服务", "使用 Qwen 云端识别，需自备 API Key，服务可能计费。")
    w.region = QComboBox()
    w.region.addItems(list(ENDPOINTS))
    w.region.setCurrentText(w.settings.region)
    field(cloud, "服务区域", w.region)
    w.model = QLineEdit(w.settings.model)
    field(cloud, "识别模型", w.model)
    w.language = QComboBox()
    for title, code in [("中文", "zh"), ("English", "en"), ("日本語", "ja"), ("한국어", "ko")]:
        w.language.addItem(title, code)
    w.language.setCurrentIndex(max(0, w.language.findData(w.settings.language)))
    field(cloud, "识别语言", w.language)
    w.key = QLineEdit()
    w.key.setEchoMode(QLineEdit.EchoMode.Password)
    w.key.setPlaceholderText("留空使用系统凭据库 / DASHSCOPE_API_KEY")
    field(cloud, "API Key", w.key)
    w.remember = QCheckBox("将新 API Key 保存到系统凭据库")
    cloud.addWidget(w.remember)

    output = card(settings_layout, "03  /  文字输出")
    w.paste = QCheckBox("全局录音结束后，自动粘贴到当前输入框")
    w.paste.setChecked(w.settings.auto_paste)
    output.addWidget(w.paste)
    w.shortcut = QComboBox()
    for title, code in [("系统默认（macOS ⌘V / 其他 Ctrl+V）", "auto"),
                        ("Ctrl+V", "ctrl+v"), ("终端 Ctrl+Shift+V", "ctrl+shift+v"), ("⌘V", "cmd+v")]:
        w.shortcut.addItem(title, code)
    w.shortcut.setCurrentIndex(w.shortcut.findData(w.settings.paste_shortcut))
    field(output, "粘贴快捷键", w.shortcut)
    w.limit = QSpinBox()
    w.limit.setRange(5, 600)
    w.limit.setSuffix(" 秒")
    w.limit.setValue(w.settings.max_seconds)
    field(output, "单次录音上限", w.limit)
    output.addWidget(label("自动粘贴会更新系统剪贴板，不会发送消息。文字不由本应用持久保存；窗口关闭到托盘时仍会保留。", "muted"))
    feedback = card(settings_layout, "04  /  录音提示", "提示显示在鼠标所在屏幕，不抢输入焦点。")
    w.indicator_position = QComboBox()
    for value, title in INDICATOR_POSITIONS.items():
        w.indicator_position.addItem(title, value)
    w.indicator_position.setCurrentIndex(w.indicator_position.findData(w.settings.indicator_position))
    field(feedback, "悬浮提示位置", w.indicator_position)
    w.preview_indicator = QPushButton("预览位置（3 秒）")
    w.preview_indicator.clicked.connect(lambda: w.indicator.present(
        "录音提示预览\n不会录音，也不会上传音频", dismiss_ms=3000,
        position=w.indicator_position.currentData()) if not w.recording else None)
    feedback.addWidget(w.preview_indicator)
    feedback.addWidget(label("点击底部「保存并启用」记住位置，下次启动继续使用。", "muted"))
    settings_layout.addStretch()
    w.settings_scroll.setWidget(settings_page)
    w.pages.addWidget(w.settings_scroll)

    footer = QHBoxLayout()
    w.status = label(initial, "muted")
    w.status.setAccessibleName("运行状态")
    w.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    footer.addWidget(w.status, 1)
    w.disable = QPushButton("停用录音键")
    w.disable.clicked.connect(w.disable_trigger)
    footer.addWidget(w.disable)
    w.enable = QPushButton("保存并启用")
    w.enable.setToolTip("保存当前设置并启用全局录音键")
    w.enable.setObjectName("primary")
    w.enable.clicked.connect(w.enable_trigger)
    footer.addWidget(w.enable)
    layout.addLayout(footer)
