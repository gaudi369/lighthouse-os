"""lighthouse-parent: requests, approvals, app changes, screen time, and the web interface."""

import datetime
import http.client
import importlib.machinery
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

loader = importlib.machinery.SourceFileLoader("parent", "/usr/bin/lighthouse-parent")
spec = importlib.util.spec_from_loader("parent", loader)
parent = importlib.util.module_from_spec(spec)
loader.exec_module(parent)

BUILTIN = """[Desktop Entry]
Type=Application
Name=PBS Kids
Exec=lighthouse-webapp pbskids
X-Lighthouse-Url=https://pbskids.org/
X-Lighthouse-Allow=pbskids.org;pbs.org;
"""


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "system").mkdir()
        (self.tmp / "system/pbskids.desktop").write_text(BUILTIN)
        (self.tmp / "system/other.desktop").write_text("[Desktop Entry]\nName=Not a web app\n")
        self.store = parent.Store(self.tmp / "state", self.tmp / "system")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_lists_only_web_apps(self):
        self.assertEqual([a["id"] for a in self.store.apps()], ["pbskids"])

    def test_request_validation_and_dedup(self):
        r1 = self.store.add_request("pbskids", "https://www.youtube.com/watch?v=1")
        r2 = self.store.add_request("pbskids", "https://www.youtube.com/watch?v=2")
        self.assertEqual(r1["id"], r2["id"])
        for app, url in (("nope", "https://a.org/"), ("pbskids", "file:///etc/passwd"),
                         ("pbskids", "https://localhost/"), ("../x", "https://a.org/")):
            with self.assertRaises(ValueError, msg=(app, url)):
                self.store.add_request(app, url)

    def test_approve_writes_parent_copy_and_keeps_builtin(self):
        r = self.store.add_request("pbskids", "https://www.youtube.com/watch?v=1")
        self.store.decide(r["id"], True)
        copy = self.tmp / "state/apps/applications/pbskids.desktop"
        self.assertIn("X-Lighthouse-Allow=pbskids.org;pbs.org;youtube.com;", copy.read_text())
        self.assertIn("Exec=lighthouse-webapp pbskids", copy.read_text())
        self.assertEqual((self.tmp / "system/pbskids.desktop").read_text(), BUILTIN)
        self.assertEqual(self.store.request(r["id"])["status"], "approved")

    def test_approving_answers_covered_requests(self):
        a = self.store.add_request("pbskids", "https://www.youtube.com/")
        b = self.store.add_request("pbskids", "https://m.youtube.com/")
        self.store.decide(a["id"], True)
        self.assertEqual(self.store.request(b["id"])["status"], "approved")

    def test_deny(self):
        r = self.store.add_request("pbskids", "https://example.org/")
        self.store.decide(r["id"], False)
        self.assertEqual(self.store.request(r["id"])["status"], "denied")
        self.assertNotIn("example.org", self.store.app("pbskids")["allow"])
        with self.assertRaises(KeyError):
            self.store.decide(r["id"], True)  # already answered

    def test_domains(self):
        self.store.allow_domain("pbskids", "Example.ORG")
        self.assertIn("example.org", self.store.app("pbskids")["allow"])
        self.store.remove_domain("pbskids", "example.org")
        self.assertNotIn("example.org", self.store.app("pbskids")["allow"])
        with self.assertRaises(ValueError):
            self.store.remove_domain("pbskids", "pbskids.org")  # built in
        for bad in ("*", "a.org;evil.com", "x", "a..org", "http://a.org"):
            with self.assertRaises(ValueError, msg=bad):
                self.store.allow_domain("pbskids", bad)

    def test_add_and_remove_app(self):
        app_id = self.store.add_app("NASA Kids", "https://www.nasa.gov/kids/")
        self.assertEqual(app_id, "parent-nasa-kids")
        app = self.store.app(app_id)
        self.assertEqual(app["allow"], ["nasa.gov"])
        self.assertTrue(app["added_by_parent"])
        with self.assertRaises(ValueError):
            self.store.add_app("NASA Kids", "https://www.nasa.gov/")
        with self.assertRaises(ValueError):
            self.store.add_app("Plain", "http://example.org/")
        self.store.remove_app(app_id)
        self.assertIsNone(self.store.app(app_id))
        with self.assertRaises(ValueError):
            self.store.remove_app("pbskids")


def at(day, clock):
    """A timestamp: day 0 is Wednesday 2026-09-30 (a school day), day 3 is Saturday."""
    h, m = map(int, clock.split(":"))
    return (datetime.datetime(2026, 9, 30, h, m) + datetime.timedelta(days=day)).timestamp()


class ScreenTimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "system").mkdir()
        self.store = parent.Store(self.tmp / "state", self.tmp / "system")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def use(self, start, minutes):
        """Report an unlocked screen every 30 s for `minutes`."""
        for i in range(minutes * 2 + 1):
            status = self.store.heartbeat(True, start + i * 30)
        return status

    def test_no_limits_by_default(self):
        status = self.use(at(0, "10:00"), 10)
        self.assertEqual((status["state"], status["remaining"], status["used"]), ("open", None, 600))

    def test_daily_limit_and_weekend(self):
        self.store.set_limits(30, 60, None, None)
        status = self.use(at(0, "10:00"), 20)
        self.assertEqual((status["state"], status["remaining"]), ("open", 600))
        status = self.use(at(0, "11:00"), 10)
        self.assertEqual((status["state"], status["reason"]), ("locked", "used-up"))
        # Saturday: a new day and the weekend limit.
        status = self.use(at(3, "10:00"), 40)
        self.assertEqual((status["state"], status["remaining"]), ("open", 1200))

    def test_locked_and_asleep_time_isnt_counted(self):
        start = at(0, "10:00")
        self.store.heartbeat(True, start)
        self.store.heartbeat(True, start + 30)            # 30 s used
        self.store.heartbeat(False, start + 60)           # locked since the last report
        self.store.heartbeat(True, start + 600)           # unlocked again
        status = self.store.heartbeat(True, start + 900)  # 5 min gap: the laptop slept
        self.assertEqual(status["used"], 30)

    def test_open_hours(self):
        self.store.set_limits(None, None, "07:00", "20:00")
        self.assertEqual(self.store.screen_time(at(0, "19:50"))["remaining"], 600)
        status = self.store.screen_time(at(0, "20:00"))
        self.assertEqual((status["state"], status["reason"], status["opens"]), ("locked", "closed", "07:00"))
        self.assertEqual(self.store.screen_time(at(0, "06:59"))["state"], "locked")
        self.assertEqual(self.store.screen_time(at(0, "07:00"))["state"], "open")

    def test_limit_and_hours_together(self):
        self.store.set_limits(60, 60, "07:00", "20:00")
        self.assertEqual(self.store.screen_time(at(0, "19:30"))["remaining"], 1800)
        self.assertEqual(self.store.screen_time(at(0, "12:00"))["remaining"], 3600)

    def test_more_time_beats_limits_and_pause_beats_more_time(self):
        self.store.set_limits(0, 0, "07:00", "20:00")
        now = at(0, "21:00")
        self.store.give_time(15, now)
        status = self.store.screen_time(now + 60)
        self.assertEqual((status["state"], status["remaining"]), ("open", 840))
        self.store.give_time(15, now + 60)  # adds on to what's left
        self.assertEqual(self.store.screen_time(now + 120)["remaining"], 1680)
        self.assertEqual(self.store.screen_time(now + 1801)["state"], "locked")
        self.store.give_time(15, now)
        self.store.set_paused(True)
        self.assertEqual(self.store.screen_time(now + 60)["reason"], "paused")
        self.store.set_paused(False)
        self.assertEqual(self.store.screen_time(now + 60)["reason"], "closed")

    def test_kid_asks_for_more_time(self):
        self.store.set_limits(0, 0, None, None)
        r = self.store.add_time_request()
        self.assertEqual(self.store.add_time_request()["id"], r["id"])  # once is enough
        self.store.decide(r["id"], True)
        status = self.store.screen_time()
        self.assertEqual(status["state"], "open")
        self.assertGreater(status["remaining"], 14 * 60)

    def test_limit_validation(self):
        for args in ((-1, None, None, None), (2000, None, None, None), (None, None, "07:00", None),
                     (None, None, "20:00", "07:00"), (None, None, "7am", "20:00")):
            with self.assertRaises(ValueError, msg=args):
                self.store.set_limits(*args)
        with self.assertRaises(ValueError):
            self.store.give_time(0)

    def test_usage_history_is_trimmed(self):
        for day in range(40):
            start = datetime.datetime(2026, 1, 1, 10).timestamp() + day * 86400
            self.store.heartbeat(True, start)
            self.store.heartbeat(True, start + 30)
            self.store.heartbeat(False, start + 60)
        usage = json.loads((self.tmp / "state/usage.json").read_text())
        self.assertEqual(len(usage), parent.USAGE_DAYS)


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "system").mkdir()
        (self.tmp / "system/pbskids.desktop").write_text(BUILTIN)
        parent.Handler.store = parent.Store(self.tmp / "state", self.tmp / "system")
        parent.Handler.store.set_passphrase("purple elephant")
        parent.Handler.sessions = {}
        parent.Handler.failures = {}
        self.server = parent.DualStackServer(("::", 0), parent.Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.tmp)

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read().decode()

    def kid_ask(self, url):
        return self.call("POST", "/api/requests", json.dumps({"app": "pbskids", "url": url}),
                         {"Content-Type": "application/json"})

    def sign_in(self, passphrase="purple elephant"):
        status, headers, _ = self.call("POST", "/login", urlencode({"passphrase": passphrase}),
                                       {"Content-Type": "application/x-www-form-urlencoded"})
        return status, headers.get("Set-Cookie", "").split(";")[0]

    def kid_post(self, path, data):
        status, _, body = self.call("POST", path, json.dumps(data), {"Content-Type": "application/json"})
        return status, json.loads(body)

    def test_kid_can_ask_and_check(self):
        status, _, body = self.kid_ask("https://www.youtube.com/")
        self.assertEqual(status, 201)
        request_id = json.loads(body)["id"]
        status, _, body = self.call("GET", f"/api/requests/{request_id}")
        self.assertEqual(json.loads(body), {"status": "pending"})

    def test_kid_session_and_time_request(self):
        parent.Handler.store.set_limits(0, 0, None, None)
        status, _, body = self.call("POST", "/api/session", json.dumps({"active": True}),
                                    {"Content-Type": "application/json"})
        self.assertEqual((status, json.loads(body)["reason"]), (200, "used-up"))
        status, _, body = self.call("POST", "/api/requests", json.dumps({"kind": "time"}),
                                    {"Content-Type": "application/json"})
        self.assertEqual(status, 201)
        request_id = json.loads(body)["id"]
        _, cookie = self.sign_in()
        _, _, page = self.call("GET", "/", headers={"Cookie": cookie})
        self.assertIn("15 more minutes", page)
        self.assertIn("Today&#x27;s time is used up", page)
        self.call("POST", f"/requests/{request_id}/approve", "",
                  {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie})
        _, _, body = self.call("POST", "/api/session", json.dumps({"active": True}),
                               {"Content-Type": "application/json"})
        self.assertEqual(json.loads(body)["state"], "open")

    def test_parent_sets_screen_time(self):
        _, cookie = self.sign_in()
        form = {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie}
        _, _, page = self.call("POST", "/time/limits",
                               "weekday_minutes=90&weekend_minutes=&opens=07%3A00&closes=20%3A00", form)
        self.assertIn("Saved screen time", page)
        limits = parent.Handler.store.limits()
        self.assertEqual((limits["weekday_minutes"], limits["weekend_minutes"], limits["closes"]),
                         (90, None, "20:00"))
        _, _, page = self.call("POST", "/time/limits", "weekday_minutes=lots", form)
        self.assertIn("minutes must be a number", page)
        self.call("POST", "/time/lock", "", form)
        self.assertEqual(parent.Handler.store.screen_time()["reason"], "paused")
        self.call("POST", "/time/unlock", "", form)
        self.call("POST", "/time/give", "minutes=30", form)
        self.assertGreater(parent.Handler.store.screen_time()["remaining"], 29 * 60)

    def test_kid_api_is_json_only(self):
        status, _, _ = self.call("POST", "/api/requests", "app=pbskids&url=https://a.org/",
                                 {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 415)

    def test_wrong_passphrase_and_no_session_are_refused(self):
        status, cookie = self.sign_in("wrong")
        self.assertEqual((status, cookie), (401, ""))
        status, headers, _ = self.call("POST", "/apps/pbskids/allow", "domain=example.org",
                                       {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual((status, headers.get("Location")), (303, "/"))
        self.assertNotIn("example.org", parent.Handler.store.app("pbskids")["allow"])
        _, _, page = self.call("GET", "/")
        self.assertIn("Parent passphrase", page)

    def test_sign_in_forgives_a_trailing_space(self):
        self.assertEqual(self.sign_in("purple elephant ")[0], 303)

    def test_too_many_wrong_passphrases_pause_sign_in(self):
        for _ in range(parent.LOGIN_TRIES):
            self.assertEqual(self.sign_in("guess")[0], 401)
        self.assertEqual(self.sign_in()[0], 429)  # even the right one, for a minute
        parent.Handler.failures.clear()
        self.assertEqual(self.sign_in()[0], 303)

    def test_changing_the_passphrase_signs_out_other_phones(self):
        _, phone = self.sign_in()
        _, laptop = self.sign_in()
        form = {"Content-Type": "application/x-www-form-urlencoded", "Cookie": phone}
        _, _, page = self.call("POST", "/passphrase", urlencode(
            {"current": "wrong", "new": "green giraffe", "repeat": "green giraffe"}), form)
        self.assertIn("current passphrase isn&#x27;t right", page)
        _, _, page = self.call("POST", "/passphrase", urlencode(
            {"current": "purple elephant", "new": "green giraffe", "repeat": "green giraffe"}), form)
        self.assertIn("Changed the passphrase", page)
        _, _, page = self.call("GET", "/", headers={"Cookie": phone})
        self.assertIn("Screen time", page)  # still signed in
        _, _, page = self.call("GET", "/", headers={"Cookie": laptop})
        self.assertIn("Sign in", page)
        self.assertEqual(self.sign_in("purple elephant")[0], 401)
        self.assertEqual(self.sign_in("green giraffe")[0], 303)

    def test_first_boot_setup(self):
        parent.Handler.store.passphrase_file.unlink()
        status, body = self.kid_post("/api/session", {"active": False})
        self.assertEqual(body["state"], "setup")
        _, _, page = self.call("GET", "/")
        self.assertIn("set up yet", page)
        self.assertEqual(self.sign_in("")[0], 200)  # nothing to sign in with yet
        self.assertEqual(self.kid_post("/api/setup", {"passphrase": "short"})[0], 400)
        self.assertEqual(self.kid_post("/api/setup", {"passphrase": "blue whale song"})[0], 201)
        self.assertEqual(self.kid_post("/api/session", {"active": False})[1]["state"], "open")
        # Once it's set, the kid side can't change it.
        self.assertEqual(self.kid_post("/api/setup", {"passphrase": "kid's own choice"})[0], 409)
        self.assertEqual(self.sign_in("blue whale song")[0], 303)

    def test_parent_approves_from_the_dashboard(self):
        _, _, body = self.kid_ask("https://www.youtube.com/<script>alert(1)</script>")
        request_id = json.loads(body)["id"]
        status, cookie = self.sign_in()
        self.assertEqual(status, 303)
        _, headers, page = self.call("GET", "/", headers={"Cookie": cookie})
        self.assertIn("wants to open", page)
        self.assertNotIn("<script>alert(1)</script>", page)  # escaped
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.call("POST", f"/requests/{request_id}/approve", "domain=youtube.com",
                  {"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie})
        _, _, body = self.call("GET", f"/api/requests/{request_id}")
        self.assertEqual(json.loads(body)["status"], "approved")
        self.assertIn("youtube.com", parent.Handler.store.app("pbskids")["allow"])


class PassphraseTest(unittest.TestCase):
    def test_passphrase_is_hashed_and_private(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            store = parent.Store(tmp, tmp)
            self.assertIsNone(store.passphrase())
            store.set_passphrase("purple elephant")
            path = tmp / "parent-passphrase"
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertNotIn("purple", path.read_text())
            self.assertTrue(store.check_passphrase("purple elephant"))
            self.assertIsNone(store.check_passphrase("Purple elephant"))
            with self.assertRaises(FileExistsError):
                store.set_passphrase("another one", first=True)
            with self.assertRaises(ValueError):
                store.set_passphrase("  short  ")
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
