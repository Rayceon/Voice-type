# Build on each target OS: pyinstaller voice-type.spec
import sys
import sysconfig
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = [("LICENSE", "."), ("README.md", "."), ("DESKTOP.md", "."),
         ("LEGACY.md", "."), ("SECURITY.md", "."), ("THIRD_PARTY.md", "."),
         ("licenses", "licenses")]
for name in ("certifi", "keyring"):
    datas += collect_data_files(name)
# Preserve the actual runtime distribution license texts/metadata, not dev tools.
for name in ("PySide6-Essentials", "sounddevice", "numpy", "soxr", "websocket-client",
             "certifi", "pynput", "platformdirs", "keyring"):
    datas += copy_metadata(name, recursive=True)
# The executable includes PyInstaller's bootloader (GPL with a distribution exception).
datas += copy_metadata("pyinstaller")
if sys.platform.startswith("linux"):
    datas += copy_metadata("dbus-next")
    for base in (Path("/usr/share/doc"), Path(".venv/native/usr/share/doc")):
        for name in ("libportaudio2", "libxcb-cursor0"):
            notice = base / name / "copyright"
            if notice.is_file():
                datas.append((str(notice), "licenses/" + name))
python_notice = next((base / name
                     for base in (Path(sys.base_prefix), Path(sysconfig.get_path("stdlib")))
                     for name in ("LICENSE.txt", "LICENSE_PYTHON.txt")
                     if (base / name).is_file()), None)
if python_notice is None:
    raise RuntimeError("Python license not found in interpreter prefix or stdlib; "
                       "use a Python installation with its original license materials.")
datas.append((str(python_notice), "licenses/python"))
hiddenimports = collect_submodules("keyring.backends")
if sys.platform.startswith("linux"):
    hiddenimports += ["pynput.keyboard._xorg", "pynput.mouse._xorg", "Xlib.display", "Xlib.ext.xtest"]
elif sys.platform == "win32":
    hiddenimports += ["pynput.keyboard._win32", "pynput.mouse._win32"]
else:
    hiddenimports += ["pynput.keyboard._darwin", "pynput.mouse._darwin", "Quartz"]

a = Analysis(["desktop_entry.py"], pathex=["src"], datas=datas, hiddenimports=hiddenimports,
             runtime_hooks=["pyi_rth_portaudio.py"])
if sys.platform.startswith("linux") and not any(item[0] == "libportaudio.so.2" for item in a.binaries):
    raise RuntimeError("PortAudio was not collected. Install requirements-apt.txt "
                       "system dependencies before building the Linux bundle.")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoiceType", console=False)
bundle = COLLECT(exe, a.binaries, a.datas, name="VoiceType")
if sys.platform == "darwin":
    app = BUNDLE(bundle, name="VoiceType.app", bundle_identifier="org.voicetype.desktop",
                 info_plist={"NSMicrophoneUsageDescription": "Record speech when you activate dictation.",
                             "NSHighResolutionCapable": True})
