import unittest
from unittest.mock import patch
from phone_playback.theme import accent_for, foreground_for, volume_symbol


class ThemeTests(unittest.TestCase):
    def test_default_follows_windows_and_custom_takes_precedence(self):
        with patch("phone_playback.theme.windows_accent", return_value="#2563eb"):
            self.assertEqual(accent_for({}), "#2563eb")
            self.assertEqual(
                accent_for({"theme_source": "custom", "accent_colour": "#ea580c"}), "#ea580c"
            )
            self.assertEqual(
                accent_for({"theme_source": "custom", "accent_colour": "invalid"}), "#2563eb"
            )

    def test_foreground_changes_to_stay_readable(self):
        self.assertEqual(foreground_for("#ffffff"), "#142019")
        self.assertEqual(foreground_for("#000000"), "#f5f5f7")

    def test_volume_level_boundaries(self):
        expected = {
            0: "muted",
            1: "low",
            33: "low",
            34: "medium",
            66: "medium",
            67: "high",
            100: "high",
        }
        for value, suffix in expected.items():
            self.assertEqual(volume_symbol(value), "volume-" + suffix)
