#!/usr/bin/env bash
# Boot the installer ISO in a UEFI VM with an empty disk, as a laptop would.
# The installer wipes that disk, installs, and reboots into Lighthouse.
# Run again later to boot the installed disk without the installer.
set -euo pipefail

iso="${BUILD_DIR}/iso/bootiso/install.iso"
state="${BUILD_DIR}/iso-test"
disk="${state}/laptop.qcow2"
vars="${state}/OVMF_VARS.fd"

[ -f "${iso}" ] || { echo "No installer ISO; run 'mise run iso' first."; exit 1; }

code=""
for dir in /usr/share/edk2/x64 /usr/share/edk2/ovmf /usr/share/OVMF; do
  for name in OVMF_CODE.4m.fd OVMF_CODE.fd; do
    [ -f "${dir}/${name}" ] && { code="${dir}/${name}"; break 2; }
  done
done
[ -n "${code}" ] || { echo "UEFI firmware (OVMF) not found; install edk2-ovmf."; exit 1; }

mkdir -p "${state}"
if [ ! -f "${disk}" ]; then
  echo "==> Creating an empty 32G laptop disk and fresh UEFI variables..."
  qemu-img create -q -f qcow2 "${disk}" 32G
  cp "${code/CODE/VARS}" "${vars}"
  boot=(-cdrom "${iso}" -boot once=d)
else
  echo "==> Booting the installed disk (delete ${state} to reinstall)..."
  boot=()
fi

exec qemu-system-x86_64 \
  -enable-kvm \
  -machine q35 \
  -m 4G \
  -smp 4 \
  -cpu host \
  -drive if=pflash,format=raw,readonly=on,file="${code}" \
  -drive if=pflash,format=raw,file="${vars}" \
  -drive file="${disk}",format=qcow2,if=virtio \
  "${boot[@]}" \
  -device virtio-vga-gl \
  -display sdl,gl=on \
  -device virtio-tablet-pci \
  -netdev user,id=net0,hostfwd=tcp::${SSH_PORT}-:22 \
  -device virtio-net-pci,netdev=net0
