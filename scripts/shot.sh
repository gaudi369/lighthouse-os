#!/usr/bin/env bash
# Run the kid session headless (niri nested in a headless sway), optionally
# launch apps, and save a screenshot. Nothing appears on the host desktop.
#
#   scripts/shot.sh [desktop-id ...]      e.g. scripts/shot.sh pbskids
#
# Env: SHOT_WAIT (seconds to let apps load, default 15), SHOT_SIZE (default 1366x768)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
image="localhost/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}-devtools"
out="${root}/build/shots"
mkdir -p "${out}"
name="$(date +%Y%m%d-%H%M%S)${1:+-$1}.png"

mounts=()
for path in etc/niri etc/lighthouse etc/chromium/policies/managed; do
  mounts+=(-v "${root}/rootfs/${path}:/${path}:ro")
done
for f in "${root}"/rootfs/usr/share/applications/*.desktop; do
  mounts+=(-v "${f}:/usr/share/applications/$(basename "$f"):ro")
done
[ -e /dev/dri ] && mounts+=(--device /dev/dri)

podman run --rm \
  --userns=keep-id \
  --user kid \
  --security-opt label=disable \
  --security-opt seccomp=unconfined \
  --shm-size 1g \
  -v "${out}:/shots" \
  -e XDG_RUNTIME_DIR=/run/kid \
  -e LANG=en_US.UTF-8 \
  -e WLR_BACKENDS=headless \
  -e WLR_LIBINPUT_NO_DEVICES=1 \
  -e SHOT_SIZE="${SHOT_SIZE:-1366x768}" \
  -e SHOT_WAIT="${SHOT_WAIT:-15}" \
  -e SHOT_NAME="${name}" \
  "${mounts[@]}" \
  "${image}" \
  dbus-run-session -- bash -c '
    set -u
    wait_for() { for _ in $(seq 150); do eval "$1" && return 0; sleep 0.2; done; echo "timed out: $1"; tail -20 /tmp/sway.log /tmp/niri.log; exit 1; }
    printf "output * resolution %s\ndefault_border none\n" "$SHOT_SIZE" > /tmp/sway.conf
    sway -c /tmp/sway.conf >/tmp/sway.log 2>&1 &
    wait_for "[ -S $XDG_RUNTIME_DIR/wayland-1 ]"
    WAYLAND_DISPLAY=wayland-1 niri >/tmp/niri.log 2>&1 &
    wait_for "ls $XDG_RUNTIME_DIR/niri.*.sock >/dev/null 2>&1"
    export NIRI_SOCKET=$(ls "$XDG_RUNTIME_DIR"/niri.*.sock)
    sleep 3
    for app in "$@"; do
      niri msg action spawn-sh -- "env | grep -E \"WAYLAND|XDG_SESSION\" > /shots/${SHOT_NAME%.png}.$app.env; gtk-launch $app > /shots/${SHOT_NAME%.png}.$app.log 2>&1"
    done
    sleep "$SHOT_WAIT"
    niri msg windows > "/shots/${SHOT_NAME%.png}.windows.txt"
    WAYLAND_DISPLAY=wayland-1 grim "/shots/$SHOT_NAME"
    sed "s/\x1b\[[0-9;]*m//g" /tmp/niri.log > "/shots/${SHOT_NAME%.png}.niri.log"
    echo "screenshot: build/shots/$SHOT_NAME"
  ' shot "$@"
