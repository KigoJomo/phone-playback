"""Optional per-user login startup; no elevation or scheduled task."""

import subprocess
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PhonePlayback"


def launch_command():
    if getattr(sys, "frozen", False):
        arguments = [sys.executable]
    else:
        executable = Path(sys.executable).with_name("pythonw.exe")
        arguments = [str(executable), "-m", "phone_playback"]
    return subprocess.list2cmdline(arguments)


def enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value == launch_command()
    except OSError:
        return False


def set_enabled(on):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
