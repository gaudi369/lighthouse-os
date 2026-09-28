# Sourced by the dev scripts. Sets $root and fills the rootfs_mounts array with
# podman flags that overlay this repo's rootfs/ config onto the kid-os image,
# so config edits take effect without rebuilding.
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rootfs_mounts=()
for path in etc/niri etc/lighthouse etc/chromium/policies/managed; do
  rootfs_mounts+=(-v "${root}/rootfs/${path}:/${path}:ro")
done
for f in "${root}"/rootfs/usr/bin/lighthouse-*; do
  rootfs_mounts+=(-v "${f}:/usr/bin/$(basename "$f"):ro")
done
rootfs_mounts+=(-v "${root}/rootfs/usr/share/lighthouse:/usr/share/lighthouse:ro")
# Stands in for the file lighthouse-hardware.service writes at boot.
rootfs_mounts+=(-v "${root}/rootfs/usr/share/lighthouse/niri-hardware.kdl:/run/lighthouse/niri-hardware.kdl:ro")

# LIGHTHOUSE_THEME=<id> previews a theme without changing the repo's default.
if [ -n "${LIGHTHOUSE_THEME:-}" ]; then
  theme_dir="${root}/rootfs/usr/share/lighthouse/themes/${LIGHTHOUSE_THEME}"
  [ -d "${theme_dir}" ] || { echo "No theme '${LIGHTHOUSE_THEME}'" >&2; exit 1; }
  for name in theme.json palette.json niri.kdl; do
    rootfs_mounts+=(-v "${theme_dir}/${name}:/etc/lighthouse/theme/${name}:ro")
  done
  rootfs_mounts+=(-v "${theme_dir}/noctalia.toml:/etc/lighthouse/noctalia/theme.toml:ro")
fi
# Desktop entries are mounted file-by-file so the image's own entries stay visible.
for f in "${root}"/rootfs/usr/share/applications/*.desktop; do
  rootfs_mounts+=(-v "${f}:/usr/share/applications/$(basename "$f"):ro")
done
