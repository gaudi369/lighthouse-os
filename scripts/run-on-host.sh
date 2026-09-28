#!/usr/bin/env bash
# Run a command from the kid-os image as window(s) on the host's Wayland
# desktop. No VM, no disk build.
#
#   scripts/run-on-host.sh niri              the whole kid session, nested
#   scripts/run-on-host.sh lighthouse-webapp pbskids
#
# rootfs/ config is bind-mounted over the image, so config edits only need a
# restart; package changes need `mise run build`. Each run starts with a fresh
# home directory under build/$STATE_NAME.
set -euo pipefail

source "$(dirname "$0")/rootfs-mounts.sh"
image="localhost/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}"

: "${WAYLAND_DISPLAY:?must be run from a Wayland session}"
host_socket="${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}"

state="${root}/build/${STATE_NAME:-dev-session}"
rm -rf "${state}"
mkdir -p -m 0700 "${state}/home" "${state}/run"

exec podman run --rm $([ -t 0 ] && echo -it) \
  --userns=keep-id \
  --network=host \
  --group-add keep-groups \
  --security-opt label=disable \
  --security-opt seccomp=unconfined \
  --device /dev/dri \
  --shm-size 1g \
  -v "${state}/home:/home/kid" \
  -v "${state}/run:/run/kid" \
  -v "${host_socket}:/run/kid/wayland-host" \
  -e HOME=/home/kid \
  -e XDG_RUNTIME_DIR=/run/kid \
  -e WAYLAND_DISPLAY=wayland-host \
  -e XDG_SESSION_TYPE=wayland \
  -e LANG=en_US.UTF-8 \
  "${rootfs_mounts[@]}" \
  "${image}" \
  dbus-run-session -- "$@"
