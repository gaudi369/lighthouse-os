#!/usr/bin/env bash
# Open one kid app in a normal window on your desktop, to click around in.
# Blocked navigations are printed here as they happen.
#
#   scripts/app.sh pbskids                   a web app at its start page
#   scripts/app.sh pbskids@https://pbskids.org/games
#   scripts/app.sh chromium [url]            Chromium with the kid policy and an address bar
#   scripts/app.sh lockscreen [reason]       the screen time lock screen (used-up, closed, paused)
#   scripts/app.sh tuxpaint                  any other desktop entry
set -euo pipefail

source "$(dirname "$0")/rootfs-mounts.sh"

if [ $# -eq 0 ]; then
  echo "Usage: mise run app -- <app>[@url] | chromium [url] | lockscreen [used-up|closed|paused]"
  echo "Web apps:"
  grep -l '^X-Lighthouse-Url=' "${root}"/rootfs/usr/share/applications/*.desktop \
    | xargs -n1 basename | sed 's/\.desktop$//; s/^/  /'
  exit 1
fi

arg="$1"; app="${arg%%@*}"
if [ "${app}" = chromium ]; then
  cmd=(chromium-browser --no-first-run "${2:-https://pbskids.org/}")
elif [ "${app}" = lockscreen ]; then
  cmd=(lighthouse-timekeeper --preview "${2:-used-up}")
elif grep -q '^X-Lighthouse-Url=' "${root}/rootfs/usr/share/applications/${app}.desktop" 2>/dev/null; then
  cmd=(lighthouse-webapp "${app}")
  [ "${arg}" != "${app}" ] && cmd+=(--url "${arg#*@}")
else
  cmd=(gtk-launch "${app}")
fi

STATE_NAME=app-session exec "$(dirname "$0")/run-on-host.sh" "${cmd[@]}"
