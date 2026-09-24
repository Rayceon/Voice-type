# Voice Type 使用与开发指南（开发预览版）

将语音输入到桌面应用。独立 Python 包；不需要原作者的目录、Conda 环境或另一个代码仓。
当前使用 Qwen Realtime ASR，需要自己的 DashScope API Key 和网络连接。

## 从源码安装

Debian/Ubuntu 推荐在项目目录运行 `make install`（需要 `make` 和 Python 3.10+）。
安装器按 `scripts/requirements-apt.txt` 检查系统依赖，仅缺失时调用 sudo 安装，
然后在用户数据目录建立或复用虚拟环境、安装 Python 依赖并执行音频自检。
请使用普通用户，不要执行 `sudo make install`；管理员密码只在本机 sudo 提示中输入。
安装会创建应用菜单入口、配置桌面登录自启动，并在当前图形会话启动后台应用。
首次使用或配置不可用时显示窗口；已有可用配置时恢复录音键并驻留托盘，不会自行录音或上传。
没有图形会话时仅完成安装，等下次登录桌面再启动。

需要 Python 3.10+。在项目目录执行：

```sh
# Linux/macOS
python3 -m venv "$HOME/.local/share/voice-type/venv"
. "$HOME/.local/share/voice-type/venv/bin/activate"
python -m pip install -r requirements.txt
voice-type-app
```

Windows PowerShell：

```powershell
$voiceEnv = Join-Path $env:LOCALAPPDATA 'VoiceType\venv'
py -m venv $voiceEnv
& "$voiceEnv\Scripts\python.exe" -m pip install -r requirements.txt
& "$voiceEnv\Scripts\voice-type-app.exe"
```

虚拟环境用于隔离源码运行的依赖，不必放在仓库里。完整桌面包自带运行时，无需虚拟环境。

`requirements.txt` 引用项目自身，Python 依赖统一维护在 `pyproject.toml`，避免两份清单漂移。
Linux 源码运行需要 PortAudio 和 Qt 系统库；Debian/Ubuntu 的完整安装清单见
`scripts/requirements-apt.txt`，它供 apt 使用，不能传给 pip。其他发行版需用自己的包管理器安装对应库。
Windows/macOS 的 sounddevice wheel 通常自带 PortAudio。

## 首次运行

1. 选择“跟随系统默认麦克风”，或指定一个输入设备，点击“测试麦克风”观察音量。
2. 录入键盘键、带修饰键的组合键或鼠标按钮；选择按住说话或按一下切换。
3. 填写 API Key，选择与 Key 匹配的服务区域。可选择系统凭据库保存；不可用时只保存在内存。
4. 在“04 / 录音提示”选择六种浮窗位置之一，用“预览位置（3 秒）”检查，再点“保存并启用”。
5. 把光标放到目标应用输入框，再用录音键说话；全局录音会显示独立浮窗，反馈录音和识别状态。
6. 窗口录音按钮也可用，结果留在窗口供复制。关闭窗口保持后台运行，托盘菜单“退出”才结束进程。

第一次点击“保存并启用”后，后续启动会自动恢复已保存的设置和全局录音键。
仅保存在进程中的 API Key 无法跨重启使用；需要自动恢复时选择系统凭据库保存，或配置 `DASHSCOPE_API_KEY`。
关闭窗口只隐藏到托盘；托盘菜单“退出”会停止监听、释放麦克风并结束进程。
没有托盘时，关闭窗口改为最小化，窗口内会显示“退出”按钮。
重复点击应用菜单会唤回已有窗口，不会创建第二个录音进程。
麦克风测试 10 秒后自动停止；切换页面、切换设备或隐藏窗口也会停止测试，释放设备。
隐藏窗口会结束窗口按钮发起的录音，不会中断由全局录音键发起的录音。

设置页的选择框和时长输入框不会通过滚轮改变值；滚轮继续滚动页面。
点击展开选项后选择，或使用键盘方向键修改。

浮窗每次出现或更新时定位到鼠标所在屏幕，位置使用该屏幕可用区域，默认底部中央。
浮窗采用深色圆角卡片，显示录音时长及随音量变化的声纹；识别中、完成与错误使用不同的图标和状态提示。
声纹只在全局录音时接收音量数据，设置中的预览使用模拟动画。隐藏浮窗后停止动画刷新。
预览不录音、不上传；实际录音使用已保存的位置，不是尚未保存的下拉选项。
当前 GNOME/X11 已验证前台为其他应用、主窗口隐藏/最小化和普通全屏窗口时的显示与焦点保持；
其他窗口管理器、Wayland、Windows/macOS 和独占全屏游戏的效果不能由此推定。

设备每次录音时重新按名称和 host API 解析；同名设备额外使用保存的当前索引消歧，唯一设备即使索引因热插拔变化也能自动重新绑定。程序自动选择设备默认值或 48/44.1/32/16/8 kHz，并转换成 16 kHz 单声道。
找不到匹配的设备时报告错误，不自动退回系统默认麦克风。点击“刷新”可发现重新连接的设备；旧设置或索引变化后的唯一同名、同 host API 设备也会在列表中重新选中。
名称和 PortAudio 索引不是物理设备的永久身份：多支同型号麦克风热插拔后可能发生索引复用，不能保证仍是原来那支。存在无法消歧的同名设备时列表会提示重新选择；重新连接后请确认选择并测试音量。
刷新会停止本地麦克风测试并重建音频设备列表；录音/识别进行中不能刷新。枚举失败时保留原选择。
设置位于系统用户配置目录（Linux 通常 `~/.config/VoiceType/settings.json`），不含 API Key。

## 后台启动与安装位置

`make install` 创建以下文件（遵循 `XDG_DATA_HOME`、`XDG_CONFIG_HOME`、`XDG_STATE_HOME`）：

- `~/.local/share/voice-type/venv/`：应用与 Python 依赖。
- `~/.local/share/applications/voice-type.desktop`：应用菜单入口。
- `~/.config/autostart/voice-type.desktop`：桌面登录自启动，使用 `--background`。
- `~/.local/state/voice-type/app.log`：由安装器首次后台启动时写入的诊断日志。

应用在当前用户的图形会话内运行。从托盘退出后不会立即重启，下次登录桌面会再次启动。
如需取消登录自启动，删除 `~/.config/autostart/voice-type.desktop`；自定义 XDG 路径时使用对应位置。
重复安装会更新上述启动入口；若旧版本正在运行，先从托盘退出，再从应用菜单打开新版本。
手动安装或自行构建不会自动创建登录启动项，可运行 `voice-type-app --background` 使用后台启动模式。
缺少配置、凭据或托盘支持时，后台启动会显示窗口，方便配置或退出。

## 自定义热词

在“设置 → 02 / 识别服务 → 自定义热词”中，建议每行输入一个专有名词或短语，例如：

```text
星尘智能
Voice Type
Qwen
```

点击“保存并启用”后，全局录音从下一次开始使用这些热词；窗口录音直接使用当前输入框内容。
录音途中修改不会影响已开始的会话。清空后保存即可停用，旧版设置默认不使用热词。
应用最多接受 2000 个字符（包括换行），超限会提示精简，不会静默截断。

使用 Qwen Realtime 的 `input_audio_transcription.corpus.text` 上下文偏置能力，
不是本地文本替换，也不保证每次都能命中。建议只填少量容易识别错误的词，避免大量无关内容。
官方接口上限为 10000 tokens，本应用采用更小的字符上限；自定义模型需支持该字段。
接口依据：[Qwen-ASR-Realtime 客户端事件](https://www.alibabacloud.com/help/en/model-studio/qwen-asr-realtime-client-events)。

热词明文保存在本地设置，并在每次 ASR 会话建立时发送到所选区域的云服务；
`--check-asr` 联网自检也会发送已保存的热词。保存设置和测试麦克风本身不会上传热词。
请勿填写密钥或敏感信息，提交设置文件或截图前也应检查热词内容。

## 当前平台边界

- Linux X11：原生抓取用户选择的录音键，触发事件不会进入目标应用，退出后自动释放。按住期间 X11 会占用相应键盘/鼠标，松开恢复；适用于按住说话，不用于同时按着录音键操作同一输入设备。
- Windows：使用 pynput 原生后端；普通权限程序不能保证输入到管理员权限窗口。
- macOS：需要麦克风、辅助功能和输入监控权限。
- Wayland：使用系统 GlobalShortcuts portal，需在系统弹窗确认键盘快捷键，以系统实际绑定为准。桌面不提供该 portal 或拒绝授权时可使用窗口录音。此接口不支持鼠标按钮；当前输出使用手动粘贴。协议已用隔离 D-Bus 服务测试，尚需真实 Wayland 桌面验收。
- Windows/macOS 已实现选择性拦截：吞掉触发键，放行其他输入及修饰键松开事件；还需对应系统实测。
- 组合键按“先修饰键、再普通键”触发；录入支持字母、数字、F1–F24、常见标点、媒体键和鼠标键，并会按平台能力校验。不要将常用输入键设为录音键，除非确实希望它被占用；建议 F8 或鼠标侧键。
- 系统保留键、安全输入窗口和权限限制不能绕过。Windows 标准鼠标后端支持左右/中键和 x1/x2；Wayland portal 不支持鼠标键，不能承诺所有系统上的任意键均可用。
- 终端可在设置中选择 `Ctrl+Shift+V`。自动粘贴不会按 Enter，也不会替用户发送消息。
- 自动粘贴会等待录音键/修饰键松开。X11 粘贴期间短暂释放并恢复录音键抓取，防止 Ctrl 等自定义键被程序自身再次触发。剪贴板已被其他操作修改时取消自动粘贴。
- 识别结果会更新系统剪贴板；当前版本不恢复旧剪贴板，避免目标应用异步读取时贴入旧内容。

Windows/macOS 尚需真实系统验收，不能以 Linux 测试结果代替。
旧 `voice_type.py`/`config.py`/`run.sh` 是本机兼容入口，不随新版发布。
运行新版全局监听前应停掉旧服务或其他语音输入工具，避免两个实例同时录音。迁移见 [旧版迁移](legacy.md)。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 提示找不到 PortAudio / 无法枚举麦克风 | Linux 源码安装先运行 `bash scripts/install-linux.sh`；用 `voice-type-app --check-audio` 检查，完整二进制包使用 `./VoiceType/VoiceType --check-audio` |
| 麦克风列表正常，但开始录音报设备被占用 | 停止其他录音应用/旧后台服务；点“停止测试”，再尝试窗口录音。枚举成功不代表能打开录音流 |
| 按键没有反应，或侧键让浏览器后退 | 先点“保存并启用”并查看底部状态；重新录入实际按键，检查冲突和平台权限。旧脚本可能改过 X11 鼠标映射，不要照抄别人的按钮编号 |
| 切到其他应用没有浮窗 | 设置页先预览位置，确认没有看错屏幕；再用全局键录音（窗口按钮不显示这类浮窗）。确认运行的是最新构建，不是旧后台实例 |
| 识别成功但没有粘贴 | 点击可编辑输入框，检查“自动粘贴”及粘贴快捷键，松开修饰键；Wayland 需手动粘贴，管理员/安全窗口可能拒绝模拟输入 |
| API Key / ASR 错误 | 检查 Key 对应的区域、模型权限、余额和网络；不要在公开 Issue 中贴 Key 或未经检查的请求日志 |
| 重启后又要填 Key | 没勾选记住或系统凭据库不可用时只在进程内保留；可用系统凭据库或 `DASHSCOPE_API_KEY` 环境变量 |

关闭“自动粘贴”后，结果仍在窗口中，但不会自动更新剪贴板，请点“复制”。
自动粘贴只发送快捷键，无法保证目标应用接受了文字；不要在终端命令行或敏感输入框盲测。
发布问题时说明版本、操作系统、X11/Wayland、触发键和复现步骤；日志及截图请先脱敏。

## 隐私与开发

测试麦克风只在本地处理。只有用户开始录音时才建立 ASR 连接并上传音频。
程序不持久化录音或转写，不输出 API Key。云服务的数据政策由所选服务提供商负责。
剪贴板、凭据库和卸载后的数据注意事项见 [SECURITY.md](../SECURITY.md)。

开发可单独使用仓库外环境。在项目目录执行以下命令；测试直接加载 `src/`，无需 editable 安装：

```sh
python3 -m venv "$HOME/.local/share/voice-type-dev/venv"
. "$HOME/.local/share/voice-type-dev/venv/bin/activate"
python -m pip install ".[dev]"
python -B -m pytest -p no:cacheprovider -q
python scripts/build.py
```

构建脚本在用户缓存目录暂存源码，源码包、wheel、桌面包默认输出至用户缓存目录下
`VoiceType/dist`（Linux 通常是 `~/.cache/VoiceType/dist`）；可用 `--output <目录>` 指定。
编译缓存同样在仓库外。直接使用 pip 安装本地项目仍可能生成 `src/*.egg-info` 等元数据，
这些不是源码，不应提交。源码调试可用 `PYTHONPATH=src python -B -m voicetype.app`。

普通测试不会连接真实 ASR，也不需要 API Key。未提供隔离 X11 显示器时，X11 集成测试会跳过。
Linux 可安装 `xvfb` 后运行以下命令；它仅向临时 X11 服务注入输入，不操作当前桌面：

```bash
xvfb-run -a python scripts/check_x11.py
xvfb-run -a -s '-screen 0 1280x1024x24 -noreset' \
  sh -c 'VOICE_TYPE_TEST_DISPLAY="$DISPLAY" python -m pytest -q'
```

先安装 `scripts/requirements-apt.txt` 及测试工具 `xvfb`、`xauth`。
预检通过 `ldd` 报告具体缺失的共享库，再实际加载 Qt xcb 插件；失败时输出插件加载日志。
Qt 的 `xcb-cursor0` 提示也可能由其他 XCB 库缺失引发，不要只重复安装 cursor 包。

裸 Xvfb/Xephyr 没有窗口管理器，浮窗层叠测试会跳过；其他全局按键和跨进程粘贴测试仍会运行。
不要把 `VOICE_TYPE_TEST_DISPLAY` 设置成日常桌面。真实麦克风、云端服务和设备热插拔需要另外人工验收。
三平台 CI 配置只表示有检查流程，不表示已经在对应系统验证通过。

### 仓库布局

| 路径 | 用途 |
| --- | --- |
| `src/voicetype/` | 新版 UI、设置、录音、ASR 和平台输入后端 |
| `tests/` | 单元、协议、GUI、打包及隔离 X11 测试 |
| `.github/workflows/desktop.yml` | 三平台检查和预览包构建，不会自动发布 Release |
| `pyproject.toml` / `requirements.txt` | 包元数据与 Python 依赖入口 |
| `packaging/` | PyInstaller 配置、桌面入口与 PortAudio 加载 hook |
| `scripts/` | Linux 安装脚本、系统依赖清单及构建入口 |
| `docs/` | 使用、迁移与第三方分发说明 |
| `licenses/` | 第三方许可材料 |

旧本机脚本和历史构建应备份到仓库外；不要把整个工作目录直接压缩发布。
源码发布用构建脚本产生的 sdist/wheel；桌面包则只归档本次构建生成的完整应用目录。
自有代码采用 [MIT](../LICENSE)。不要在发布准备时把开发预览号改成稳定版本号来代替验收。

## 构建桌面预览包

在目标系统安装开发依赖后执行 `python scripts/build.py`；在输出目录中，Linux/Windows 运行
`VoiceType/VoiceType`（Windows 后缀 `.exe`），macOS 打开 `VoiceType.app`。
必须保留完整目录，不能只复制可执行文件。无需额外安装 Python。
传入 `--smoke-test` 会打开界面后自动退出，不录音、不联网、不注册全局按键。
传入 `--check-tls` 离线检查包内 OpenSSL 和 CA 证书，不需要 Key；构建脚本和 CI 必须通过此检查。
传入 `--check-asr` 使用已保存的 Key（或 `DASHSCOPE_API_KEY`）及已保存的区域/模型完成真实服务握手，
不打开麦克风、不发送音频、不输出 Key。仅在希望联网验证时手动运行，不在 CI 中执行。
传入 `--check-audio` 会验证 PortAudio 加载并列出输入设备，不打开录音流、不联网；
音频组件加载失败时返回非零退出码。仅窗口启动通过不代表音频组件可用。
Linux 预览包自带 PortAudio 并按包内绝对路径加载，不需要为它额外运行 apt 或安装编译工具。
这不表示它适用于所有 Linux：仍需兼容的 glibc、图形会话和音频服务，应在目标发行版上验证。
CI 为三个系统分别构建并运行此启动检查；是否通过以对应提交的 Actions 结果为准，不代替真机验收。
Linux 以 `*-preview.tar.gz`、Windows/macOS 以 `*-preview.zip` 保存完整应用；不要直接下载拆散的 Unix 可执行文件，归档用于保留执行权限和框架符号链接。
依赖许可和正式分发前的检查见 [第三方分发说明](third-party.md)。

公开源码前应检查包内文档链接、许可、依赖和敏感信息，并从干净环境安装 wheel 验证入口。
公开二进制前还需核验对应平台功能、依赖许可/source 材料及签名/公证要求；不要上传过期预览包。
