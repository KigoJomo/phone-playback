"""Windowless entry with a local startup error report if imports fail."""

import json
import os
from pathlib import Path
import sys
import traceback

try:
    from phone_playback.ui import main

    main()
except Exception:
    detail = traceback.format_exc()
    directory = Path(os.environ["LOCALAPPDATA"]) / "PhonePlayback"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "startup-error.log").write_text(detail, encoding="utf-8")
    if "--self-test-report" in sys.argv:
        report = Path(sys.argv[sys.argv.index("--self-test-report") + 1])
        report.write_text(json.dumps({"startup_error": detail}), encoding="utf-8")
    else:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Phone Playback could not start. Details were saved in:\n"
            + str(directory / "startup-error.log"),
            "Phone Playback",
            0x10,
        )
    raise SystemExit(1)
