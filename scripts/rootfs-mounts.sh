# Sourced by the dev scripts. Sets $root and fills the rootfs_mounts array with
# podman flags that overlay this repo's rootfs/ config onto the kid-os image,
# so config edits take effect without rebuilding.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rootfs_mounts=()
for path in etc/niri etc/lighthouse etc/chromium/policies/managed; do
  rootfs_mounts+=(-v "${root}/rootfs/${path}:/${path}:ro")
done
rootfs_mounts+=(-v "${root}/rootfs/usr/bin/lighthouse-webapp:/usr/bin/lighthouse-webapp:ro")
# Desktop entries are mounted file-by-file so the image's own entries stay visible.
for f in "${root}"/rootfs/usr/share/applications/*.desktop; do
  rootfs_mounts+=(-v "${f}:/usr/share/applications/$(basename "$f"):ro")
done
