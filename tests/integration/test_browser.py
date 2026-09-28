"""Browser integration tests: lighthouse-webapp and the Chromium policy.

Runs inside the devtools image under a headless sway (see scripts/test.sh).
A local web server answers for allowed.test, sub.allowed.test, blocked.test and
later.test (all mapped to 127.0.0.1), so no internet access is needed. Test
pages trigger their own navigations with JavaScript; the result is read from
window titles (via swaymsg) and from lighthouse-webapp's "blocked ..." log lines.
A real lighthouse-parent runs alongside for the ask-a-grown-up flow.
"""

import http.client
import http.server
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest

PORT = 8000
ALLOWED = f"http://allowed.test:{PORT}"
BLOCKED = f"http://blocked.test:{PORT}"
APP_ID = "lighthouse-test"
ASK_TITLE = "Ask a grown-up · Lighthouse Test"
TMP = tempfile.mkdtemp()
PARENT_PORT = 8080


def page(title, script=""):
    return f"<!doctype html><title>{title}</title><body>{title}<script>{script}</script>"


def go(url):
    return f"setTimeout(() => location.href = {json.dumps(url)}, 300)"


# path -> (status, headers, body); {host} in a body is replaced per request.
ROUTES = {
    "/home": (200, {}, page("HOME")),
    "/target": (200, {}, page("TARGET {host}")),
    "/nav-blocked": (200, {}, page("NAV-BLOCKED", go(f"{BLOCKED}/target"))),
    "/nav-later": (200, {}, page("NAV-LATER", go(f"http://later.test:{PORT}/target"))),
    "/nav-subdomain": (200, {}, page("NAV-SUB", go(f"http://sub.allowed.test:{PORT}/target"))),
    "/nav-lookalike": (200, {}, page("NAV-LOOKALIKE", go(f"http://allowed.test.blocked.test:{PORT}/target"))),
    "/nav-file": (200, {}, page("NAV-FILE", go("file:///etc/passwd"))),
    "/redirect": (302, {"Location": f"{BLOCKED}/target"}, ""),
    "/iframe": (200, {}, page("IFRAME") + f'<iframe src="{BLOCKED}/target"></iframe>'),
    "/download": (200, {}, page("DOWNLOAD", go("/file.bin"))),
    "/file.bin": (200, {"Content-Type": "application/octet-stream",
                        "Content-Disposition": "attachment; filename=file.bin"}, "data"),
}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        status, headers, body = ROUTES.get(self.path, (404, {}, page("NOT FOUND")))
        body = body.replace("{host}", self.headers.get("Host", "").split(":")[0]).encode()
        self.send_response(status)
        headers = {"Content-Type": "text/html; charset=utf-8", **headers}
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def window_titles():
    tree = json.loads(subprocess.run(["swaymsg", "-t", "get_tree"], capture_output=True,
                                     text=True, check=True).stdout)
    titles, nodes = [], [tree]
    while nodes:
        n = nodes.pop()
        if n.get("pid"):
            titles.append(n.get("name") or "")
        nodes += n.get("nodes", []) + n.get("floating_nodes", [])
    return titles


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return False


class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

        system, state = os.path.join(TMP, "system"), os.path.join(TMP, "state")
        os.makedirs(system)
        with open(os.path.join(system, f"{APP_ID}.desktop"), "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Lighthouse Test\n"
                    f"Exec=lighthouse-webapp {APP_ID}\n"
                    f"X-Lighthouse-Url={ALLOWED}/home\nX-Lighthouse-Allow=allowed.test;\n")
        os.environ["LIGHTHOUSE_APP_DIRS"] = f"{state}/apps/applications:{system}"

        env = {**os.environ, "LIGHTHOUSE_STATE_DIR": state, "LIGHTHOUSE_SYSTEM_APPS": system,
               "LIGHTHOUSE_PARENT_PORT": str(PARENT_PORT)}
        cls.parent = subprocess.Popen(["lighthouse-parent", "serve"], env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        token_file = os.path.join(state, "parent-token")
        wait_for(lambda: os.path.exists(token_file), timeout=10)
        with open(token_file) as f:
            cls.token = f.read().strip()

    @classmethod
    def tearDownClass(cls):
        cls.parent.terminate()
        cls.parent.wait(timeout=10)
        cls.server.shutdown()
        cls.server.server_close()

    def run_app(self, path, until, settle=2):
        """Start the web app at ALLOWED+path, wait for `until(titles)`, return (titles, log)."""
        with tempfile.TemporaryFile(mode="w+") as log:
            proc = subprocess.Popen(["lighthouse-webapp", APP_ID, "--url", ALLOWED + path],
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                ok = wait_for(lambda: until(window_titles()))
                time.sleep(settle)  # give a navigation we expect to be blocked time to happen
                titles = window_titles()
            finally:
                proc.terminate()
                proc.wait(timeout=10)
                wait_for(lambda: not window_titles(), timeout=5)
            log.seek(0)
            output = log.read()
        self.assertTrue(ok, f"window never matched; titles={titles}\n{output}")
        return titles, output

    def assert_blocked(self, path, blocked_url):
        """A blocked page swaps in the kid's "Ask a grown-up" page."""
        titles, log = self.run_app(path, lambda t: ASK_TITLE in t)
        self.assertIn(f"blocked {blocked_url}", log)
        self.assertNotIn("TARGET blocked.test", titles)

    def parent_allows(self, domain):
        """Sign in to lighthouse-parent as a grown-up and allow a domain for the test app."""
        def post(path, body, cookie=""):
            conn = http.client.HTTPConnection("127.0.0.1", PARENT_PORT, timeout=5)
            conn.request("POST", path, body, {"Content-Type": "application/x-www-form-urlencoded",
                                              "Cookie": cookie})
            r = conn.getresponse()
            r.read()
            return r
        cookie = post("/login", f"token={self.token}").getheader("Set-Cookie").split(";")[0]
        self.assertEqual(post(f"/apps/{APP_ID}/allow", f"domain={domain}", cookie).status, 200)

    # --- lighthouse-webapp ---------------------------------------------------

    def test_start_page_loads(self):
        self.run_app("/home", lambda t: "HOME" in t, settle=0)

    def test_navigation_to_other_site_is_blocked(self):
        self.assert_blocked("/nav-blocked", f"{BLOCKED}/target")

    def test_redirect_to_other_site_is_blocked(self):
        titles, log = self.run_app("/redirect", lambda t: bool(t))
        self.assertIn(f"blocked {BLOCKED}/target", log)
        self.assertNotIn("TARGET blocked.test", titles)

    def test_iframe_from_other_site_is_blocked(self):
        _, log = self.run_app("/iframe", lambda t: "IFRAME" in t)
        self.assertIn(f"blocked {BLOCKED}/target", log)

    def test_lookalike_domain_is_blocked(self):
        self.assert_blocked("/nav-lookalike", f"http://allowed.test.blocked.test:{PORT}/target")

    def test_file_urls_are_blocked(self):
        titles, _ = self.run_app("/nav-file", lambda t: "NAV-FILE" in t)
        self.assertIn("NAV-FILE", titles)

    def test_blocked_page_opens_once_a_grown_up_allows_it(self):
        with tempfile.TemporaryFile(mode="w+") as log:
            proc = subprocess.Popen(["lighthouse-webapp", APP_ID, "--url", ALLOWED + "/nav-later"],
                                    stdout=log, stderr=subprocess.STDOUT)
            try:
                asked = wait_for(lambda: ASK_TITLE in window_titles())
                if os.environ.get("SHOTS_DIR"):  # scripts/test.sh saves what the kid saw
                    time.sleep(1)
                    subprocess.run(["grim", os.path.join(os.environ["SHOTS_DIR"], "ask-a-grown-up.png")])
                self.parent_allows("later.test")
                opened = wait_for(lambda: "TARGET later.test" in window_titles(), timeout=15)
                titles = window_titles()
            finally:
                proc.terminate()
                proc.wait(timeout=10)
                wait_for(lambda: not window_titles(), timeout=5)
        self.assertTrue(asked, "the ask page never appeared")
        self.assertTrue(opened, f"the page didn't open after approval; titles={titles}")

    def test_subdomain_is_allowed(self):
        self.run_app("/nav-subdomain", lambda t: "TARGET sub.allowed.test" in t, settle=0)

    def test_downloads_are_blocked(self):
        _, log = self.run_app("/download", lambda t: "DOWNLOAD" in t)
        self.assertIn("blocked download", log)

    def test_disallowed_start_url_is_refused(self):
        result = subprocess.run(["lighthouse-webapp", APP_ID, "--url", f"{BLOCKED}/target"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not allowed", result.stderr)

    # --- Chromium managed policy (the real one from rootfs/) -----------------

    def test_chromium_policy_blocks_unlisted_sites(self):
        with tempfile.TemporaryDirectory() as profile:
            proc = subprocess.Popen(
                ["chromium-browser", "--no-first-run", f"--user-data-dir={profile}",
                 f"--app={BLOCKED}/target"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                opened = wait_for(lambda: bool(window_titles()), timeout=30)
                time.sleep(3)
                titles = window_titles()
            finally:
                proc.terminate()
                proc.wait(timeout=15)
        self.assertTrue(opened, "Chromium never opened a window")
        self.assertNotIn("TARGET blocked.test", titles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
