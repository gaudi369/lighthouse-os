# Lighthouse

A kids' OS (ages 8–12): an immutable Fedora bootc image with niri, Noctalia and
locked-down web apps, plus a parent web page. README.md is the full reference:
architecture, the parent page, the roadmap and known issues. Read the section
you need rather than the whole file.

## Layout

- `Containerfile`: packages and image setup. `rootfs/` is copied over the image as-is.
- `rootfs/usr/bin/lighthouse-*`: the Lighthouse programs (Python, no packaging):
  `webapp` (Blink web apps, allowlists, link routing), `parent` (parent web page
  and kid API on :8080, screen time, the parent passphrase), `timekeeper` (kid
  session: screen time lock and the first-boot setup screen),
  `theme` / `themes` (theme switching and the kid's picker).
- `rootfs/etc/niri/config.kdl`, `rootfs/etc/lighthouse/noctalia/config.toml`: session config.
- `themes/*.toml` → `scripts/gen-themes.py` → generated files under `rootfs/` (committed).
- `tests/`: unit tests (run in the image by `mise run check`); `tests/integration/`:
  headless browser tests (`mise run test`).

## Verifying changes

Use the fastest loop that covers the change (README "Which task to use" has the
full table): `mise run check` always; `mise run app -- <id>` for web apps;
`mise run test` for webapp/parent/policy; `mise run shot` for a headless
screenshot of the session. Before calling something done, `mise run vm-test`
(builds, updates the headless test VM, runs tests/vm; about 5 minutes when the
VM is already up) and look at the screenshots in build/vm-test/shots/.

You can drive the test VM yourself: `mise run vm-start`, then
`scripts/vmctl.py shot NAME` (read the PNG), `click X Y [button]`,
`key super-space`, `type TEXT`, `ssh CMD`. In tests, import `scripts/vmctl.py`.
Programs niri spawns have their stdout discarded; log to syslog to see them in
`journalctl -t <name>`. A solid red screen means the session lock's client
died (niri keeps the screen locked); `WAYLAND_DEBUG=1` shows protocol errors.
`vmctl.py ssh` runs as admin; the tests' `Kid` class runs commands in the kid's
session. Tests sign in with `PASSPHRASE`, set over SSH by `lighthouse-parent passphrase`. When a new kid-facing behaviour can be checked
end to end, add it to tests/vm/test_vm.py.

Package changes need `mise run build` first. Only `disk` and `iso` need sudo
(ask the user to run them). Don't run `mise run iso` output on hardware: it
erases every disk.

## Ground rules

- The kid must never get a general browser, a terminal, admin rights, or a way
  to change system or shell config. Anything a kid can click is a possible
  escape route; check new apps and shell features for settings windows,
  command runners and link handlers.
- Kid-facing text is short, friendly and concrete ("Ask a grown-up"). Parent
  docs are plain and direct.
- Fail open on screen time (a broken service must not lock a kid out), fail
  closed on web access.
- Don't restyle the Noctalia launcher: the owner hasn't picked its look yet.
  No app icons on the desktop background; they go in the launcher only.
