"""Resolve bundled PortAudio without Linux ldconfig/compiler development files."""
def _pyi_rthook():
    import ctypes.util
    from pathlib import Path
    import sys

    if not sys.platform.startswith("linux") or not hasattr(sys, "_MEIPASS"):
        return
    library = Path(sys._MEIPASS) / "libportaudio.so.2"
    if not library.is_file():
        return
    original = ctypes.util.find_library

    def find_library(name):
        return str(library) if name == "portaudio" else original(name)

    ctypes.util.find_library = find_library


_pyi_rthook()
del _pyi_rthook
