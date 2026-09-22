FROM quay.io/fedora/fedora-bootc:41

# 1. Install base Wayland compositor, display manager, graphics, audio, and tools
RUN dnf5 -y --setopt=fastestmirror=1 --setopt=timeout=60 install \
    mesa-dri-drivers \
    pipewire \
    wireplumber \
    greetd \
    niri \
    chromium \
    tuxpaint \
    gcompris-qt \
    foot \
    xwayland-run \
    flatpak \
    openssh-server \
    && dnf5 clean all

# 2. Layer in configurations and desktop shortcuts
COPY rootfs/ /

# 3. Enable systemd services
RUN systemctl enable greetd.service && \
    systemctl enable sshd.service && \
    bootc container lint
