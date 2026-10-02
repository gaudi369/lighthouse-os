"""lighthouse-timekeeper: lock screen text and the setup screen's Wi-Fi list. Run inside the image: mise run check."""

import importlib.machinery
import importlib.util
import unittest

loader = importlib.machinery.SourceFileLoader("timekeeper", "/usr/bin/lighthouse-timekeeper")
spec = importlib.util.spec_from_loader("timekeeper", loader)
timekeeper = importlib.util.module_from_spec(spec)
loader.exec_module(timekeeper)


class WifiList(unittest.TestCase):
    def test_escaped_colons_and_backslashes(self):
        self.assertEqual(timekeeper.split_terse(r"*:80:WPA2:Cafe\:Guest\\5G"),
                         ["*", "80", "WPA2", "Cafe:Guest\\5G"])

    def test_one_entry_per_name_connected_first_then_strongest(self):
        out = "\n".join([
            " :40:WPA2:Home",
            " :90:WPA2:Home",       # the same network from a closer access point
            " :70::Library Free",   # open
            "*:30:WPA1 WPA2:Upstairs",
            " :99:WPA2:",           # hidden: no name to pick
        ])
        self.assertEqual(timekeeper.parse_wifi_list(out), [
            {"ssid": "Upstairs", "signal": 30, "secure": True, "in_use": True},
            {"ssid": "Home", "signal": 90, "secure": True, "in_use": False},
            {"ssid": "Library Free", "signal": 70, "secure": False, "in_use": False},
        ])


class LockText(unittest.TestCase):
    def test_every_reason_has_a_heading(self):
        for reason in ("used-up", "closed", "paused", "setup"):
            emoji, title, _detail = timekeeper.lock_text({"reason": reason, "opens": "07:00"})
            self.assertTrue(emoji and title)
        self.assertIn("07:00", timekeeper.lock_text({"reason": "closed", "opens": "07:00"})[2])


if __name__ == "__main__":
    unittest.main()
