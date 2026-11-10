"""Build an unsigned, per-user Windows installer using PyInstaller and Inno Setup."""

from importlib.metadata import distribution
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from phone_playback import __version__


def checked(arguments, env=None):
    subprocess.run(arguments, cwd=ROOT, check=True, env=env)


def main():
    if sys.platform != "win32":
        raise SystemExit("Build on Windows x64.")
    # Generate the COM type library before freezing; include it in the frozen app.
    import comtypes.client

    comtypes.client.GetModule("UIAutomationCore.dll")
    # Do not let unrelated tools on PATH supply incompatible DLLs (notably ICU).
    windows = Path(os.environ["WINDIR"])
    environment = {
        **os.environ,
        "PATH": os.pathsep.join(
            [
                sys.base_prefix,
                str(Path(sys.executable).parent),
                str(windows / "System32"),
                str(windows),
                str(windows / "System32/Wbem"),
            ]
        ),
    }
    checked(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onedir",
            "--name",
            "PhonePlayback",
            "--icon",
            str(ROOT / "docs/phone-playback.ico"),
            "--specpath",
            str(ROOT / "build/spec"),
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build/pyinstaller"),
            "--paths",
            str(ROOT),
            "--collect-submodules",
            "comtypes.gen",
            "--hidden-import",
            "comtypes.stream",
            str(ROOT / "tools/frozen_entry.py"),
        ],
        env=environment,
    )
    bundle = ROOT / "dist/PhonePlayback"
    notices = bundle / "third-party-licenses"
    notices.mkdir(parents=True, exist_ok=True)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, notices / "PYTHON-LICENSE.txt")
    for name in ("PySide6-Essentials", "shiboken6", "comtypes", "PyInstaller"):
        dependency = distribution(name)
        for item in dependency.files:
            if "/licenses/" in str(item).replace("\\", "/"):
                target = notices / name / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dependency.locate_file(item), target)
    # Include open-source Qt/PySide license texts, not just the wheel's commercial notice.
    for repository, ref in [("qt/qtbase", "v6.10.1"), ("pyside/pyside-setup", "v6.10.1")]:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/contents/LICENSES?ref={ref}",
            headers={"User-Agent": "PhonePlayback-build"},
        )
        with urllib.request.urlopen(request) as response:
            files = json.load(response)
        for entry in files:
            if entry["type"] != "file":
                continue
            destination = notices / repository.replace("/", "-") / entry["name"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(entry["download_url"]) as response:
                destination.write_bytes(response.read())
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copy2(ROOT / "README.md", bundle / "README.md")
    candidates = [
        shutil.which("ISCC.exe"),
        str(Path(os.environ["LOCALAPPDATA"]) / "Programs/Inno Setup 6/ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    ]
    compiler = next((p for p in candidates if p and Path(p).is_file()), None)
    if not compiler:
        raise SystemExit("Install Inno Setup 6 or add ISCC.exe to PATH.")
    checked([compiler, f"/DAppVersion={__version__}", str(ROOT / "installer/phone-playback.iss")])
    installer = ROOT / f"release/PhonePlayback-Setup-{__version__}-win-x64.exe"
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    (ROOT / "release/SHA256SUMS.txt").write_text(f"{digest}  {installer.name}\n", encoding="utf-8")
    print(f"Built {installer.name}: {digest}")


if __name__ == "__main__":
    main()
