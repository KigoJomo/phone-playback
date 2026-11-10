"""Opt-in packaged-runtime smoke check. No input injection or player changes."""

import json
import sys
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from . import __version__
from .taskbar import Taskbar
from .placement import free_slot


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    taskbar = Taskbar()

    def finish():
        layouts = taskbar.layouts(QApplication.screens())
        report = {
            "version": __version__,
            "frozen": bool(getattr(sys, "frozen", False)),
            "tray_available": QSystemTrayIcon.isSystemTrayAvailable(),
            "taskbar_scan_ok": any(x["known"] for x in layouts),
            "monitor_count": len(QApplication.screens()),
            "taskbar_free_slot": False,
        }
        for layout in layouts:
            bar = layout["bar"]
            intervals = [(r.left(), r.right() + 1) for r in layout["occupied"] if r.intersects(bar)]
            report["taskbar_free_slot"] |= (
                free_slot(bar.left(), bar.right() + 1, intervals, 260) is not None
            )
        try:
            from .bus import call

            call(
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "ListNames",
                destination="org.freedesktop.DBus",
            )
            report["kdeconnect_bus_available"] = True
        except Exception as error:
            report["kdeconnect_bus_available"] = False
            report["bus_error"] = type(error).__name__
        if "--self-test-report" in sys.argv:
            path = Path(sys.argv[sys.argv.index("--self-test-report") + 1])
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        taskbar.stop.set()
        app.exit(0 if report["tray_available"] and report["taskbar_scan_ok"] else 1)

    QTimer.singleShot(3000, finish)
    raise SystemExit(app.exec())
