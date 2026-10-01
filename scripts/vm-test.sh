#!/usr/bin/env bash
# End-to-end tests in the headless test VM (mise run vm-test).
#
#   scripts/vm-test.sh [unittest args]     e.g. scripts/vm-test.sh -k screen_time
#
# Boots the test VM if it isn't running, updates it to the freshly built image
# (bootc upgrade from the local registry; only changed layers), then runs
# tests/vm. The VM keeps running afterwards so the next run is quick; stop it
# with `mise run vm-stop`. Screenshots: build/vm-test/shots/.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

"${root}/scripts/vmctl.py" start
SSH_PORT="${VM_TEST_SSH_PORT:-2223}" "${root}/scripts/vm.sh" update
rm -f "${root}"/build/vm-test/shots/[0-9]*.png
python3 "${root}/tests/vm/test_vm.py" -v "$@"
echo "Screenshots: build/vm-test/shots/"
