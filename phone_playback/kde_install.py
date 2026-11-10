"""Locate the existing KDE Connect installation without bundling its binaries."""

import os
import shutil
import subprocess
from pathlib import Path


def find_bin():
    override = os.environ.get("KDECONNECT_BIN")
    candidates = [Path(override)] if override else []
    executable = shutil.which("kdeconnect-cli.exe")
    if executable:
        candidates.append(Path(executable).parent)
    for variable, suffix in [
        ("LOCALAPPDATA", "Programs/KDE Connect/bin"),
        ("ProgramFiles", "KDE Connect/bin"),
        ("ProgramFiles(x86)", "KDE Connect/bin"),
    ]:
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / suffix)
    for candidate in candidates:
        if (candidate / "dbus-1-3.dll").is_file():
            return candidate
    # Store package paths vary; query only the installed KDE Connect package.
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-AppxPackage -Name '*KDEConnect*').InstallLocation",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in result.stdout.splitlines():
            for candidate in (Path(line.strip()) / "bin", Path(line.strip())):
                if (candidate / "dbus-1-3.dll").is_file():
                    return candidate
    except (OSError, subprocess.TimeoutExpired):
        pass
    raise RuntimeError("Install and start KDE Connect, or set KDECONNECT_BIN to its bin folder.")
