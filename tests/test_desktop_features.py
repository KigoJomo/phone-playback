import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage, QColor
from phone_playback.placement import free_slot, WheelSteps
from phone_playback.player_follow import PlayerFollower
from phone_playback.theme import album_accent, accent_for
from phone_playback import startup


class PlacementTests(unittest.TestCase):
    def test_never_overlaps_task_buttons_or_tray(self):
        self.assertEqual(free_slot(0, 1920, [(0, 700), (1700, 1920)], 260), 1432)
        self.assertIsNone(free_slot(0, 800, [(0, 550), (700, 800)], 260))

    def test_saved_location_moves_to_nearest_free_gap_after_resize(self):
        x = free_slot(-1920, 0, [(-1920, -1700), (-800, 0)], 260, desired=-1000)
        self.assertEqual(x, -1068)
        self.assertIsNone(free_slot(0, 200, [], 260))

    def test_high_resolution_wheel_and_shift_are_separate(self):
        wheel = WheelSteps()
        self.assertEqual(wheel.consume(40), ("volume", 0))
        self.assertEqual(wheel.consume(80), ("volume", 5))
        self.assertEqual(wheel.consume(-240, True), ("seek", -20))
        self.assertEqual(wheel.consume(0, True), ("seek", 0))
        wheel.consume(60, True)
        self.assertEqual(wheel.consume(60), ("volume", 0))


class FollowerTests(unittest.TestCase):
    def test_follow_newly_playing_and_remain_stable(self):
        follower = PlayerFollower()
        self.assertEqual(follower.choose("Music", {"Music": "Playing", "VLC": "Paused"}), "Music")
        self.assertEqual(follower.choose("Music", {"Music": "Paused", "VLC": "Playing"}), "VLC")
        self.assertEqual(follower.choose("VLC", {"Music": "Paused", "VLC": "Playing"}), "VLC")

    def test_lock_and_simultaneous_sessions_do_not_oscillate(self):
        follower = PlayerFollower()
        states = {"Music": "Playing", "VLC": "Playing"}
        self.assertEqual(follower.choose("Music", states), "Music")
        self.assertEqual(follower.choose("Music", states, locked="VLC"), "VLC")
        self.assertEqual(follower.choose("VLC", {}, locked="Missing"), "Missing")

    def test_foreign_phone_cannot_match_and_duplicate_identity_is_ignored(self):
        follower = PlayerFollower()
        services = {
            "org.mpris.MediaPlayer2.kdeconnect.one": ("Music - My phone", "Playing"),
            "org.mpris.MediaPlayer2.kdeconnect.two": ("VLC - Other phone", "Playing"),
        }

        def call(path, interface, method, args=(), destination=None):
            if method == "ListNames":
                return [list(services)]
            return [services[destination][0 if args[1] == "Identity" else 1]]

        self.assertEqual(
            follower.statuses(call, "My phone", ["Music", "VLC"]), {"Music": "Playing"}
        )
        services["org.mpris.MediaPlayer2.kdeconnect.three"] = ("Music - My phone", "Paused")
        self.assertEqual(follower.statuses(call, "My phone", ["Music", "VLC"]), {})


class AlbumTests(unittest.TestCase):
    def test_extracts_colour_and_never_fetches_remote_art(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "art.png"
            image = QImage(24, 24, QImage.Format.Format_ARGB32)
            image.fill(QColor("#ce543e"))
            image.save(str(path))
            colour = album_accent(QUrl.fromLocalFile(str(path)).toString())
            self.assertIsNotNone(colour)
            self.assertLess(QColor(colour).hsvHueF(), 0.08)
            self.assertEqual(accent_for({"theme_source": "album"}, colour), colour)
        self.assertIsNone(album_accent("https://example.com/cover.jpg"))

    def test_missing_art_falls_back_to_windows(self):
        with patch("phone_playback.theme.windows_accent", return_value="#2563eb"):
            self.assertEqual(accent_for({"theme_source": "album"}), "#2563eb")


class StartupTests(unittest.TestCase):
    def test_installed_build_registers_itself_and_source_uses_pythonw(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", r"C:\Example App\PhonePlayback.exe"),
        ):
            self.assertEqual(startup.launch_command(), '"C:\\Example App\\PhonePlayback.exe"')
        with patch.object(sys, "executable", r"C:\Example\python.exe"):
            self.assertIn("pythonw.exe", startup.launch_command())
            self.assertTrue(startup.launch_command().endswith("-m phone_playback"))

    def test_startup_toggle_only_touches_its_own_current_user_value(self):
        with (
            patch.object(startup.winreg, "CreateKey") as create,
            patch.object(startup.winreg, "SetValueEx") as set_value,
            patch.object(startup.winreg, "DeleteValue") as delete,
        ):
            startup.set_enabled(True)
            self.assertEqual(
                create.call_args.args, (startup.winreg.HKEY_CURRENT_USER, startup.RUN_KEY)
            )
            self.assertEqual(set_value.call_args.args[1], "PhonePlayback")
            startup.set_enabled(False)
            self.assertEqual(delete.call_args.args[1], "PhonePlayback")
