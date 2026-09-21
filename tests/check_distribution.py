"""Audit actual release archives; no extraction, credentials or network required.

Run after `python -m build`: python tests/check_distribution.py dist
"""
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
from urllib.parse import unquote, urlsplit
import zipfile


def audit(files: dict[str, bytes], *, source: bool) -> None:
    """Fail closed on missing release files or obvious local/private artifacts."""
    forbidden_dirs = {".git", ".venv", "build", "dist", "__pycache__", ".pytest_cache", ".codebase-memory"}
    legacy = {"config.py", "voice_type.py", "run.sh", "probe_button.py"}
    for name, data in files.items():
        path = PurePosixPath(name)
        assert not path.is_absolute() and ".." not in path.parts, f"Unsafe path: {name}"
        assert not forbidden_dirs.intersection(path.parts), f"Local artifact: {name}"
        assert name not in legacy, f"Legacy script: {name}"
        assert not (path.name.startswith(".env") or path.name == "settings.json"
                    or path.suffix in {".pyc", ".pem", ".key", ".wav", ".pcm", ".log"}
                    or path.name.endswith("_api_key.txt")), f"Private/generated file: {name}"
        # Report only a filename, never the secret-like match itself.
        assert not re.search(rb"sk-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----", data), f"Possible secret: {name}"
        assert not re.search(rb"/home/[A-Za-z0-9_.-]+/", data), f"Author-specific path: {name}"
    if source:
        required = {"README.md", "DESKTOP.md", "LEGACY.md", "SECURITY.md", "LICENSE", "THIRD_PARTY.md",
                    "pyproject.toml", "requirements.txt", "requirements-apt.txt", "install-linux.sh",
                    "MANIFEST.in", "voice-type.spec", "desktop_entry.py", "pyi_rth_portaudio.py",
                    "src/voicetype/app.py", "src/voicetype/ui.py", "tests/check_distribution.py",
                    ".github/workflows/desktop.yml", "licenses/README.md"}
        assert not (required - files.keys()), f"Missing source files: {sorted(required - files.keys())}"
        for name, data in files.items():
            if not name.endswith(".md"):
                continue
            for target in re.findall(r"\]\(([^\s)]+)\)", data.decode("utf-8")):
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path:
                    continue
                resolved = (PurePosixPath(name).parent / unquote(url.path)).as_posix()
                assert resolved in files, f"Broken document link: {name} -> {target}"
    else:
        assert "voicetype/app.py" in files, "Wheel is missing the application"
        metadata = [data for name, data in files.items() if name.endswith(".dist-info/METADATA")]
        assert len(metadata) == 1 and b"# Voice Type" in metadata[0], "Wheel is missing README metadata"
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in files), "Wheel is missing LICENSE"


def main(directory: str) -> None:
    root = Path(directory)
    sources, wheels = list(root.glob("voice_type_desktop-*.tar.gz")), list(root.glob("voice_type_desktop-*.whl"))
    if len(sources) != 1 or len(wheels) != 1:
        raise SystemExit("Expected exactly one Voice Type sdist and wheel in the build directory")
    with tarfile.open(sources[0]) as archive:
        members = archive.getmembers()
        assert all(m.isdir() or m.isfile() for m in members), "Unexpected archive entry type"
        roots = {PurePosixPath(m.name).parts[0] for m in members}
        assert len(roots) == 1, "Expected one source archive root"
        files = {PurePosixPath(m.name).relative_to(next(iter(roots))).as_posix(): archive.extractfile(m).read()
                 for m in members if m.isfile()}
    audit(files, source=True)
    with zipfile.ZipFile(wheels[0]) as archive:
        audit({name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}, source=False)
    print("Release archives OK: required files, document links, local artifacts and basic secret patterns")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dist")
