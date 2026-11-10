"""Offscreen interaction tests; never send input to the user's desktop."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from phone_playback import ui as m


class InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = m.QApplication.instance() or m.QApplication([])

    def setUp(self):
        self.clock = SimpleNamespace(now=100.0)
        self.pointer = SimpleNamespace(point=m.QPoint(0, 0))
        patches = [
            patch.object(m, "PREVIEW", True),
            patch.object(m, "time", SimpleNamespace(monotonic=lambda: self.clock.now)),
            patch.object(m, "QCursor", SimpleNamespace(pos=lambda: self.pointer.point)),
            patch.object(m.core, "CONFIG", {}),
            patch.object(
                m,
                "Taskbar",
                lambda: SimpleNamespace(
                    geometry=lambda: (m.QRect(0, 760, 800, 40), m.QRect(700, 760, 100, 40)),
                    fullscreen=lambda ours: False,
                ),
            ),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.controller = m.Controller()
        self.controller.timer.stop()
        self.controller.apply_state(
            {
                "title": "A long song title for scrolling across the taskbar",
                "artist": "Artist",
                "player": "Music",
                "playerList": ["Music", "VLC"],
                "isPlaying": True,
                "canSeek": True,
                "position": 15000,
                "length": 180000,
                "volume": 40,
            }
        )
        self.app.processEvents()

    def tearDown(self):
        self.controller.panel.close()
        self.controller.pill.close()
        self.controller.menu.close()
        while not m.core.commands.empty():
            m.core.commands.get_nowait()

    def test_hover_opens_and_leaving_closes(self):
        c = self.controller
        self.assertFalse(c.panel.isVisible())
        self.pointer.point = c.pill.geometry().center()
        c.hover_since = None
        c.poll()
        self.clock.now += 0.3
        c.poll()
        self.assertTrue(c.panel.isVisible())
        self.pointer.point = c.panel.geometry().center()
        self.clock.now += 2
        c.poll()
        self.assertTrue(c.panel.isVisible())
        self.pointer.point = m.QPoint(0, 0)
        c.poll()
        self.clock.now += 0.6
        c.poll()
        self.assertFalse(c.panel.isVisible())

    def test_sliders_and_transport_route_to_phone(self):
        c = self.controller
        c.panel.volume.setValue(35)
        c.panel.volume.sliderReleased.emit()
        self.assertEqual(m.core.commands.get_nowait(), ("set-volume", 35))
        c.panel.seek.setValue(32000)
        c.panel.seek.sliderReleased.emit()
        self.assertEqual(m.core.commands.get_nowait(), ("position", 32000))
        c.panel.controls[0].callback()
        self.assertEqual(m.core.commands.get_nowait(), ("seek", -15))
        c.panel.play.callback()
        self.assertEqual(m.core.commands.get_nowait(), ("action", "PlayPause"))

    def test_disconnected_commands_are_not_queued(self):
        c = self.controller
        c.offline("Phone offline")
        c.command("action", "Next")
        self.assertTrue(m.core.commands.empty())
        self.assertFalse(c.panel.play.isEnabled())
        self.assertFalse(c.panel.seek.isEnabled())

    def test_icon_uses_phone_reported_volume(self):
        c = self.controller
        for volume, icon in ((0, "muted"), (10, "low"), (50, "medium"), (90, "high")):
            c.apply_state({**c.state, "volume": volume})
            self.assertEqual(c.panel.volume_icon.symbol, "volume-" + icon)
            self.assertIn(str(volume) + "%", c.panel.volume_icon.toolTip())

    def test_custom_colour_persists_and_windows_changes_refresh(self):
        c = self.controller
        with (
            patch.object(m.QColorDialog, "getColor", return_value=m.QColor("#ea580c")),
            patch.object(m, "save_config") as save,
        ):
            c.choose_custom_colour()
            self.assertEqual(c.settings["accent_colour"], "#ea580c")
            self.assertEqual(m.ACCENT, "#ea580c")
            self.assertTrue(c.custom_theme.isChecked())
            save.assert_called_once()
        with (
            patch("phone_playback.theme.windows_accent", return_value="#2563eb"),
            patch.object(m, "save_config"),
        ):
            c.follow_windows_theme()
            self.assertEqual(m.ACCENT, "#2563eb")
            self.assertTrue(c.windows_theme.isChecked())
        with patch("phone_playback.theme.windows_accent", return_value="#8b5cf6"):
            c.apply_theme()
            self.assertEqual(m.ACCENT, "#8b5cf6")

    def test_marquee_and_layout(self):
        c = self.controller
        self.clock.now += 5
        c.pill.title.animate()
        self.assertGreater(c.pill.title.offset, 0)
        self.assertLessEqual(c.panel.layout().minimumSize().height(), c.panel.height())

    def test_first_run_phone_selection_works_while_disconnected(self):
        c = self.controller
        c.connected = False
        device = {"id": "test_phone", "name": "Test phone", "reachable": True}
        c.update_devices([device])
        c.phone_menu.actions()[0].trigger()
        self.assertEqual(m.core.commands.get_nowait(), ("device", device))

    def test_discovery_excludes_computers_and_unpaired_devices(self):
        info = {
            "computer": {"type": "desktop", "isPaired": True, "isReachable": True},
            "phone": {"type": "phone", "isPaired": True, "isReachable": True, "name": "Phone"},
            "stranger": {"type": "phone", "isPaired": False, "isReachable": True},
        }

        def call(path, interface, method, args=()):
            if method == "devices":
                return [list(info)]
            return [list(info[path.rsplit("/", 1)[1]].items())]

        self.assertEqual(
            m.core.devices(call), [{"id": "phone", "name": "Phone", "reachable": True}]
        )


if __name__ == "__main__":
    unittest.main()
