#!/usr/bin/env bash
# Run the browser integration tests headless, with no internet needed.
#
#   scripts/test.sh [unittest args]    e.g. scripts/test.sh -k redirect
set -euo pipefail

source "$(dirname "$0")/rootfs-mounts.sh"
image="localhost/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}-devtools"

mounts=("${rootfs_mounts[@]}")
[ -e /dev/dri ] && mounts+=(--device /dev/dri)

exec podman run --rm \
  --userns=keep-id \
  --user kid \
  --security-opt label=disable \
  --security-opt seccomp=unconfined \
  --shm-size 1g \
  --add-host allowed.test:127.0.0.1 \
  --add-host sub.allowed.test:127.0.0.1 \
  --add-host blocked.test:127.0.0.1 \
  --add-host allowed.test.blocked.test:127.0.0.1 \
  -v "${root}/tests:/tests:ro" \
  -e HOME=/home/kid \
  -e XDG_RUNTIME_DIR=/run/kid \
  -e LANG=en_US.UTF-8 \
  -e XDG_SESSION_TYPE=wayland \
  -e WLR_BACKENDS=headless \
  -e WLR_LIBINPUT_NO_DEVICES=1 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "${mounts[@]}" \
  "${image}" \
  dbus-run-session -- bash -c '
    printf "output * resolution 1366x768\n" > /tmp/sway.conf
    sway -c /tmp/sway.conf >/tmp/sway.log 2>&1 &
    for _ in $(seq 100); do [ -S "$XDG_RUNTIME_DIR/wayland-1" ] && break; sleep 0.2; done
    export WAYLAND_DISPLAY=wayland-1 SWAYSOCK=$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock)
    cd /tests/integration && python3 -m unittest -v test_browser "$@"
  ' test "$@"
