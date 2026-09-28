#!/usr/bin/env bash
# Change the running VM (mise run launch) without rebuilding its disk.
#
#   scripts/vm.sh update             push the image to a local registry and
#                                    `bootc upgrade` the VM onto it (reboots)
#   scripts/vm.sh sync [--session]   copy rootfs/ into the VM over SSH; /usr
#                                    changes last until the next reboot
#
# update is the real update path laptops will use; sync is for quick config
# checks. Both need the VM running with SSH forwarded on $SSH_PORT.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
image="localhost/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}"
registry_port="${REGISTRY_PORT:-5000}"
registry="lighthouse-registry"
# From inside QEMU's user network, 10.0.2.2 is the host's loopback.
vm_image="10.0.2.2:${registry_port}/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}"

ssh_opts=(-i "${SSH_KEY:?}" -p "${SSH_PORT:?}" -o StrictHostKeyChecking=no
          -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=5)
vm() { ssh "${ssh_opts[@]}" admin@localhost "$@"; }

require_vm() {
  vm true 2>/dev/null || { echo "Can't reach the VM over SSH. Start it with 'mise run launch'."; exit 1; }
}

start_registry() {
  if ! podman container exists "${registry}"; then
    echo "==> Creating local registry on 127.0.0.1:${registry_port}"
    podman run -d --name "${registry}" -p "127.0.0.1:${registry_port}:5000" \
      docker.io/library/registry:2 >/dev/null
  elif [ "$(podman inspect -f '{{.State.Running}}' "${registry}")" != true ]; then
    podman start "${registry}" >/dev/null
  fi
}

cmd_update() {
  require_vm
  start_registry
  echo "==> Pushing ${image}"
  podman push -q --tls-verify=false "${image}" "127.0.0.1:${registry_port}/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}"

  # Dev-only: let the VM pull from the plain-HTTP registry. Never in the image.
  vm "sudo tee /etc/containers/registries.conf.d/50-lighthouse-dev.conf >/dev/null" <<EOF
[[registry]]
location = "10.0.2.2:${registry_port}"
insecure = true
EOF

  booted="$(vm "sudo bootc status --format json" | python3 -c \
    'import json,sys; s=json.load(sys.stdin)["status"]["booted"]; print(((s or {}).get("image") or {}).get("image",{}).get("image",""))')"
  if [ "${booted}" != "${vm_image}" ]; then
    echo "==> Switching the VM to ${vm_image} (first update; downloads every layer once)"
    cmd="sudo bootc switch --apply ${vm_image}"
  else
    echo "==> Upgrading the VM (downloads only changed layers)"
    cmd="sudo bootc upgrade --apply"
  fi
  # --apply reboots the VM when there is something new, which drops SSH.
  vm "${cmd}" || true

  echo "==> Waiting for the VM to come back"
  sleep 5
  for _ in $(seq 60); do vm true 2>/dev/null && break; sleep 3; done
  require_vm
  vm "sudo bootc status --booted" | sed -n '1,12p'
}

cmd_sync() {
  require_vm
  echo "==> Copying rootfs/ into the VM"
  # Keep the VM's current theme choice; those files are runtime state.
  tar -C "${root}/rootfs" -cf - \
      --exclude=./etc/lighthouse/theme --exclude=./etc/lighthouse/noctalia/theme.toml . \
    | vm "sudo bootc usr-overlay >/dev/null 2>&1 || true; sudo tar -C / --no-same-owner --no-overwrite-dir -xf -"
  vm "sudo systemctl daemon-reload && sudo systemctl restart lighthouse-parent"
  if [ "${1:-}" = "--session" ]; then
    echo "==> Restarting the kid session"
    vm "sudo systemctl restart greetd"
  else
    echo "niri reloads its config by itself; web apps pick up changes when reopened."
    echo "Use 'mise run vm-sync -- --session' to restart the kid session."
  fi
  echo "Changes under /usr last until the VM reboots; 'mise run vm-update' makes them permanent."
}

case "${1:-}" in
  update) cmd_update ;;
  sync) shift; cmd_sync "$@" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
