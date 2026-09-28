#!/usr/bin/env bash
# Screenshot every theme (headless) with a web app open, and combine them into
# build/shots/themes.png.
#
#   scripts/theme-gallery.sh [app]        default app: scratch
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
app="${1:-scratch}"
out="${root}/build/shots/themes"
rm -rf "${out}" && mkdir -p "${out}"

for theme in "${root}"/themes/*.toml; do
  id="$(basename "${theme}" .toml)"
  echo "==> ${id}"
  LIGHTHOUSE_THEME="${id}" SHOT_WAIT="${SHOT_WAIT:-12}" "${root}/scripts/shot.sh" "${app}" >/dev/null 2>&1
  mv "$(ls -t "${root}"/build/shots/*-"${app}".png | head -1)" "${out}/${id}.png"
done

if command -v magick >/dev/null; then
  magick montage "${out}"/*.png -tile 2x -geometry 683x384+10+10 -pointsize 22 -label '%t' \
    "${root}/build/shots/themes.png"
  echo "Gallery: build/shots/themes.png"
else
  echo "Screenshots in build/shots/themes/ (install ImageMagick for a combined gallery)"
fi
