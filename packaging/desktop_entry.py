"""Standalone bundler entry point; source users run python -m voicetype.app."""
from voicetype.app import main

if __name__ == "__main__":
    raise SystemExit(main())
