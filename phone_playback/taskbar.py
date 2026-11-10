"""Read taskbar controls off the UI thread; never resize or patch Explorer."""

import ctypes as C
from ctypes import wintypes as W
import threading
from PySide6.QtCore import QRect


class MONITORINFOEX(C.Structure):
    _fields_ = [
        ("cbSize", W.DWORD),
        ("rcMonitor", W.RECT),
        ("rcWork", W.RECT),
        ("dwFlags", W.DWORD),
        ("szDevice", W.WCHAR * 32),
    ]


def rect_tuple(r):
    return (r.left, r.top, r.right, r.bottom)


def screen_key(screen):
    identity = screen.serialNumber()
    if not identity:
        point = screen.geometry().topLeft()
        identity = f"{point.x()},{point.y()}"
    return screen.name() + "@" + identity


class Taskbar:
    def __init__(self):
        self.u = C.WinDLL("user32")
        self.u.GetForegroundWindow.restype = W.HWND
        self.u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.u.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
        self.u.FindWindowExW.argtypes = [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR]
        self.u.FindWindowExW.restype = W.HWND
        self.u.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
        self.u.MonitorFromWindow.restype = W.HANDLE
        self.u.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MONITORINFOEX)]
        self.records = []
        self.error = None
        self.stop = threading.Event()
        threading.Thread(target=self._watch, daemon=True).start()

    def _taskbars(self):
        handles = []
        callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

        def visit(hwnd, _):
            name = C.create_unicode_buffer(256)
            self.u.GetClassNameW(hwnd, name, 256)
            if name.value in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
                handles.append(hwnd)
            return True

        self.u.EnumWindows.argtypes = [callback, W.LPARAM]
        self.u.EnumWindows(callback(visit), 0)
        return handles

    def _watch(self):
        try:
            import comtypes
            import comtypes.client
            from comtypes.gen import UIAutomationClient as UIA

            comtypes.CoInitialize()
        except ImportError:
            try:
                import comtypes.client

                comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen import UIAutomationClient as UIA

                comtypes.CoInitialize()
            except Exception as error:
                self.error = type(error).__name__
                return
        try:
            automation = comtypes.client.CreateObject(
                UIA.CUIAutomation, interface=UIA.IUIAutomation
            )
            condition = automation.CreateTrueCondition()
            while not self.stop.is_set():
                records = []
                for hwnd in self._taskbars():
                    r = W.RECT()
                    self.u.GetWindowRect(hwnd, C.byref(r))
                    monitor = MONITORINFOEX()
                    monitor.cbSize = C.sizeof(monitor)
                    self.u.GetMonitorInfoW(self.u.MonitorFromWindow(hwnd, 2), C.byref(monitor))
                    tray_handle = self.u.FindWindowExW(hwnd, None, "TrayNotifyWnd", None)
                    tray = W.RECT()
                    if tray_handle:
                        self.u.GetWindowRect(tray_handle, C.byref(tray))
                    else:
                        tray = W.RECT(max(r.left, r.right - 130), r.top, r.right, r.bottom)
                    occupied = [rect_tuple(tray)]
                    known = False
                    try:
                        root = automation.ElementFromHandle(hwnd)
                        elements = root.FindAll(4, condition)  # TreeScope_Descendants
                        for index in range(min(elements.Length, 600)):
                            item = elements.GetElement(index)
                            if item.CurrentIsOffscreen:
                                continue
                            if item.CurrentControlType in (
                                50000,
                                50002,
                                50003,
                                50004,
                                50005,
                                50011,
                                50031,
                            ):
                                box = item.CurrentBoundingRectangle
                                if box.right > box.left and box.bottom > box.top:
                                    occupied.append(rect_tuple(box))
                                    known = True
                    except Exception:
                        known = False
                    records.append(
                        {
                            "bar": rect_tuple(r),
                            "tray": rect_tuple(tray),
                            "monitor": monitor.szDevice,
                            "monitor_rect": rect_tuple(monitor.rcMonitor),
                            "primary": bool(monitor.dwFlags & 1),
                            "occupied": occupied,
                            "known": known,
                        }
                    )
                self.records = records
                self.stop.wait(1.5)
        except Exception as error:
            self.error = type(error).__name__
        finally:
            comtypes.CoUninitialize()

    def layouts(self, screens):
        result = []
        for record in self.records:
            physical = record["monitor_rect"]
            # Qt may use the EDID-friendly name instead of Win32's DISPLAYn name.
            # Windows preserves physical monitor origins in Qt's logical desktop.
            screen = next(
                (
                    s
                    for s in screens
                    if s.geometry().x() == physical[0] and s.geometry().y() == physical[1]
                ),
                None,
            )
            if screen is None and len(screens) == 1 and record.get("primary"):
                screen = screens[0]
            if screen is None:
                continue
            physical = record["monitor_rect"]
            logical = screen.geometry()
            d = screen.devicePixelRatio()

            def convert(box):
                l, t, r, b = box
                return QRect(
                    logical.left() + round((l - physical[0]) / d),
                    logical.top() + round((t - physical[1]) / d),
                    round((r - l) / d),
                    round((b - t) / d),
                )

            result.append(
                {
                    "screen": screen,
                    "name": screen_key(screen),
                    "bar": convert(record["bar"]),
                    "tray": convert(record["tray"]),
                    "occupied": [convert(b) for b in record["occupied"]],
                    "known": record["known"],
                    "physical_screen": physical,
                }
            )
        return result

    def fullscreen(self, ours, screen=None):
        hwnd = self.u.GetForegroundWindow()
        if int(hwnd or 0) in ours or not screen:
            return False
        r = W.RECT()
        if not self.u.GetWindowRect(hwnd, C.byref(r)):
            return False
        left, top, right, bottom = screen
        return r.left <= left and r.top <= top and r.right >= right and r.bottom >= bottom
