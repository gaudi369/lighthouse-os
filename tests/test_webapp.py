"""Allowlist tests for lighthouse-webapp. Run inside the image: mise run check."""

import importlib.machinery
import importlib.util
import unittest

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


if __name__ == "__main__":
    unittest.main()
