# Third-party components

The application source is MIT licensed. The installer includes unmodified, dynamically linked runtime components with their own licenses:

- CPython 3.13: Python Software Foundation License. [Source](https://www.python.org/downloads/source/).
- PySide6 Essentials / Shiboken 6.10.1: Qt for Python, available under LGPLv3/GPLv3 or commercial terms. This open-source distribution uses the applicable open-source terms. [Exact source](https://github.com/pyside/pyside-setup/tree/v6.10.1).
- Qt 6.10.1: applicable open-source Qt and third-party component licenses. [Complete source archive](https://download.qt.io/official_releases/qt/6.10/6.10.1/single/qt-everywhere-src-6.10.1.tar.xz).
- comtypes 1.4.13: MIT license. [Source](https://github.com/enthought/comtypes/tree/1.4.13).
- PyInstaller bootloader: GPL with its distribution exception. The exception allows distributing the application under its own license. [Source and license](https://github.com/pyinstaller/pyinstaller/tree/v6.16.0).

License texts are included in `third-party-licenses/` and in the runtime's `base_library.zip` where supplied by the upstream packages. Qt's upstream LICENSES collection includes the texts referenced by its third-party components; consult the exact upstream source for attribution details. No modifications are made to these dependencies.

The installation keeps Qt/PySide DLLs outside the executable in `_internal/`. Compatible modified libraries may be substituted there. The application does not prohibit reverse engineering for debugging modifications to LGPL components. Build instructions and the application source are available in the public repository.

KDE Connect and its libdbus runtime are **not bundled**; the app loads libdbus from the user's existing KDE Connect installation. KDE Connect retains its own licenses.
