import tempfile
import unittest
from pathlib import Path

from controle_elk.storage.preferences import DeviceStore, SavedDevice


class PreferencesTests(unittest.TestCase):
    def test_saved_devices_colors_and_gradients_survive_reopening(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.sqlite3"
            store = DeviceStore(path)
            device = SavedDevice("00:00:00:00:00:01", "ELK-BLEDOM", "4")
            store.remember(device)
            store.rename(device.address, "Mesa")
            store.save_color("#22ABFA")
            store.save_gradient("Noite", ["#FF0000", "#0000FF:2", "loop"])
            store.save_gradient("Noite", ["#FFFF00:5"], sequence=True)
            store.save_brightness(26)
            store.save_brightness(42)

            reopened = DeviceStore(path)
            self.assertEqual(
                reopened.load(),
                [SavedDevice(device.address, device.model, "4", "Mesa")],
            )
            self.assertEqual(reopened.load_colors(), ["#22ABFA"])
            self.assertEqual(reopened.load_brightness(), 42)
            self.assertEqual(reopened.load_last_device(), device.address)
            self.assertEqual(
                reopened.load_gradients(), {"Noite": ["#FF0000", "#0000FF:2", "loop"]}
            )
            self.assertEqual(
                reopened.load_gradients(sequence=True), {"Noite": ["#FFFF00:5"]}
            )

    def test_fresh_database_starts_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DeviceStore(Path(directory) / "local" / "preferences.sqlite3")
            self.assertEqual(store.load(), [])
            self.assertEqual(store.load_colors(), [])
            self.assertEqual(store.load_gradients(), {})
            self.assertEqual(store.load_brightness(), 70)
            self.assertIsNone(store.load_last_device())
