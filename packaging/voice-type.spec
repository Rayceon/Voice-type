# Build on each target OS: python scripts/build.py
import os
import sys
import sysconfig
from pathlib import Path
from PyInstaller.depend.bindepend import get_imports
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).resolve().parent
datas = [(str(root / name), ".") for name in ("LICENSE", "README.md", "SECURITY.md")]
datas += [(str(root / name), name) for name in ("docs", "licenses")]
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
    notice_dirs = [Path("/usr/share/doc")]
    if os.environ.get("VOICE_TYPE_NATIVE_ROOT"):
        notice_dirs.append(Path(os.environ["VOICE_TYPE_NATIVE_ROOT"]) / "usr/share/doc")
    for base in notice_dirs:
        for name in ("libportaudio2", "libxcb-cursor0"):
            notice = base / name / "copyright"
            if notice.is_file():
                datas.append((str(notice), "licenses/" + name))
python_notice = next((base / name
                     for base in (Path(sysconfig.get_path("stdlib")), Path(sys.base_prefix))
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

tls_libraries = {}
if sys.platform.startswith("linux"):
    import _ssl
    # Resolve against the actual interpreter, not Qt's/system OpenSSL. They may
    # share the same SONAME but expose different symbol versions (e.g. Conda).
    for name, path in get_imports(_ssl.__file__):
        if name.startswith(("libssl.so", "libcrypto.so")):
            if path is None:
                raise RuntimeError(f"Cannot resolve Python TLS dependency: {name}")
            tls_libraries[name] = path

a = Analysis([str(root / "packaging/desktop_entry.py")], pathex=[str(root / "src")],
             datas=datas, hiddenimports=hiddenimports,
             binaries=[(path, ".") for path in tls_libraries.values()],
             runtime_hooks=[str(root / "packaging/pyi_rth_portaudio.py")])
# Dependency traversal can encounter another copy under the same destination.
# Pin the final TOC as well, before COLLECT copies any libraries.
a.binaries = [(name, tls_libraries[name], "BINARY") if name in tls_libraries
              else (name, path, kind) for name, path, kind in a.binaries]
if sys.platform.startswith("linux") and not any(item[0] == "libportaudio.so.2" for item in a.binaries):
    raise RuntimeError("PortAudio was not collected. Install scripts/requirements-apt.txt "
                       "system dependencies before building the Linux bundle.")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoiceType", console=False)
bundle = COLLECT(exe, a.binaries, a.datas, name="VoiceType")
if sys.platform == "darwin":
    app = BUNDLE(bundle, name="VoiceType.app", bundle_identifier="org.voicetype.desktop",
                 info_plist={"NSMicrophoneUsageDescription": "Record speech when you activate dictation.",
                             "NSHighResolutionCapable": True})
