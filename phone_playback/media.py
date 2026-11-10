"""Time and unit conversions independent of Windows and the transport."""

import time


def clamp_position(position_ms, length_ms):
    return max(0, min(int(length_ms or 0), int(position_ms)))


class PlaybackClock:
    def __init__(self):
        self.signature = None
        self.position = 0
        self.updated_at = 0
        self.playing = False

    def observe(self, state, now=None):
        now = time.monotonic() if now is None else now
        signature = (
            state.get("player"),
            state.get("title"),
            state.get("artist"),
            state.get("length"),
            state.get("position"),
            bool(state.get("isPlaying")),
        )
        if signature != self.signature:
            self.signature = signature
            self.position = int(state.get("position", 0))
            self.updated_at = now
            self.playing = bool(state.get("isPlaying"))
        elapsed = (now - self.updated_at) * 1000 if self.playing else 0
        return clamp_position(self.position + elapsed, state.get("length", 0))


def seek_to(call, path, interface, state, position_ms):
    if not state.get("canSeek") or not state.get("length"):
        return None
    target = clamp_position(position_ms, state["length"])
    # Android's receiver handles SetPosition in milliseconds. It ignores Seek.
    call(path, "org.freedesktop.DBus.Properties", "Set", (interface, "position", (target,)))
    return target


def seek_relative(call, path, interface, state, seconds, clock, now=None):
    current = clock.observe(state, now)
    return seek_to(call, path, interface, state, current + seconds * 1000)
