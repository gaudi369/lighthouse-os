#!/usr/bin/env bash
# Run the kid session (niri + noctalia + apps) from the kid-os image as a
# window inside the host's Wayland compositor. No VM, no disk build.
#
# rootfs/ config is bind-mounted over the image, so config edits only need
# a restart of this script; package changes need `mise run build`.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
image="localhost/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}"

: "${WAYLAND_DISPLAY:?dev-session must be run from a Wayland session}"
host_socket="${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}"

# Fresh home and runtime dir each run, owned by the invoking user.
state="${root}/build/dev-session"
rm -rf "${state}"
mkdir -p -m 0700 "${state}/home" "${state}/run"

mounts=()
for path in etc/niri etc/lighthouse etc/chromium/policies/managed; do
  mounts+=(-v "${root}/rootfs/${path}:/${path}:ro")
done
# Desktop entries are mounted file-by-file so the image's own entries stay visible.
mounts+=(-v "${root}/rootfs/usr/bin/lighthouse-webapp:/usr/bin/lighthouse-webapp:ro")
for f in "${root}"/rootfs/usr/share/applications/*.desktop; do
  mounts+=(-v "${f}:/usr/share/applications/$(basename "$f"):ro")
done

exec podman run --rm $([ -t 0 ] && echo -it) \
  --userns=keep-id \
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
  -e LANG=en_US.UTF-8 \
  "${mounts[@]}" \
  "${image}" \
  dbus-run-session -- niri "$@"
