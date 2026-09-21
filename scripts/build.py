"""Build in the user cache, leaving environments and binary output outside the repo."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from platformdirs import user_cache_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=user_cache_path("VoiceType", appauthor=False) / "dist")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    work = user_cache_path("VoiceType", appauthor=False) / "build"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    work.mkdir(parents=True, exist_ok=True)
    # setuptools writes egg-info/build beside its input. Stage only release sources
    # so neither these files nor local credentials enter the working checkout.
    with tempfile.TemporaryDirectory(prefix="source-", dir=work) as temporary:
        staged = Path(temporary)
        for name in ("LICENSE", "README.md", "SECURITY.md", "pyproject.toml", "MANIFEST.in",
                     ".gitignore", ".gitattributes", "requirements.txt"):
            shutil.copy2(root / name, staged / name)
        for name in ("src", "docs", "licenses", "scripts", "packaging", "tests", ".github"):
            shutil.copytree(root / name, staged / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
        for command in (
            ["build", "--outdir", str(output)],
            ["PyInstaller", "--noconfirm", "--distpath", str(output), "--workpath", str(work),
             str(staged / "packaging/voice-type.spec")],
        ):
            subprocess.run([sys.executable, "-m", *command], cwd=staged, env=env, check=True)
    subprocess.run([sys.executable, str(root / "tests/check_distribution.py"), str(output)],
                   cwd=root, env=env, check=True)
    executable = (output / "VoiceType.app/Contents/MacOS/VoiceType" if sys.platform == "darwin"
                  else output / "VoiceType" / ("VoiceType.exe" if sys.platform == "win32" else "VoiceType"))
    # Do not let the build environment hide incompatible bundled shared libs.
    runtime_env = {key: value for key, value in env.items()
                   if key not in {"LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "PYTHONPATH"}}
    subprocess.run([str(executable), "--check-tls"], cwd=root, env=runtime_env, check=True)
    print(f"Build output: {output}")


if __name__ == "__main__":
    main()
