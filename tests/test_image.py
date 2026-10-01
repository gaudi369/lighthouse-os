"""The built image: what the kid can launch. Run inside the image: mise run check.

A package that pulls in a terminal, or puts a new app in the launcher, fails
here, so it can't reach a kid unnoticed. When you add an app on purpose, add
it to LAUNCHER.
"""

import configparser
import shutil
import unittest
from pathlib import Path

APPS = Path("/usr/share/applications")
# Desktop entries the kid sees in the launcher.
LAUNCHER = {"pbskids", "scratch", "lighthouse-themes", "tuxpaint", "org.kde.gcompris"}
TERMINALS = ["alacritty", "foot", "kitty", "xterm", "gnome-terminal", "ptyxis", "konsole",
             "wezterm", "ghostty", "xfce4-terminal", "terminator", "tilix", "urxvt", "st"]


def visible_entries():
    for path in sorted(APPS.glob("*.desktop")):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        parser.read(path)
        entry = parser["Desktop Entry"] if parser.has_section("Desktop Entry") else {}
        if entry.get("Type") != "Application":
            continue
        if entry.get("NoDisplay", "false") == "true" or entry.get("Hidden", "false") == "true":
            continue
        if entry.get("OnlyShowIn"):
            continue
        yield path.stem


class Image(unittest.TestCase):
    def test_no_terminal_installed(self):
        self.assertEqual([t for t in TERMINALS if shutil.which(t)], [])

    def test_launcher_shows_only_kid_apps(self):
        self.assertEqual(set(visible_entries()), LAUNCHER)


if __name__ == "__main__":
    unittest.main()
