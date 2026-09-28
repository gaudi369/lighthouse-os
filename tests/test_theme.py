"""lighthouse-theme: switching, locking, and what the kid's picker may do.

Run inside the image as root (mise run check) against a scratch LIGHTHOUSE_ROOT.
PKEXEC_UID is set by pkexec, so setting it here stands in for the picker.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest


class Theme(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        shutil.copytree("/usr/share/lighthouse", f"{self.root}/usr/share/lighthouse")
        os.makedirs(f"{self.root}/etc/lighthouse/noctalia")

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_theme(self, *args, kid=False):
        env = {**os.environ, "LIGHTHOUSE_ROOT": self.root}
        if kid:
            env["PKEXEC_UID"] = "1001"
        return subprocess.run(["lighthouse-theme", *args], env=env, capture_output=True, text=True)

    def current(self):
        with open(f"{self.root}/etc/lighthouse/theme/theme.json") as f:
            return json.load(f)["id"]

    def test_set_installs_every_part(self):
        self.assertEqual(self.run_theme("set", "owl").returncode, 0)
        self.assertEqual(self.current(), "owl")
        with open(f"{self.root}/etc/lighthouse/noctalia/theme.toml") as f:
            self.assertIn('custom_palette = "owl"', f.read())
        self.assertTrue(os.path.exists(f"{self.root}/etc/lighthouse/theme/niri.kdl"))

    def test_unknown_and_path_like_ids_are_refused(self):
        for bad in ("nope", "../../etc", "owl/../piglet", ""):
            self.assertNotEqual(self.run_theme("set", bad).returncode, 0, bad)

    def test_kid_can_set_when_unlocked(self):
        self.assertEqual(self.run_theme("set", "tigger", kid=True).returncode, 0)
        self.assertEqual(self.current(), "tigger")

    def test_kid_cannot_set_when_locked(self):
        self.run_theme("set", "piglet")
        self.run_theme("lock")
        result = self.run_theme("set", "tigger", kid=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("locked", result.stderr)
        self.assertEqual(self.current(), "piglet")

    def test_parent_can_set_when_locked(self):
        self.run_theme("lock")
        self.assertEqual(self.run_theme("set", "rabbit").returncode, 0)
        self.assertEqual(self.current(), "rabbit")

    def test_kid_cannot_lock_or_unlock(self):
        self.run_theme("lock")
        self.assertNotEqual(self.run_theme("unlock", kid=True).returncode, 0)
        self.assertEqual(self.run_theme("locked").stdout.strip(), "yes")
        self.run_theme("unlock")
        self.assertNotEqual(self.run_theme("lock", kid=True).returncode, 0)
        self.assertEqual(self.run_theme("locked").stdout.strip(), "no")


if __name__ == "__main__":
    unittest.main()
