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
| Parent service | `lighthouse-parent` on port 8080: kid requests in, parent approvals out, screen time; runs as its own `lighthouse` user |
| Screen time | `lighthouse-timekeeper` in the kid's session reports to `lighthouse-parent` every 30 s and locks the session (Wayland session lock, via gtk4-layer-shell) when time is up |
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

Each built-in web app is one desktop entry in `rootfs/usr/share/applications/`:

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
When a page is blocked, the kid sees "This page isn't in PBS Kids yet" with
**Ask a grown-up** and **Go back**. Asking sends the request to
`lighthouse-parent`; the page opens by itself as soon as a grown-up allows
it, or says "not this time" if they don't. These pages live on a local
`lighthouse://` scheme that web pages can't link to. Pop-ups open in the
same window. Downloads, camera/mic/location prompts,
the context menu and developer tools are off. Each app has its own storage
(`~/.local/share/lighthouse/blink/<id>`) and its own window id.

Apps a parent adds or changes are written to
`/var/lib/lighthouse/apps/applications/`, which `lighthouse-webapp` and the
launcher read before `/usr/share/applications`. The kid's home directory is
never read for app entries, so the kid can't widen an allowlist.

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

### For parents

Open `http://<computer>:8080` from a phone or laptop on the same network
(`http://localhost:8080` for the VM) and sign in with the parent code from
`sudo lighthouse-parent token`. The page shows:

- **Asking to visit**: each site the kid asked for, with **Allow** (the
  site's domain, without `www.`) or **Not now**.
- **Web apps**: each app's allowed sites; add more or remove ones you added.
- **Add a web app**: a name and an `https://` address; it appears in the
  launcher straight away.

The kid-side API only accepts JSON from the computer itself; everything
else needs the parent code. It is plain HTTP on the local network for now
(Tailscale comes later), so use it on a network you trust.

- **Screen time**: a daily limit for school days and for weekends, the hours
  the computer is open, **Give 15/30 more minutes**, and **Lock now**. Empty
  boxes mean no limit, which is the default.

#### Screen time

Time counts while the kid's screen is unlocked; time while it's locked or the
laptop is asleep doesn't. Five minutes and one minute before it locks, a
notification says how much is left. Then the session locks with a screen that
says why ("That's all the screen time for today", "The computer is resting"
outside open hours, or "A grown-up paused the computer"), with **Ask a
grown-up for more time** and **Turn off the computer**. Asking shows up under
**Asking to visit** as a request for 15 more minutes; allowing it unlocks the
computer within 30 seconds.

More time always wins over the limit and the open hours, and **Lock now**
wins over everything until you unlock it. If `lighthouse-parent` isn't
running, the computer stays open rather than locking a kid out.

#### What the kid can't change

- **Noctalia's settings.** Its settings window can add plugins (which run
  commands) and bind commands to the bar, and a kid can reach it from the
  control center or the launcher's `/pan`. Noctalia only applies a settings
  change after saving it, and its state and data directories
  (`NOCTALIA_STATE_HOME`, `NOCTALIA_DATA_HOME`) point at a read-only
  directory, so nothing changed there takes effect. The bar's middle and
  right clicks, which open settings and the control center, are turned off.
- **The session menu** offers only Restart and Shut down: Lock and Log out
  would leave a kid with no password at a login prompt.
- **Web links from other programs** (`x-scheme-handler/http(s)`) go to
  `lighthouse-webapp --open`, which opens them in the web app whose allowlist
  covers them, or nowhere. Chromium no longer handles links.
- **niri's config** is pinned with `NIRI_CONFIG`, so a file in the kid's home
  can't replace it. Hot corners (which open the overview) are off, and there
  are no login prompts on other virtual terminals.

Over SSH as `admin` (`mise run ssh` for the VM):

| Command | Does |
|---|---|
| `lighthouse-theme list` | Show themes; `*` marks the current one |
| `sudo lighthouse-theme set <id>` | Switch the theme (works even when locked) |
| `sudo lighthouse-theme lock` / `unlock` | Stop or allow the kid changing it |
| `sudo lighthouse-parent token` | Show the parent code for the web page |

## Development

Most work doesn't need a VM. Pick the fastest loop that covers your change:

| Task | What it does | Use it for |
|---|---|---|
| `mise run build` | Build the container image | Package changes |
| `mise run check` | Validate niri and Noctalia config, Chromium policy, desktop entries and themes; unit tests for the web app allowlist and link routing, `lighthouse-theme` and `lighthouse-parent` (including screen time) | Every change |
| `mise run app -- pbskids` | Open one app in a normal window on your desktop; blocked navigations print in the terminal. Also `pbskids@<url>`, `chromium [url]` (kid policy, with an address bar), `lockscreen [used-up\|closed\|paused]` (the screen time lock screen in a window), or any desktop entry like `tuxpaint` | Trying and exploring apps |
| `mise run parent` | Run the parent service on your computer (state in `build/parent-state`); open http://localhost:8080 with the printed code. `mise run app` in another terminal talks to it, so you can ask and approve end to end | Parent page and the ask flow |
| `mise run dev` | Run the whole kid session in a window on your desktop | Shell, keybindings, layout |
| `mise run test` | Browser tests, headless and offline: allowlist (navigation, redirects, frames, lookalike domains, file URLs, downloads), the ask page, a parent approving through the real service, and the Chromium policy. Saves `build/shots/ask-a-grown-up.png` | Web app, parent or policy changes |
| `mise run shot -- <app>` | Run the kid session headless, open apps, save a screenshot and logs to `build/shots/` | Checking the result without a window |
| `mise run themes` | Screenshot every theme into `build/shots/themes.png` | Theme changes |
| `mise run disk` | Build a bootable qcow2 (needs sudo, ~7 min) | Once, or when accounts or partitions change |
| `mise run launch` / `sandbox` | Boot the VM (`sandbox` discards changes, including updates) | Boot, login, services |
| `mise run vm-update` | Build, push to a local registry (`lighthouse-registry` on 127.0.0.1:5000) and `bootc upgrade` the running VM onto it; reboots it. The first run switches the VM to the registry and downloads every layer; later runs only changed layers | Testing a new image in the VM |
| `mise run vm-sync` | Copy `rootfs/` into the running VM over SSH in seconds; `-- --session` restarts the kid session. `/usr` changes last until the VM reboots; the VM's theme choice is kept | Quick config checks in the VM |
| `mise run ssh` | SSH into the VM as `admin` | Debugging the VM |
| `mise run vm-test` | End-to-end tests in a headless test VM: builds, boots or reuses the test VM, updates it to the build, then acts as the kid (clicks and keys) and the parent (the parent page). Covers the session, the kid's account, terminals, VT logins, Noctalia settings, link routing and screen time. Screenshots in `build/vm-test/shots/`; `-- -k <name>` runs one test | Before calling anything done; after package, service or session changes |
| `mise run vm-start` / `vm-stop` | Boot or shut down the headless test VM (SSH on 2223, parent page on 8081). It has its own copy of `build/qcow2/disk.qcow2` (`-- --fresh` makes a new one), so it can run alongside `mise run launch` | Driving the VM by hand or from Claude |
| `mise run vm-ctl -- <cmd>` | Drive the test VM: `shot [name]`, `click X Y [middle\|right]`, `key super-space`, `type text`, `ssh <command>` | Looking at or poking the VM without a window |
| `mise run iso` | Build the unattended laptop installer (needs sudo) | Installing on real hardware |
| `mise run iso-test` | Install from the ISO onto an empty disk in a UEFI VM, then boot it | Testing the installer |

`app`, `dev`, `shot` and `test` overlay this repo's `rootfs/` config and
tools on the built image, so edits there only need a restart; package
changes need `mise run build`. `LIGHTHOUSE_THEME=<id>` previews a theme in
any of them. `IMAGE_TAG=<tag>` builds or uses a different image tag.

### Which task to use

| You changed… | Check it with |
|---|---|
| Anything | `mise run check` first (seconds) |
| A web app, its allowlist, or `lighthouse-webapp` | `mise run app -- <id>` to click around, then `mise run test` |
| The ask flow or the parent page | `mise run parent` + `mise run app -- <id>`, then `mise run check` and `mise run test` |
| Screen time or the lock screen | `mise run check`; `mise run app -- lockscreen` for the look; `mise run vm-test -- -k time` to see it lock and unlock |
| A theme | `LIGHTHOUSE_THEME=<id> mise run app -- pbskids`, then `mise run themes` |
| niri config, shortcuts, the bar or launcher | `mise run dev` (Mod is Alt there), or `mise run shot` without a window |
| Packages in the `Containerfile` | `mise run build`, then any of the above |
| Services, polkit, greetd, boot-time behaviour | `mise run vm-sync` for a quick try, then `mise run vm-update` |
| Anything before calling it done | `mise run vm-test`, then a look at `build/vm-test/shots/` |
| Accounts, disk layout, `config.toml.in` | `mise run disk` (the only time a full disk build is needed) |
| The installer | `mise run iso` + `mise run iso-test` |

**The installer ISO erases every disk in the machine it boots on, without
asking.** Write it to a USB stick (`build/iso/bootiso/install.iso`) only for
a laptop you intend to wipe. It installs `kid` (autologin) and `admin`
(the dev SSH key in `build/ssh/`), using your current timezone.

## Roadmap

| Goal | Done | Still to do |
|---|---|---|
| 1. One scrolling strip | niri strip, full-width apps, Mod+R half width, shortcuts overlay, no terminal or general browser in the launcher; Noctalia settings, lock and log out out of reach; hot corners off | Keep kids to one workspace (niri still has vertical workspace swipes); check touchpad gestures on real hardware; a friendlier launcher |
| 2. Web sites are apps | `lighthouse-webapp` on Blink with per-app allowlists, storage and window ids; toolbar; "Ask a grown-up" page for blocked links; offline tests | Launcher icons (once the app list is decided); one window per app (opening twice gives two); video playback checked |
| 3. Fully themeable | Eight themes with contrast checks; bar, focus ring, wallpaper, web app toolbars and picker follow the theme; kid picker with parent lock | Theme GTK/Qt apps (Tux Paint, GCompris, dialogs); confirm live switching in the VM |
| 4. Parent control plane | Parent web page: approve or deny the kid's requests, edit each app's allowed sites, add web apps; screen time (daily limits, open hours, more time, lock now) with a kid lock screen that can ask for more; parent code sign-in; commands over SSH | Activity (which apps, for how long; the per-day usage is already kept in `usage.json`); notifying parents of new requests; Tailscale setup flow (and serving only on Tailscale); HTTPS |
| 5. Works out of the box | Immutable bootc image, autologin, no admin rights for the kid, laptop hardware support, unattended installer | Publish the image to a registry and turn on automatic updates; real-hardware testing; a first-boot setup for the parent (admin key, Wi-Fi, Tailscale) instead of the dev SSH key |

Known issues and open questions:

- `mise run vm-test` checks the disk image's accounts, not the installer's.
  The installer's kickstart also creates `kid` without a password (locked),
  but `mise run iso-test` doesn't check that yet.
- The test VM renders through a virtual GPU (niri won't use a software
  renderer), so screenshots come from QEMU's VNC server rather than its
  screendump command. CI runners need KVM and a render node (`/dev/dri`).
- `niri-session` starts through the kid's login shell, which reads
  `~/.bash_profile`. The kid has no way to write files there today, but if an
  app ever gains one, that is a way in.
- Flatpak is installed with no remotes, for later. Nothing the kid can reach
  runs it.

- The disk build used to print `blueprint validation failed ...
  customizations.filesystem` (an `fstype` key the builder doesn't accept);
  `config.toml.in` now sets only a 24 GiB root, so `vm-update` has room for
  two deployments. Not yet confirmed with a disk build.
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
