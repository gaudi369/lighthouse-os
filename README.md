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
are a bonus), Raspberry Pi (possible later; see [Roadmap](#roadmap)), and the
final choice of offline apps (leaning FOSS, such as Luanti). Tux Paint and
GCompris are placeholders.

## Architecture

| Piece | Choice |
|---|---|
| Base | `quay.io/fedora/fedora-bootc:44`, built from `Containerfile` |
| Session | greetd autologins `kid` into `niri-session` |
| Compositor | niri, config in `rootfs/etc/niri/config.kdl` |
| Shell | Noctalia v5 (bar and launcher), config in `rootfs/etc/lighthouse/noctalia/` via `NOCTALIA_CONFIG_HOME` |
| Web apps | `lighthouse-webapp`: Chromium's Blink engine through QtWebEngine (PySide6), one desktop entry per site |
| Themes | `themes/*.toml` → `scripts/gen-themes.py` → Noctalia palette, niri colours, wallpaper; `lighthouse-theme` switches |
| Accounts | `kid` has no password and no sudo; `admin` uses an SSH key only |
| Laptops | Wi-Fi, audio firmware, power profiles, Bluetooth, backlight; unattended installer ISO |

`rootfs/` is copied over the image as-is. Generated files under `rootfs/`
(themes) are committed; `mise run check` fails if they are stale.

## Using it

### Keyboard shortcuts

**Mod** is Super on real hardware and in the VM (click into the QEMU window,
or Ctrl+Alt+G, so Hyprland doesn't take Super first), and Alt inside
`mise run dev`.

| Keys | Action |
|---|---|
| Mod+/ | Show these shortcuts |
| Mod+Space | Open an app (Noctalia launcher) |
| Mod+← / Mod+→, Mod+scroll | Go to the app on the left / right |
| Mod+R | Make this app half or full width |
| Mod+Q | Close this app |
| Alt+← / Alt+→ / Alt+Home | Back, forward, home in a web app |

Apps open full width in one horizontal strip; touchpad three-finger swipes
scroll it. Web apps have a toolbar with back, forward and home buttons.

### Web apps

Each web app is one desktop entry in `rootfs/usr/share/applications/`:

```ini
[Desktop Entry]
Name=PBS Kids
Exec=lighthouse-webapp pbskids
Icon=applications-games
Type=Application
StartupWMClass=org.lighthouse.webapp.pbskids
X-Lighthouse-Url=https://pbskids.org/
X-Lighthouse-Allow=pbskids.org;pbs.org;
```

`X-Lighthouse-Allow` lists domains; each includes its subdomains. Every
page load, embedded frame and redirect must stay inside that list, or it is
blocked and logged (`lighthouse-webapp[pbskids]: blocked https://...`).
Pop-ups open in the same window. Downloads, camera/mic/location prompts,
the context menu and developer tools are off. Each app has its own storage
(`~/.local/share/lighthouse/blink/<id>`) and its own window id.

Optional keys: `X-Lighthouse-UserAgent` for sites that sniff the browser,
and `X-Lighthouse-Engine=chromium` to run the full Chromium browser instead.
There, only the machine-wide policy in
`rootfs/etc/chromium/policies/managed/parental_controls.json` applies.

To find the domains a new site needs, run `mise run app -- <id>` and watch
the blocked lines as you click around.

### Themes

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

Each theme is one file, `themes/<id>.toml`, with UI and wallpaper colours.
`scripts/gen-themes.py` checks contrast (body text at least 7:1, other text
4.5:1, focus ring and borders 3:1), then generates the Noctalia palette,
niri focus-ring colours and the SVG wallpaper into `rootfs/`. Web app
toolbars and the theme picker read the current theme too.

Kids pick their own theme with **Choose a Theme** in the launcher
(`lighthouse-themes`). It runs `pkexec lighthouse-theme set <id>`, which
polkit allows for the active local session without a password
(`org.lighthouse.theme.policy`). Under pkexec, `lighthouse-theme` only
allows `set`, and refuses it while a parent has locked the theme.

### Parent commands

Over SSH as `admin` (`mise run ssh` for the VM):

| Command | Does |
|---|---|
| `lighthouse-theme list` | Show themes; `*` marks the current one |
| `sudo lighthouse-theme set <id>` | Switch the theme (works even when locked) |
| `sudo lighthouse-theme lock` / `unlock` | Stop or allow the kid changing it |

## Development

Most work doesn't need a VM. Pick the fastest loop that covers your change:

| Task | What it does | Use it for |
|---|---|---|
| `mise run build` | Build the container image | Package changes |
| `mise run check` | Validate niri config, Chromium policy, desktop entries and themes; unit tests for the web app allowlist and `lighthouse-theme` | Every change |
| `mise run app -- pbskids` | Open one app in a normal window on your desktop; blocked navigations print in the terminal. Also `pbskids@<url>`, `chromium [url]` (kid policy, with an address bar), or any desktop entry like `tuxpaint` | Trying and exploring apps |
| `mise run dev` | Run the whole kid session in a window on your desktop | Shell, keybindings, layout |
| `mise run test` | Browser tests: allowlist (navigation, redirects, frames, lookalike domains, file URLs, downloads) and the Chromium policy, headless and offline | Web app or policy changes |
| `mise run shot -- <app>` | Run the kid session headless, open apps, save a screenshot and logs to `build/shots/` | Checking the result without a window |
| `mise run themes` | Screenshot every theme into `build/shots/themes.png` | Theme changes |
| `mise run disk` | Build a bootable qcow2 (needs sudo) | Boot, login, services |
| `mise run launch` / `sandbox` | Boot the VM (`sandbox` discards changes) | Same |
| `mise run ssh` | SSH into the VM as `admin` | Debugging the VM |
| `mise run iso` | Build the unattended laptop installer (needs sudo) | Installing on real hardware |
| `mise run iso-test` | Install from the ISO onto an empty disk in a UEFI VM, then boot it | Testing the installer |

`app`, `dev`, `shot` and `test` overlay this repo's `rootfs/` config and
tools on the built image, so edits there only need a restart; package
changes need `mise run build`. `LIGHTHOUSE_THEME=<id>` previews a theme in
any of them. `IMAGE_TAG=<tag>` builds or uses a different image tag.

**The installer ISO erases every disk in the machine it boots on, without
asking.** Write it to a USB stick (`build/iso/bootiso/install.iso`) only for
a laptop you intend to wipe. It installs `kid` (autologin) and `admin`
(the dev SSH key in `build/ssh/`), using your current timezone.

## Roadmap

| Goal | Done | Still to do |
|---|---|---|
| 1. One scrolling strip | niri strip, full-width apps, Mod+R half width, shortcuts overlay, no terminal or general browser in the launcher | Keep kids to one workspace (niri still has vertical workspace swipes); check touchpad gestures on real hardware; a friendlier launcher |
| 2. Web sites are apps | `lighthouse-webapp` on Blink with per-app allowlists, storage and window ids; toolbar; offline tests | App icons; one window per app (opening twice gives two); a friendly "ask a grown-up" page for blocked links; video playback checked |
| 3. Fully themeable | Eight themes with contrast checks; bar, focus ring, wallpaper, web app toolbars and picker follow the theme; kid picker with parent lock | Theme GTK/Qt apps (Tux Paint, GCompris, dialogs); confirm live switching in the VM |
| 4. Parent control plane | Parent commands over SSH; key-only admin account | The web app (approve apps and requests, time limits, activity); request queue from the kid side; Tailscale setup flow |
| 5. Works out of the box | Immutable bootc image, autologin, no admin rights for the kid, laptop hardware support, unattended installer | Publish the image to a registry and turn on automatic updates; real-hardware testing; a first-boot setup for the parent (admin key, Wi-Fi, Tailscale) instead of the dev SSH key |

Known issues and open questions:

- The disk build prints `blueprint validation failed ... customizations.filesystem`;
  the disk still builds, but the 10 GiB root size is probably ignored.
- While `bootc-image-builder` runs, its loop-device partitions show up in
  file managers (udisks). A udev rule on the build host
  (`ENV{UDISKS_IGNORE}="1"` for loop devices) would hide them; `mise run clean`
  currently detaches every loop device on the host.
- Raspberry Pi: every package exists for aarch64, but booting needs the Pi
  firmware added to the image. Laptops come first.

## History

The first draft was generated by Gemini. Its summary claimed a working
Noctalia/Fuzzel setup that was never installed, and a niri config path that
niri doesn't read. Both were fixed in the Fedora 44 move. A WebKitGTK version
of `lighthouse-webapp` was replaced with Blink because it rendered PBS Kids
badly.
