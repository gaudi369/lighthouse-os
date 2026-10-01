#!/usr/bin/env python3
"""Drive a headless Lighthouse VM: boot it, look at its screen, click, type, and SSH in.

    vmctl.py start [--fresh]     boot the test VM in the background (no window)
    vmctl.py stop                shut it down
    vmctl.py status              is it running, and can SSH reach it?
    vmctl.py shot [name]         save the screen to build/vm-test/shots/<name>.png
    vmctl.py click X Y [button]  click at X,Y in screen pixels (button: left, middle, right)
    vmctl.py key COMBO...        press keys, e.g. ctrl-alt-f2, super-space, ret, tab
    vmctl.py type TEXT           type text (letters, digits, space and simple punctuation)
    vmctl.py ssh CMD...          run a command in the VM as admin

The test VM is separate from `mise run launch`: its own disk (an instant
reflink copy of build/qcow2/disk.qcow2, kept between runs so updates stay
small), its own ports (SSH 2223, parent page 8081) and no window, so both can
run at once. The VM has a virtual GPU (niri won't render in software), so
screenshots come from QEMU's VNC server (which reads the GPU's frames back)
through a small built-in VNC client; input goes through QEMU's QMP socket.
Also importable (tests/vm uses it).
"""

import json
import os
import socket
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_DISK = Path(os.environ.get("DISK_IMAGE", ROOT / "build/qcow2/disk.qcow2"))
DIR = ROOT / "build/vm-test"
DISK = DIR / "disk.qcow2"
QMP = DIR / "qmp.sock"
VNC = DIR / "vnc.sock"
PIDFILE = DIR / "qemu.pid"
SHOTS = DIR / "shots"
SSH_KEY = Path(os.environ.get("SSH_KEY", ROOT / "build/ssh/lighthouse_dev"))
SSH_PORT = int(os.environ.get("VM_TEST_SSH_PORT", "2223"))
WEB_PORT = int(os.environ.get("VM_TEST_WEB_PORT", "8081"))
ABS_MAX = 0x7FFF  # virtio-tablet's coordinate range


# --- QEMU ----------------------------------------------------------------------

def running():
    try:
        pid = int(PIDFILE.read_text())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def start(fresh=False):
    if running():
        print(f"Test VM already running (SSH on {SSH_PORT}).")
        return
    if not BASE_DISK.exists():
        sys.exit(f"No disk at {BASE_DISK}. Run 'mise run disk' first (needs sudo).")
    DIR.mkdir(parents=True, exist_ok=True)
    if fresh or not DISK.exists():
        print(f"==> Copying {BASE_DISK.name} for the test VM")
        DISK.unlink(missing_ok=True)
        subprocess.run(["cp", "--reflink=auto", BASE_DISK, DISK], check=True)
    QMP.unlink(missing_ok=True)
    VNC.unlink(missing_ok=True)
    print(f"==> Booting the test VM headless (SSH localhost:{SSH_PORT}, parent page localhost:{WEB_PORT})")
    subprocess.run([
        "qemu-system-x86_64", "-enable-kvm", "-m", "4G", "-smp", "4", "-cpu", "host",
        "-drive", f"file={DISK},format=qcow2,if=virtio",
        "-device", "virtio-vga-gl", "-display", "egl-headless",
        "-device", "virtio-tablet-pci", "-device", "virtio-keyboard-pci",
        "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{SSH_PORT}-:22,hostfwd=tcp:127.0.0.1:{WEB_PORT}-:8080",
        "-device", "virtio-net-pci,netdev=net0",
        "-qmp", f"unix:{QMP},server=on,wait=off",
        "-vnc", f"unix:{VNC}",
        "-serial", f"file:{DIR / 'serial.log'}",
        "-daemonize", "-pidfile", str(PIDFILE),
    ], check=True)
    wait_ssh()


def stop():
    if not running():
        print("Test VM isn't running.")
        return
    try:
        ssh("sudo systemctl poweroff", check=False, timeout=10)
    except subprocess.TimeoutExpired:
        pass
    for _ in range(60):
        if not running():
            print("Test VM stopped.")
            return
        time.sleep(1)
    qmp("quit")
    print("Test VM stopped (forced).")


class Qmp:
    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(str(QMP))
        self.file = self.sock.makefile("rw")
        self._read()  # greeting
        self.call("qmp_capabilities")

    def _read(self):
        while True:
            msg = json.loads(self.file.readline())
            if "event" not in msg:
                return msg

    def call(self, command, **arguments):
        self.file.write(json.dumps({"execute": command, "arguments": arguments}) + "\n")
        self.file.flush()
        reply = self._read()
        if "error" in reply:
            raise RuntimeError(f"QMP {command}: {reply['error'].get('desc')}")
        return reply.get("return")

    def close(self):
        self.sock.close()


def qmp(command, **arguments):
    q = Qmp()
    try:
        return q.call(command, **arguments)
    finally:
        q.close()


# --- screen and input -----------------------------------------------------------

def _recv(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("VNC connection closed")
        buf += chunk
    return bytes(buf)


def framebuffer():
    """(width, height, RGB bytes) of the guest screen, read over VNC (RFB 3.8, raw encoding)."""
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(20)
    sock.connect(str(VNC))
    try:
        _recv(sock, 12)
        sock.sendall(b"RFB 003.008\n")
        types = _recv(sock, _recv(sock, 1)[0])
        if 1 not in types:
            raise RuntimeError("VNC server wants a password")
        sock.sendall(b"\x01")
        if struct.unpack(">I", _recv(sock, 4))[0] != 0:
            raise RuntimeError("VNC security handshake failed")
        sock.sendall(b"\x01")  # shared
        width, height = struct.unpack(">HH", _recv(sock, 4))
        _recv(sock, 16)
        _recv(sock, struct.unpack(">I", _recv(sock, 4))[0])  # name
        # 32 bpp, little endian, true colour: bytes arrive as B, G, R, padding.
        sock.sendall(struct.pack(">B3xBBBBHHHBBB3x", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0))
        sock.sendall(struct.pack(">BxHi", 2, 1, 0))  # raw encoding only
        sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, width, height))
        pixels = bytearray(width * height * 4)
        while True:
            kind = _recv(sock, 1)[0]
            if kind == 2:  # bell
                continue
            if kind == 3:  # clipboard
                _recv(sock, 3)
                _recv(sock, struct.unpack(">I", _recv(sock, 4))[0])
                continue
            if kind != 0:
                raise RuntimeError(f"unexpected VNC message {kind}")
            _recv(sock, 1)
            for _ in range(struct.unpack(">H", _recv(sock, 2))[0]):
                x, y, w, h, enc = struct.unpack(">HHHHi", _recv(sock, 12))
                if enc != 0:
                    raise RuntimeError(f"unexpected VNC encoding {enc}")
                data = _recv(sock, w * h * 4)
                for row in range(h):
                    start = ((y + row) * width + x) * 4
                    pixels[start:start + w * 4] = data[row * w * 4:(row + 1) * w * 4]
            break
    finally:
        sock.close()
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = pixels[2::4], pixels[1::4], pixels[0::4]
    return width, height, bytes(rgb)


def write_png(path, width, height, rgb):
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def shot(name=None):
    """Save the screen as a PNG; returns its path."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name or time.strftime('%Y%m%d-%H%M%S')}.png"
    write_png(path, *framebuffer())
    return path


def screen_size():
    width, height, _ = framebuffer()
    return width, height


def move(x, y, size=None):
    width, height = size or screen_size()
    qmp("input-send-event", events=[
        {"type": "abs", "data": {"axis": "x", "value": round(x * ABS_MAX / (width - 1))}},
        {"type": "abs", "data": {"axis": "y", "value": round(y * ABS_MAX / (height - 1))}},
    ])


def click(x, y, button="left", size=None):
    move(x, y, size)
    for down in (True, False):
        qmp("input-send-event", events=[{"type": "btn", "data": {"down": down, "button": button}}])
        time.sleep(0.05)


ALIASES = {"super": "meta_l", "win": "meta_l", "enter": "ret", "esc": "esc", "space": "spc",
           "ctrl": "ctrl", "alt": "alt", "shift": "shift", "/": "slash", "-": "minus",
           ".": "dot", ",": "comma", ":": "shift-semicolon", "_": "shift-minus", " ": "spc"}


def key(combo, hold_ms=100):
    """Press a key combination like ctrl-alt-f2, super-space or ret."""
    keys = []
    for part in combo.lower().split("-") if combo not in ("-",) else ["-"]:
        part = ALIASES.get(part, part)
        keys += part.split("-")
    qmp("send-key", keys=[{"type": "qcode", "data": k} for k in keys], **{"hold-time": hold_ms})
    time.sleep(0.05)


def type_text(text):
    for ch in text:
        if ch.isupper():
            key(f"shift-{ch.lower()}")
        else:
            key(ALIASES.get(ch, ch))


# --- SSH ------------------------------------------------------------------------

def ssh_args():
    return ["ssh", "-i", str(SSH_KEY), "-p", str(SSH_PORT), "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5",
            "admin@127.0.0.1"]


def ssh(command, check=True, timeout=120, input=None):
    """Run a shell command in the VM as admin; returns stdout."""
    r = subprocess.run([*ssh_args(), command], capture_output=True, text=True, timeout=timeout, input=input)
    if check and r.returncode != 0:
        raise RuntimeError(f"in the VM: {command}\n{r.stdout}{r.stderr}")
    return r.stdout


def wait_ssh(timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if subprocess.run([*ssh_args(), "true"], capture_output=True, timeout=30).returncode == 0:
            print(f"Test VM is up (SSH on {SSH_PORT}).")
            return
        time.sleep(3)
    sys.exit(f"The test VM didn't answer SSH within {timeout} s; see {DIR / 'serial.log'} and 'vmctl.py shot'.")


def main(argv):
    if not argv:
        sys.exit(__doc__.strip())
    cmd, args = argv[0], argv[1:]
    if cmd == "start":
        start(fresh="--fresh" in args)
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        up = running() and subprocess.run([*ssh_args(), "true"], capture_output=True).returncode == 0
        print(f"running: {running()}, ssh: {up}")
    elif not running():
        sys.exit("The test VM isn't running; start it with 'mise run vm-start'.")
    elif cmd == "shot":
        print(shot(args[0] if args else None))
    elif cmd == "click":
        click(int(args[0]), int(args[1]), args[2] if len(args) > 2 else "left")
    elif cmd == "key":
        for combo in args:
            key(combo)
    elif cmd == "type":
        type_text(" ".join(args))
    elif cmd == "ssh":
        r = subprocess.run([*ssh_args(), " ".join(args)])
        sys.exit(r.returncode)
    else:
        sys.exit(__doc__.strip())


if __name__ == "__main__":
    main(sys.argv[1:])
