#!/usr/bin/env bash
# Package the kid-os container image with bootc-image-builder.
#
#   scripts/image-builder.sh <type> <config-template> <output-dir>
#
# type: qcow2 (VM disk) or anaconda-iso (unattended laptop installer).
# The template's @ADMIN_SSH_KEY@ and @TIMEZONE@ are filled in; the dev SSH key
# is generated on first use. Needs sudo: the builder runs as a privileged
# container against root's image store.
set -euo pipefail

type="$1" template="$2" out="$3"
image="localhost/${IMAGE_NAME:-kid-os}:${IMAGE_TAG:-dev}"
key="${SSH_KEY:?SSH_KEY must be set}"

# Ask for the sudo password once, and keep it fresh for the whole build (the
# builder alone takes longer than sudo's default 5-minute timeout).
sudo -v
while sleep 60; do sudo -n true 2>/dev/null || exit; done &
keepalive=$!
trap 'kill "${keepalive}" 2>/dev/null' EXIT

mkdir -p "${out}" "$(dirname "${key}")"
if [ ! -f "${key}" ]; then
  echo "==> Generating dev SSH key for the admin account..."
  ssh-keygen -q -t ed25519 -N "" -C "lighthouse-dev" -f "${key}"
fi

timezone="$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)"
sed -e "s|@ADMIN_SSH_KEY@|$(cat "${key}.pub")|" \
    -e "s|@TIMEZONE@|${timezone}|" \
    "${template}" > "${out}/config.toml"

echo "==> Transferring ${image} to root podman store..."
podman save "${image}" | sudo podman load

echo "==> Building ${type}..."
sudo podman run \
  --rm \
  -it \
  --privileged \
  --pull=newer \
  --security-opt label=type:unconfined_t \
  -v "${out}/config.toml:/config.toml:ro" \
  -v "${out}:/output" \
  -v /var/lib/containers/storage:/var/lib/containers/storage \
  quay.io/centos-bootc/bootc-image-builder:latest \
  --type "${type}" \
  --target-arch x86_64 \
  --rootfs btrfs \
  --config /config.toml \
  "${image}"

echo "==> Setting permissions on ${out}..."
sudo chown -R "${USER}:${USER}" "${out}"
