# voice-type 旧版本机脚本

这份说明仅供已经使用过旧脚本的用户迁移参考；新用户直接阅读
[README.md](README.md) 和 [DESKTOP.md](DESKTOP.md)，不要安装或启动旧服务。
旧 `voice_type.py`、`config.py`、`run.sh`、`probe_button.py` 可保留在原本机目录，
但由 `.gitignore` 和 `MANIFEST.in` 排除，不随新版发布，也不会被新版自动迁移。

## 迁移到桌面版

1. 如果装过旧服务，先执行 `systemctl --user stop voice-type.service`，避免占用同一麦克风。
2. 启动新版，重新选择设备、录入实际录音键、填写 API Key，然后“保存并启用”。旧脚本配置不会自动导入。
3. 旧脚本可能将鼠标物理侧键 8 映射成逻辑按钮 13。使用新版的“录入按键…”获取当前映射，不要手填别人的编号。
4. 确认新版可用且不再需要旧服务后，可自行执行 `systemctl --user disable voice-type.service` 取消旧自启。

下面保留旧脚本的行为说明。新版不依赖 `natural-hri-p0`、Conda、`xclip` 或 `xdotool`。
新版不会替你启停旧服务、修改鼠标映射或删除旧文件。

按住鼠标侧键说话，松开把实时转写的中文键入到光标所在处。X11 下的系统级语音听写小工具。

## 是什么

- **触发**：按住鼠标侧键录音，松开停止并转写。X11 启动时会把物理 `button8`
  映射为内部 `button13`，避免 Electron/浏览器把侧键解释为导航或聊天快捷键。
- **转写**：复用 `natural-hri-p0` 的阿里云 `qwen3-asr-flash-realtime` 实时 ASR 客户端（通过 sys.path 导入，不复制代码）。
- **注入**：把转写文字写进剪贴板 + 模拟粘贴键（默认 `ctrl+v`），粘完恢复原剪贴板。中文可靠。
- **形态**：systemd user service，后台常驻 + 登录自启。

## 日常使用

仅在你已安装并启动旧服务的前提下：光标点进输入框 → 按住配置的侧键说话 → 松开 → 中文自动粘入。
本文不是旧服务当前运行状态的声明。

⚠️ 终端里的粘贴键是 `ctrl+shift+v`，而默认配的是 `ctrl+v`（适配编辑器/浏览器）。在普通输入框验证，别在终端里测。

## 常用命令

```bash
systemctl --user status voice-type       # 看状态
journalctl --user -u voice-type -f        # 实时日志（转写内容都在这）
systemctl --user restart voice-type       # 改完 config.py 后重启生效
systemctl --user disable --now voice-type # 停掉并关闭自启
systemctl --user enable --now voice-type  # 重新开启
```

**改了 `config.py` 必须 `restart` 才生效。**

## 配置（config.py）

| 项 | 说明 |
|---|---|
| `TRIGGER_BUTTON` | 实际监听的 pynput 按钮名，由 `run.sh` 注入。X11 映射成功时本机为 `button13`；失败或直接运行 Python 时回退 `button8`。 |
| `X11_REMAP_TRIGGER` | 是否启用 X11 侧键隔离。默认 `True`；映射失败会自动回退，不会导致工具失效。 |
| `X11_TRIGGER_DEVICE` | 需要隔离的 xinput 鼠标精确名称，取决于原本机配置。 |
| `MIC_NAME_MATCH` | 麦克风名字子串匹配，取决于原本机设备；同型号设备可能无法区分。 |
| `CAPTURE_RATE` | 麦克风原生采样率，旧代码重采样到 16k 喂 ASR。 |
| `INJECT_METHOD` | `clipboard`（中文可靠，默认）\| `type`（逐字键入，中文常丢字）。 |
| `PASTE_HOTKEY` | 粘贴键。编辑器/浏览器 `ctrl+v`；终端改 `ctrl+shift+v`。 |
| `RESTORE_CLIPBOARD` | 粘贴后恢复原剪贴板内容。 |
| `STRIP_TRAILING_PUNCT` | 去掉 ASR 结尾自动加的句号等标点。 |

## 文件

```
voice_type.py       # 主程序：鼠标监听 + 采集/重采样 + ASR + 注入
config.py           # 配置（复用 natural-hri-p0 的 ASR 客户端与 .env）
run.sh              # 启动包装：定位 X11 环境(DISPLAY/XAUTHORITY)后拉起
probe_button.py     # 探针：探出鼠标键的 pynput 名字
README.md
~/.config/systemd/user/voice-type.service   # 守护 + 自启定义
```

## 依赖

- conda `audio` 环境：`dashscope`、`sounddevice`、`numpy`、`pynput`
- 系统：`xdotool`（模拟粘贴键）、`xclip`（读写剪贴板）
- 密钥：复用 `natural-hri-p0/.env` 的 `NHRI_API_KEY`（ASR 走公网 dashscope endpoint）

## 手动调试

服务跑不起来时，手动前台跑看报错：

```bash
bash run.sh  # 仅在仍保留旧脚本的本机目录运行
```

## 已知点

- **仅 X11**：文字注入依赖 xdotool/xclip。Wayland 需换 wtype/wl-copy（本机是 X11）。
- **中文必须走 clipboard**：`type` 模式实测中文丢字（xdotool 靠临时 keymap 映射，CJK 映不了）。
- **短音易抖**：说太短（"喂""嗯"）ASR 容易糊，正常整句稳。
- **X11 侧键隔离**：服务启动时将本机物理 `button8` 映射到 `button13`，因此 ChatGPT、浏览器等不会再收到默认的侧键导航事件。鼠标重新插拔或图形会话重启后映射会恢复默认；执行 `systemctl --user restart voice-type` 即可重新应用。
