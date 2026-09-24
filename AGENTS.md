# Repository Guidelines

## Project Structure & Module Organization

Voice Type uses Python 3.10+, PySide6, and Qwen Realtime ASR, primarily on Linux/X11.

- `src/voicetype/`: `app.py` coordinates application behavior, `ui.py` presents widgets, `engine.py` processes audio, and `asr.py` handles recognition sessions.
- `settings.py`, `devices.py`, and the trigger modules manage configuration, microphones, and platform input backends.
- `tests/`: unit, protocol, GUI, packaging, and isolated X11 tests.
- `scripts/` and `packaging/`: installation, build helpers, PyInstaller configuration, and runtime hooks.
- `docs/` and `licenses/`: usage, migration, and redistribution guidance. UI styling lives in Python.

## Build, Test, and Development Commands

Run commands from the repository root with an activated Python environment outside the checkout. Linux system dependencies are listed in `scripts/requirements-apt.txt`.

```bash
python -m pip install ".[dev]"          # Install application and development tools
voice-type-app                        # Launch the installed desktop application
python -B -m pytest -p no:cacheprovider -q  # Run tests against src/
python scripts/build.py               # Build archives and desktop bundle in the user cache
```

The build helper audits distributions and checks bundled TLS. Use `--output PATH` for another output directory. See `docs/usage.md` for setup and `.github/workflows/desktop.yml` for CI checks.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Follow nearby type annotations and Chinese user-facing messages. Keep presentation in `ui.py` and network work outside audio callbacks. Maintain Python dependencies in `pyproject.toml`. No formatter or linter is currently configured.

## Testing Guidelines

Use pytest files named `tests/test_*.py` and functions named `test_*`. Add regression tests for changed behavior, with simulated audio and services. Ordinary tests require no API key. No numeric coverage threshold is configured.

For X11 changes, install `xvfb` and `xauth`, then run:

```bash
xvfb-run -a -s '-screen 0 1280x1024x24 -noreset' \
  sh -c 'VOICE_TYPE_TEST_DISPLAY="$DISPLAY" python -m pytest tests/test_x11.py -q'
```

Use only an isolated display for input injection. Report platform-specific skips and distinguish automated checks from real desktop verification.

## Commit & Pull Request Guidelines

Follow existing concise commit subjects: `feat: add ASR hotwords` or `fix: correct ASR shutdown ordering`. Keep changes focused. Include the problem, behavior changes, validation results, and relevant issues in PR descriptions. Include screenshots for UI changes and identify tested platforms.

## Security & Configuration

Keep API keys in the system keyring or `DASHSCOPE_API_KEY`, outside settings JSON. Exclude credentials, recordings, transcripts, and private hotwords from commits and screenshots. Read `SECURITY.md` before privacy-related changes and `docs/third-party.md` before binary redistribution.
