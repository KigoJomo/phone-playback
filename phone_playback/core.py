"""Small, local KDE Connect remote for one paired phone. No network listener."""

import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import queue
import threading
import time

BASE = Path(__file__).resolve().parent
from .config import load, save
from .media import PlaybackClock, seek_to, seek_relative
from .player_follow import PlayerFollower

CONFIG = load()
MEDIA = "org.kde.kdeconnect.device.mprisremote"
PROPERTIES = "org.freedesktop.DBus.Properties"
user32 = C.WinDLL("user32", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
kernel32.CreateMutexW.restype = W.HANDLE
kernel32.CreateEventW.argtypes = [C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR]
kernel32.CreateEventW.restype = W.HANDLE
kernel32.SetEvent.argtypes = [W.HANDLE]
kernel32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]


def single_instance():
    global mutex, show_event
    mutex = kernel32.CreateMutexW(None, False, "Local\\PhonePlayback")
    already_running = C.get_last_error() == 183
    show_event = kernel32.CreateEventW(None, False, False, "Local\\PhonePlaybackShow")
    if already_running:
        kernel32.SetEvent(show_event)
        return False
    return True


try:
    C.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PhonePlayback.Desktop")
except OSError:
    pass

commands = queue.Queue()
updates = queue.Queue()
stop = threading.Event()


def devices(call):
    result = []
    for device_id in call("/modules/kdeconnect", "org.kde.kdeconnect.daemon", "devices")[0]:
        path = "/modules/kdeconnect/devices/" + device_id
        info = dict(call(path, PROPERTIES, "GetAll", ("org.kde.kdeconnect.device",))[0])
        if info.get("isPaired") and info.get("type") in ("phone", "tablet"):
            result.append(
                {
                    "id": device_id,
                    "name": info.get("name", "Phone"),
                    "reachable": bool(info.get("isReachable")),
                }
            )
    return result


def select_device(device):
    CONFIG.update(device_id=device["id"], device_name=device["name"])
    save(CONFIG)


def media_worker():
    last_request = last_discovery = last_follow = 0
    clock = PlaybackClock()
    follower = PlayerFollower()
    statuses = {}
    while not stop.is_set():
        pending = []
        try:
            from .bus import call

            while True:
                try:
                    item = commands.get_nowait()
                except queue.Empty:
                    break
                action, value = item[:2]
                if action == "device":
                    select_device(value)
                    clock = PlaybackClock()
                    follower = PlayerFollower()
                    last_follow = 0
                    pending.clear()
                elif action == "follow":
                    if value:
                        CONFIG.pop("player_lock", None)
                    else:
                        CONFIG["player_lock"] = CONFIG.get("last_player")
                    save(CONFIG)
                    last_follow = 0
                elif action == "player":
                    CONFIG["player_lock"] = value
                    save(CONFIG)
                else:
                    pending.append(item)
            now = time.monotonic()
            if now - last_discovery > 10 or not last_discovery:
                available = devices(call)
                updates.put(("devices", available))
                reachable = [d for d in available if d["reachable"]]
                if not CONFIG.get("device_id") and len(reachable) == 1:
                    select_device(reachable[0])
                last_discovery = now
            if not CONFIG.get("device_id"):
                raise RuntimeError("Choose a paired phone from the tray menu.")
            phone_path = "/modules/kdeconnect/devices/" + CONFIG["device_id"]
            media_path = phone_path + "/mprisremote"
            device = dict(call(phone_path, PROPERTIES, "GetAll", ("org.kde.kdeconnect.device",))[0])
            if not device.get("isPaired") or not device.get("isReachable"):
                raise RuntimeError("Phone offline. Check KDE Connect and Wi-Fi.")
            state = dict(call(media_path, PROPERTIES, "GetAll", (MEDIA,))[0])
            players = state.get("playerList", [])
            locked = CONFIG.get("player_lock")
            if now - last_follow > 1.2 or not last_follow:
                try:
                    statuses = follower.statuses(call, device.get("name", ""), players)
                except RuntimeError:
                    statuses = {}
                last_follow = now
            target = follower.choose(state.get("player"), statuses, locked)
            if target and target in players and target != state.get("player"):
                call(media_path, PROPERTIES, "Set", (MEDIA, "player", (target,)))
                state = dict(call(media_path, PROPERTIES, "GetAll", (MEDIA,))[0])
                clock = PlaybackClock()
            clock.observe(state)
            if now - last_request > 10:
                call(media_path, MEDIA, "requestPlayerList")
                last_request = now
            for item in pending:
                action, value = item[:2]
                requested = item[2] if len(item) > 2 else state.get("player")
                if not requested or requested not in players or (locked and locked not in players):
                    continue
                # A click acts on the player shown when it was made, even if another starts.
                if requested != state.get("player"):
                    call(media_path, PROPERTIES, "Set", (MEDIA, "player", (requested,)))
                    state = dict(call(media_path, PROPERTIES, "GetAll", (MEDIA,))[0])
                    clock = PlaybackClock()
                if action == "action" and value in ("PlayPause", "Previous", "Next"):
                    call(media_path, MEDIA, "sendAction", (value,))
                elif action in ("volume", "set-volume"):
                    volume = state.get("volume", 0) + value if action == "volume" else value
                    volume = max(0, min(100, volume))
                    call(media_path, PROPERTIES, "Set", (MEDIA, "volume", (volume,)))
                    state["volume"] = volume
                elif action in ("seek", "position"):
                    if action == "seek":
                        target = seek_relative(call, media_path, MEDIA, state, value, clock)
                    else:
                        target = seek_to(call, media_path, MEDIA, state, value)
                    if target is not None:
                        state["position"] = target
                        clock = PlaybackClock()
                        clock.observe(state)
            state["device_name"] = device.get("name", CONFIG.get("device_name", "Phone"))
            state["playerLocked"] = bool(locked)
            state["playerAvailable"] = not locked or locked in players
            state["followAvailable"] = bool(statuses)
            if locked and locked not in players:
                state.update(
                    player=locked,
                    title="Pinned player unavailable",
                    artist="Start it on your phone or choose another player",
                    localAlbumArtUrl="",
                    isPlaying=False,
                    canSeek=False,
                )
            CONFIG["last_player"] = state.get("player")
            updates.put(("state", state))
        except Exception as error:
            # Do not replay queued clicks after reconnecting.
            while not commands.empty():
                try:
                    item = commands.get_nowait()
                    if item[0] in ("device", "follow", "player"):
                        # Settings changes must still work while the phone is offline.
                        if item[0] == "device":
                            select_device(item[1])
                        elif item[0] == "player":
                            CONFIG["player_lock"] = item[1]
                            save(CONFIG)
                        elif item[1]:
                            CONFIG.pop("player_lock", None)
                            save(CONFIG)
                except queue.Empty:
                    break
            updates.put(("error", str(error)))
            stop.wait(1)
        stop.wait(0.35)


# Ctrl+Alt bindings use MOD_NOREPEAT, so held keys don't queue track skips.
HOTKEYS = {
    1: (0x20, "action", "PlayPause", "Ctrl+Alt+Space"),
    2: (0x25, "action", "Previous", "Ctrl+Alt+Left"),
    3: (0x27, "action", "Next", "Ctrl+Alt+Right"),
    4: (0x26, "volume", 5, "Ctrl+Alt+Up"),
    5: (0x28, "volume", -5, "Ctrl+Alt+Down"),
    6: (ord("M"), "show", None, "Ctrl+Alt+M"),
}


def hotkey_worker():
    user32.RegisterHotKey.argtypes = [W.HWND, C.c_int, W.UINT, W.UINT]
    user32.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
    registered, unavailable = [], []
    try:
        for number, (key, action, value, label) in HOTKEYS.items():
            if user32.RegisterHotKey(None, number, 0x4003, key):
                registered.append(number)
            else:
                unavailable.append(label)
        updates.put(("hotkeys", unavailable))
        message = W.MSG()
        while not stop.wait(0.03):
            while user32.PeekMessageW(C.byref(message), None, 0x0312, 0x0312, 1):
                binding = HOTKEYS.get(message.wParam)
                if binding:
                    _, action, value, _ = binding
                    if action == "show":
                        updates.put(("show", None))
                    else:
                        commands.put((action, value))
    finally:
        for number in registered:
            user32.UnregisterHotKey(None, number)
