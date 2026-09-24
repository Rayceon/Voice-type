# Voice Type

把说的话，输入到你正在使用的桌面应用。

按住录音键说话，松开后识别并粘贴；也可以选择“按一下开始，再按一下结束”。
适合聊天、写文档、写邮件等输入场景，不会自动按 Enter 或发送消息。

**当前版本：`0.1.0a1`，Linux/X11 优先的开发预览版。**
使用阿里云 Qwen 实时语音识别，需要网络和你自己的 DashScope API Key，可能产生云服务费用。
这不是离线识别工具；Windows、macOS 和 Wayland 尚未完成真机验收。

## 功能

- **自定义录音键**：键盘、组合键或鼠标侧键；默认 F8，支持按住和切换模式。
- **跨应用输入**：识别后向当前输入框发送粘贴快捷键，也可在窗口录音、手动复制。
- **录音浮窗**：显示录音、识别收尾和完成状态，不抢输入焦点；提供六个位置与预览。
- **麦克风选择**：跟随系统默认设备或指定设备，支持本地音量测试和设备刷新。
- **完整转写**：一次录音统一提交，识别文本按结果项累积，不用只保留最后一句。
- **自定义热词**：在识别服务中填写专有名词或短语，作为云端识别上下文，提高相关词的识别机会。
- **独立运行**：不依赖作者的 Conda 环境、个人目录或其他项目。自有代码采用 MIT 许可证。

## 安装

### Linux（Debian / Ubuntu，推荐）

下载或克隆本项目后，进入项目目录运行：

```bash
make install
```

安装脚本仅在缺少系统依赖时通过 `sudo` 安装，Python 环境放在仓库外的用户数据目录
（默认 `~/.local/share/voice-type/venv`），不会在项目内创建 `.venv`。
请用普通用户执行 `make install`，不要使用 `sudo make install`。需要 Python 3.10+ 和 `make`。
安装后自动启动，并添加应用菜单入口与桌面登录自启动。首次使用打开设置窗口；
已有可用配置和已保存的 API Key 时，自动启用录音键并驻留托盘，不会自行录音。
后续可从应用菜单或托盘打开同一窗口。重复安装后，若旧版本仍在运行，请从托盘退出后重新打开。

系统依赖（包括 `libportaudio2`）在 [requirements-apt.txt](scripts/requirements-apt.txt)，
Python 依赖由 [requirements.txt](requirements.txt) 引用 [pyproject.toml](pyproject.toml)。
apt 包不能直接写进 pip 的 requirements 文件。

### 其他平台 / 手动安装

先安装 Python 3.10+；Linux 还需上述系统库。以下命令均在项目目录执行。

Linux / macOS：

```bash
python3 -m venv "$HOME/.local/share/voice-type/venv"
"$HOME/.local/share/voice-type/venv/bin/python" -m pip install -r requirements.txt
"$HOME/.local/share/voice-type/venv/bin/voice-type-app"
```

Windows PowerShell：

```powershell
$voiceEnv = Join-Path $env:LOCALAPPDATA 'VoiceType\venv'
py -3 -m venv $voiceEnv
& "$voiceEnv\Scripts\python.exe" -m pip install -r requirements.txt
& "$voiceEnv\Scripts\voice-type-app.exe"
```

目前没有本项目已公开发布的安装包，也未发布到 PyPI；请勿把同名第三方包当成本项目。
自行构建的预览包自带 Python 和依赖，运行时不需要 `.venv`；须完整解压，不能只复制可执行文件。
详见 [桌面使用与开发指南](docs/usage.md)。

## 第一次使用

1. 打开“设置”，选择麦克风，点“测试麦克风”观察音量；测试只在本地运行，10 秒后自动停止。
2. 点“录入按键…”设置录音键，选择按住或切换模式。建议先用 F8，再尝试鼠标侧键。
3. 填入 DashScope API Key，选择匹配的服务区域。默认模型为 `qwen3-asr-flash-realtime`。
4. 在“录音提示”选择浮窗位置，点击“预览位置（3 秒）”确认，再点底部“保存并启用”。
5. 切换到目标应用，点进输入框，按录音键说话。按住模式松开结束；切换模式再按一次结束。

浮窗在每次显示时选择鼠标所在屏幕，可选顶部/底部的左、中、右六个位置。
Linux/X11 上浮窗独立于主窗口，主窗口隐藏或最小化后仍可显示。
这是位置预设，不是拖动定位；其他桌面的置顶效果仍需验证。

首次配置后点击“保存并启用”；之后启动时自动恢复已保存的配置。若 API Key 仅保存在本次进程中，
下次启动仍需重新填写。关闭窗口只隐藏到托盘，录音键继续可用；托盘菜单“退出”才结束后台进程。
没有系统托盘时，关闭窗口改为最小化，可用窗口内的“退出”按钮结束进程。
通过 `make install` 安装后，每次登录桌面自动启动；从托盘退出后不会在本次会话中自动重启。

识别结果会替换系统剪贴板，**不恢复旧剪贴板**。默认粘贴键在 macOS 为 ⌘V，其他系统为 Ctrl+V；
终端通常需要在设置中改为 Ctrl+Shift+V。窗口录音不自动向其他应用粘贴。

## 平台与验证范围

| 平台 | 状态与边界 |
| --- | --- |
| Linux X11 | 当前主要验证平台；全局键、跨进程中文粘贴有自动化测试，GNOME/X11 跨应用浮窗已做桌面验证 |
| Windows / macOS | 已有后端和构建 CI 配置，尚未完成真实系统验收；macOS 需麦克风、辅助功能和输入监控权限 |
| Linux Wayland | 依赖 GlobalShortcuts portal 和系统授权；不支持鼠标录音键，目前需手动粘贴，待真机验收 |

不承诺绕过系统保留键、安全输入框、管理员窗口或所有独占全屏应用的限制。
本机曾做过真实 ASR 联通测试；自动化测试使用模拟音频/服务，不能代替不同设备和网络的验收。
完整排障与测试方法见 [使用指南](docs/usage.md)。

## 隐私与许可证

开始录音后，音频会上传到所选区域的阿里云 ASR 服务。麦克风测试不上传音频。
自定义热词明文保存在本地设置中，并随识别发送到云端；请勿填写密钥或敏感信息。
新版不将录音或转写保存为文件；文字仍可能留在窗口、系统剪贴板及其历史记录中。
API Key 不写入设置 JSON，可选择系统凭据库保存，也可仅在本次运行使用。
凭据保存、云端处理与问题反馈注意事项见 [SECURITY.md](SECURITY.md)。

自有代码：[MIT](LICENSE)。依赖许可及二进制分发前的检查：[第三方许可](docs/third-party.md)。
当前二进制尚未完成完整许可材料核验、签名或公证，不能把源码开源等同于二进制正式发布。

开发、测试、构建见 [使用指南](docs/usage.md)；从本机旧脚本迁移见 [迁移参考](docs/legacy.md)。
旧脚本不是新版安装入口，不随新版源码分发包或桌面包发布。
