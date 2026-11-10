"""Per-user configuration; never stored in the source checkout."""

import json
import os
import threading
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "PhonePlayback"
CONFIG_FILE = CONFIG_DIR / "settings.json"
_save_lock = threading.Lock()


def load():
    try:
        value = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save(value):
    with _save_lock:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        temporary = CONFIG_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        temporary.replace(CONFIG_FILE)
