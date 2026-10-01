"""Allowlist tests for lighthouse-webapp. Run inside the image: mise run check."""

import importlib.machinery
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

loader = importlib.machinery.SourceFileLoader("webapp", "/usr/bin/lighthouse-webapp")
spec = importlib.util.spec_from_loader("webapp", loader)
webapp = importlib.util.module_from_spec(spec)
loader.exec_module(webapp)


def app(*allow):
    a = object.__new__(webapp.App)
    a.id, a.allow = "test", list(allow)
    return a


class Allows(unittest.TestCase):
    def test_exact_and_subdomains(self):
        a = app("pbskids.org")
        self.assertTrue(a.allows("https://pbskids.org/"))
        self.assertTrue(a.allows("https://www.pbskids.org/games"))
        self.assertTrue(a.allows("http://cdn.pbskids.org/x.js"))

    def test_lookalike_domains_blocked(self):
        a = app("pbskids.org")
        self.assertFalse(a.allows("https://evilpbskids.org/"))
        self.assertFalse(a.allows("https://pbskids.org.evil.com/"))
        self.assertFalse(a.allows("https://evil.com/?u=pbskids.org"))
        self.assertFalse(a.allows("https://pbskids.org@evil.com/"))

    def test_other_schemes(self):
        a = app("pbskids.org")
        self.assertTrue(a.allows("about:blank"))
        self.assertTrue(a.allows("blob:https://pbskids.org/1234"))
        self.assertFalse(a.allows("file:///etc/passwd"))
        self.assertFalse(a.allows("ftp://pbskids.org/"))

    def test_host_case(self):
        self.assertTrue(app("pbskids.org").allows("https://PBSKids.ORG/"))


class OpenLinks(unittest.TestCase):
    """lighthouse-webapp --open: links from other programs go to the web app that allows them."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name in ("parent", "system"):
            (self.tmp / name).mkdir()
        entry = "[Desktop Entry]\nName={0}\nExec=lighthouse-webapp {0}\nX-Lighthouse-Url=https://{1}/\nX-Lighthouse-Allow={1};\n"
        (self.tmp / "system/scratch.desktop").write_text(entry.format("scratch", "scratch.mit.edu"))
        (self.tmp / "system/pbskids.desktop").write_text(entry.format("pbskids", "pbskids.org"))
        (self.tmp / "system/tuxpaint.desktop").write_text("[Desktop Entry]\nName=Tux Paint\n")
        # A parent allowed nasa.gov in PBS Kids; their copy wins over the built-in one.
        (self.tmp / "parent/pbskids.desktop").write_text(
            entry.format("pbskids", "pbskids.org").replace("pbskids.org;\n", "pbskids.org;nasa.gov;\n"))
        self.dirs = webapp.APP_DIRS
        webapp.APP_DIRS = [self.tmp / "parent", self.tmp / "system"]

    def tearDown(self):
        webapp.APP_DIRS = self.dirs
        shutil.rmtree(self.tmp)

    def test_routes_to_the_allowing_app(self):
        self.assertEqual(webapp.app_for_url("https://scratch.mit.edu/projects/1"), "scratch")
        self.assertEqual(webapp.app_for_url("https://www.nasa.gov/kids"), "pbskids")

    def test_everything_else_goes_nowhere(self):
        for url in ("https://youtube.com/", "file:///etc/passwd", "https://scratch.mit.edu.evil.com/"):
            self.assertIsNone(webapp.app_for_url(url), url)


if __name__ == "__main__":
    unittest.main()
