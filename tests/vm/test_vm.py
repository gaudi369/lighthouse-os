"""End-to-end tests in the headless test VM: a booted Lighthouse, driven like a kid and a parent.

Run with `mise run vm-test`, which builds the image, boots the test VM
(scripts/vmctl.py), updates it to the new image and runs these. The tests
act as the kid through the screen (clicks and keys over QMP) and the kid's
session (commands run as `kid` with its Wayland and niri sockets), and as the
parent through the parent page on localhost:8081. Screenshots go to
build/vm-test/shots/ so a person can look at what happened.

The tests share one VM and run in order (test_01, test_02, ...), but each
sets up what it needs, so `-k <name>` runs one on its own.
"""

import http.client
import json
import re
import shlex
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import vmctl  # noqa: E402

WEB_PORT = vmctl.WEB_PORT


def wait_for(check, timeout, message, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout} s: {message}")


class Kid:
    """Commands run as the kid, inside the kid's running session."""

    def __init__(self):
        self.uid = vmctl.ssh("id -u kid").strip()
        pid = wait_for(lambda: vmctl.ssh("pgrep -u kid -x noctalia || true").strip(), 120,
                       "the kid's session to start")
        environ = vmctl.ssh(f"sudo cat /proc/{pid.split()[0]}/environ | tr '\\0' '\\n'")
        keep = ("WAYLAND_DISPLAY", "NIRI_SOCKET", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                "NOCTALIA_CONFIG_HOME", "NOCTALIA_STATE_HOME", "NOCTALIA_DATA_HOME", "XDG_DATA_DIRS")
        self.env = dict(line.split("=", 1) for line in environ.splitlines()
                        if line.split("=", 1)[0] in keep)

    def run(self, command, check=True):
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in self.env.items())
        return vmctl.ssh(f"sudo -u kid env {env} sh -c {shlex.quote(command)}", check=check)

    def windows(self):
        return json.loads(self.run("niri msg -j windows"))

    def close_all_windows(self):
        for w in self.windows():
            self.run(f"niri msg action close-window --id {w['id']}")


class Parent:
    """The parent page, signed in with the parent code."""

    def __init__(self):
        token = vmctl.ssh("sudo lighthouse-parent token").strip()
        status, headers, _ = self.call("POST", "/login", {"token": token}, cookie=None)
        assert status == 303, f"sign-in failed ({status})"
        self.cookie = headers["Set-Cookie"].split(";")[0]

    def call(self, method, path, form=None, cookie=""):
        conn = http.client.HTTPConnection("127.0.0.1", WEB_PORT, timeout=10)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie is not None:
            headers["Cookie"] = cookie or self.cookie
        conn.request(method, path, body=urlencode(form or {}), headers=headers)
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read().decode()

    def post(self, path, **form):
        status, _, page = self.call("POST", path, form)
        assert status == 200, f"{path}: {status}"
        return page

    def page(self):
        return self.call("GET", "/")[2]

    def clear_screen_time(self):
        self.post("/time/limits", weekday_minutes="", weekend_minutes="", opens="", closes="")
        self.post("/time/unlock")


class VM(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vmctl.wait_ssh()
        cls.kid = Kid()
        cls.parent = Parent()
        cls.parent.clear_screen_time()
        cls.kid.close_all_windows()
        cls.width, cls.height = vmctl.screen_size()

    @classmethod
    def tearDownClass(cls):
        cls.parent.clear_screen_time()

    def journal(self, since, pattern):
        """lighthouse-timekeeper's log lines since `since` (a timestamp) that match `pattern`."""
        out = vmctl.ssh(f"sudo journalctl -t lighthouse-timekeeper --since @{int(since)} --no-pager -o cat")
        return [line for line in out.splitlines() if re.search(pattern, line)]

    def wait_log(self, since, pattern, timeout=50):
        return wait_for(lambda: self.journal(since, pattern), timeout, f"log line /{pattern}/")

    # --- the system ----------------------------------------------------------

    def test_01_session_is_up(self):
        for name in ("niri", "noctalia"):
            self.assertTrue(vmctl.ssh(f"pgrep -u kid -x {name} || true").strip(), name)
        self.assertTrue(vmctl.ssh("pgrep -u kid -f lighthouse-timekeeper || true").strip())
        vmctl.shot("01-desktop")

    def test_02_kid_account_has_no_password_or_admin(self):
        password = vmctl.ssh("sudo getent shadow kid").split(":")[1]
        self.assertTrue(password.startswith(("!", "*")), "the kid's password should be locked")
        self.assertNotIn("wheel", vmctl.ssh("id -nG kid").split())

    def test_03_no_terminal_installed(self):
        found = vmctl.ssh("for t in alacritty foot kitty xterm gnome-terminal ptyxis konsole; "
                          "do command -v $t; done; true").split()
        self.assertEqual(found, [])

    def test_04_no_login_prompt_on_other_terminals(self):
        nautovts = vmctl.ssh("busctl get-property org.freedesktop.login1 /org/freedesktop/login1 "
                             "org.freedesktop.login1.Manager NAutoVTs")
        self.assertEqual(nautovts.split(), ["u", "0"])
        vmctl.key("ctrl-alt-f2")
        time.sleep(3)
        vmctl.shot("04-ctrl-alt-f2")
        # (The VM's serial console has a getty of its own; only VTs matter here.)
        self.assertEqual(vmctl.ssh("pgrep -a agetty | grep -E ' tty[0-9]' || true").strip(), "")
        vmctl.key("ctrl-alt-f1")
        time.sleep(3)

    # --- Noctalia ------------------------------------------------------------

    def test_05_noctalia_settings_dont_stick(self):
        self.assertEqual(self.kid.env.get("NOCTALIA_STATE_HOME"), "/usr/share/lighthouse/noctalia-readonly")
        before = self.kid.run("noctalia msg theme-mode-get").strip()
        self.kid.run(f"noctalia msg theme-mode-set {'light' if before == 'dark' else 'dark'}", check=False)
        time.sleep(2)
        self.assertEqual(self.kid.run("noctalia msg theme-mode-get").strip(), before)
        self.assertEqual(vmctl.ssh("ls /usr/share/lighthouse/noctalia-readonly/noctalia").split(), ["README"])

    def test_06_bar_clicks_dont_open_settings(self):
        clock = (self.width // 2, 24)
        for button in ("middle", "right", "left"):
            vmctl.click(*clock, button)
            time.sleep(2)
            vmctl.shot(f"06-bar-{button}-click")
            app_ids = [w.get("app_id") for w in self.kid.windows()]
            self.assertNotIn("dev.noctalia.Noctalia", app_ids, f"{button} click opened settings")
            vmctl.key("esc")

    # --- web links -----------------------------------------------------------

    def test_07_links_open_in_their_web_app(self):
        self.kid.run("gio open https://scratch.mit.edu/projects/editor/ >/dev/null 2>&1 &")
        wait_for(lambda: any(w.get("app_id") == "org.lighthouse.webapp.scratch" for w in self.kid.windows()),
                 30, "Scratch to open")
        before = len(self.kid.windows())
        self.kid.run("gio open https://www.youtube.com/ >/dev/null 2>&1 || true")
        time.sleep(8)
        vmctl.shot("07-links")
        self.assertEqual(len(self.kid.windows()), before, "a link no app allows opened a window")
        self.kid.close_all_windows()

    # --- screen time ---------------------------------------------------------

    def test_08_warning_before_time_runs_out(self):
        since = time.time()
        self.parent.post("/time/limits", weekday_minutes="0", weekend_minutes="0", opens="", closes="")
        self.parent.post("/time/give", minutes="3")
        self.wait_log(since, r"warning: 3 minutes")
        time.sleep(1)
        vmctl.shot("08-warning")

    def test_09_time_up_locks_and_asking_unlocks(self):
        since = time.time()
        self.parent.post("/time/limits", weekday_minutes="0", weekend_minutes="0", opens="", closes="")
        self.parent.post("/time/lock")  # ends any extra time from earlier tests
        self.parent.post("/time/unlock")
        self.wait_log(since, r"locking \(used-up\)")
        time.sleep(2)
        vmctl.shot("09-locked")
        self.assertIn("Today&#x27;s time is used up", self.parent.page())

        # The kid can't get past the lock screen by switching apps or opening the launcher.
        vmctl.key("super-space")
        time.sleep(1)
        vmctl.shot("09-locked-after-super-space")

        # The kid asks for more time by mashing keys: the Ask button has focus, and
        # "Turn off the computer" can't get it, so this asks and nothing else.
        for combo in ("tab", "ret", "tab", "ret", "ret"):
            vmctl.key(combo)

        def asked():
            page = self.parent.page()
            return page if "more minutes</strong>" in page else None
        page = wait_for(asked, 20, "the request on the parent page")
        time.sleep(1)
        vmctl.shot("09-asked")
        self.assertTrue(vmctl.running(), "key presses turned the computer off")
        request_id = re.search(r'action="/requests/([0-9a-f]+)/approve"><button>Give', page).group(1)
        since = time.time()
        self.parent.post(f"/requests/{request_id}/approve")
        self.wait_log(since, r"unlocking")
        time.sleep(2)
        vmctl.shot("09-unlocked")

    def test_10_lock_now_and_unlock(self):
        since = time.time()
        self.parent.clear_screen_time()
        self.parent.post("/time/lock")
        self.wait_log(since, r"locking \(paused\)")
        time.sleep(2)
        vmctl.shot("10-paused")
        since = time.time()
        self.parent.post("/time/unlock")
        self.wait_log(since, r"unlocking")


if __name__ == "__main__":
    unittest.main(verbosity=2)
