import unittest
from phone_playback.media import PlaybackClock, seek_relative, seek_to


class SeekingTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.call = lambda *args: self.calls.append(args)
        self.state = {
            "player": "Music",
            "title": "Track",
            "artist": "Artist",
            "position": 60000,
            "length": 180000,
            "isPlaying": True,
            "canSeek": True,
        }

    def test_relative_seek_uses_android_absolute_milliseconds(self):
        clock = PlaybackClock()
        clock.observe(self.state, now=10)
        target = seek_relative(
            self.call, "/media", "media.interface", self.state, -15, clock, now=20
        )
        self.assertEqual(target, 55000)  # 60s metadata + 10s elapsed - 15s
        self.assertEqual(
            self.calls,
            [
                (
                    "/media",
                    "org.freedesktop.DBus.Properties",
                    "Set",
                    ("media.interface", "position", (55000,)),
                )
            ],
        )

    def test_bounds_in_both_directions(self):
        self.assertEqual(seek_to(self.call, "/media", "media", self.state, -15000), 0)
        self.assertEqual(seek_to(self.call, "/media", "media", self.state, 999999), 180000)

    def test_disabled_and_unknown_duration_do_not_send(self):
        for state in ({**self.state, "canSeek": False}, {**self.state, "length": 0}):
            self.assertIsNone(seek_to(self.call, "/media", "media", state, 100))
        self.assertEqual(self.calls, [])

    def test_paused_position_does_not_advance(self):
        clock = PlaybackClock()
        paused = {**self.state, "isPlaying": False}
        clock.observe(paused, now=1)
        self.assertEqual(clock.observe(paused, now=50), 60000)

    def test_new_track_resets_elapsed_clock(self):
        clock = PlaybackClock()
        clock.observe(self.state, now=10)
        new = {**self.state, "title": "New track", "position": 0}
        self.assertEqual(clock.observe(new, now=50), 0)
        self.assertEqual(clock.observe(new, now=55), 5000)


if __name__ == "__main__":
    unittest.main()
