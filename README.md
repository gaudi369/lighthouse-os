# Lighthouse

A proof-of-concept operating system for kids aged roughly 8–12, inspired by
Omarchy. It is an immutable Fedora image (bootc) meant to run on budget and
spare laptops, with things working out of the box and parents in control.

## Goals

1. **One scrolling strip.** A single niri workspace that you scroll through,
   with touchpad swipe gestures. No terminal, no run dialog, no general browser.
2. **Web sites are apps.** Each approved site gets its own launcher, icon,
   profile and list of allowed domains. There is no search box.
3. **Fully themeable.** One theme drives the shell, the compositor and the apps.
4. **Parent control plane (optional).** A web app for approving apps and
   requests and setting time limits, reachable remotely through Tailscale
   with a simple setup flow.
5. **Works out of the box.** Immutable image, automatic updates, and the child
   has no admin rights.

Non-goals for now: tablets as the primary target (touchscreen 2-in-1 laptops
are a bonus), and the final choice of offline apps (leaning FOSS, such as
Luanti). The Tux Paint and GCompris packages are placeholders.

## Architecture

| Piece | Choice |
|---|---|
| Base | `quay.io/fedora/fedora-bootc:44`, built from `Containerfile` |
| Session | greetd autologins `kid` into `niri-session` |
| Compositor | niri, config in `rootfs/etc/niri/config.kdl` |
| Shell | Noctalia v5, config in `rootfs/etc/lighthouse/noctalia/` (via `NOCTALIA_CONFIG_HOME`) |
| Web apps | `lighthouse-webapp`, a WebKitGTK shell driven by per-site manifests (experimental), with Chromium `--app` plus managed policy as the fallback |
| Accounts | `kid` has no password and no sudo; `admin` uses an SSH key only |

## Themes

Eight themes inspired by the Hundred Acre Wood of A. A. Milne's books (1926
and 1928, now public domain in the US). The wallpapers are original scenes
drawn from simple shapes; they don't use Disney's character designs.

| Theme | Mode | Scene |
|---|---|---|
| Christopher Robin (default) | light | Sunny hills, an oak tree and a blue balloon |
| Piglet | light | Beech tree with a round door, TRESPASSERS W, haycorns and violets |
| Rabbit | light | Carrot rows behind a picket fence |
| Kanga and Roo | light | Sandy meadow with big hops and little hops |
| Winnie-the-Pooh | dark | HUNNY pots and a beehive on a warm evening |
| Eeyore | dark | Rainy dusk, thistles, a house of sticks and a pink bow |
| Tigger | dark | Bouncy stripes, stars and bouncing trails |
| Owl | dark | Full moon, stars, and Owl on a branch by a lit window |

Each theme is one file, `themes/<id>.toml`, with UI colours and wallpaper
colours. `scripts/gen-themes.py` checks contrast (body text at least 7:1,
other text 4.5:1, focus ring and borders 3:1), then generates the Noctalia
palette, niri focus-ring colours and the SVG wallpaper into `rootfs/`.
`mise run check` fails if a theme misses a contrast target or the generated
files are out of date.

Kids pick their own theme with **Choose a Theme** in the launcher
(`lighthouse-themes`): all eight scenes as big picture buttons. It runs
`pkexec lighthouse-theme set <id>`, which polkit allows for the active local
session without a password (`org.lighthouse.theme.policy`). Under pkexec,
`lighthouse-theme` only allows `set`, and refuses it while locked.

Parents, over SSH: `sudo lighthouse-theme set <id>` switches the theme,
`sudo lighthouse-theme lock` / `unlock` stops or allows the kid changing it,
and `lighthouse-theme list` shows them all. In development,
`LIGHTHOUSE_THEME=<id> mise run dev` (or `shot`, `app`) previews a theme.

## Development

Most work doesn't need a VM. Pick the fastest loop that covers your change:

| Task | What it does | Use it for |
|---|---|---|
| `mise run build` | Build the container image | Package changes |
| `mise run check` | Validate niri config, Chromium policy and desktop entries | Every change |
| `mise run dev` | Run the kid session in a window on your desktop, using this repo's `rootfs/` config | Shell, keybindings, theme, apps |
| `mise run app -- pbskids` | Open one app in a normal window to click around; blocked navigations print in the terminal. Also `pbskids@<url>`, `chromium [url]` (kid policy, with an address bar), or any desktop entry like `tuxpaint` | Exploring what a site needs |
| `mise run test` | Browser tests: web app allowlist (navigation, redirects, frames, lookalike domains, downloads) and the Chromium policy, headless and offline | Web app or policy changes |
| `mise run themes` | Screenshot every theme with a web app open, into `build/shots/themes.png` | Theme changes |
| `mise run shot` | Run the kid session headless and save a screenshot | Checking the result without a window |
| `mise run disk` | Build a bootable qcow2 (needs sudo) | Boot, login, services |
| `mise run launch` / `sandbox` | Boot the VM (`sandbox` discards changes) | Same |
| `mise run ssh` | SSH into the VM as `admin` | Debugging the VM |
| `mise run iso` | Build the unattended laptop installer (needs sudo) | Installing on real hardware |
| `mise run iso-test` | Install from the ISO onto an empty disk in a UEFI VM, then boot it | Testing the installer |

**The installer ISO erases every disk in the machine it boots on, without
asking.** Write it to a USB stick (`build/iso/bootiso/install.iso`) only for
a laptop you intend to wipe. It installs `kid` (autologin) and `admin`
(the dev SSH key in `build/ssh/`), using your current timezone.

Config edits under `rootfs/` only need a restart of `mise run dev`. Package
changes need `mise run build` first.

## Status

- Working in `mise run dev` and `mise run shot`: niri, the Noctalia bar, and the PBS Kids and Scratch web apps.
- Web apps run on `lighthouse-webapp` (WebKitGTK). Each app is one desktop
  entry with `X-Lighthouse-Url`, `X-Lighthouse-Allow`, and optionally
  `X-Lighthouse-Engine=chromium` or `X-Lighthouse-UserAgent`. Blocked
  navigations are logged to stderr, so running an app with `mise run shot`
  shows which domains it needs.
- Known WebKit costs so far: PBS Kids needs a desktop Chrome user agent to
  avoid its mobile "download our app" banner.
- The VM boots into the kid session with autologin; `admin` SSH works.
- Laptop hardware support: Wi-Fi (NetworkManager-wifi, Intel/Realtek/
  MediaTek/Atheros/Broadcom firmware), Intel SOF audio, power profiles
  (tuned-ppd), Bluetooth, backlight. Not yet tested on real hardware.
- Not yet tested: the installer ISO end to end.
- Noctalia runs without its setup wizard, telemetry or keyring prompts.

## History

The first draft was generated by Gemini. Its summary claimed a working
Noctalia/Fuzzel setup that was never installed, and a niri config path that
niri doesn't read. Both were fixed in the Fedora 44 move.
