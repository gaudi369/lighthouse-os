FROM quay.io/fedora/fedora-bootc:44

# 1. Session, shell, graphics, audio, fonts, and kid apps
RUN dnf5 -y --setopt=timeout=60 install \
    mesa-dri-drivers \
    pipewire \
    wireplumber \
    greetd \
    niri \
    noctalia \
    xdg-desktop-portal-gnome \
    xdg-desktop-portal-gtk \
    chromium \
    tuxpaint \
    gcompris-qt \
    glibc-langpack-en \
    google-noto-sans-fonts \
    google-noto-emoji-fonts \
    flatpak \
    openssh-server \
    desktop-file-utils \
    dbus-daemon \
    && dnf5 clean all

# 2. Runtime for lighthouse-webapp (web sites as apps)
RUN dnf5 -y --setopt=timeout=60 install \
    python3-gobject \
    gtk4 \
    webkitgtk6.0 \
    && dnf5 clean all

# 3. Laptop hardware: Wi-Fi, audio firmware, power profiles, backlight
RUN dnf5 -y --setopt=timeout=60 install \
    NetworkManager-wifi \
    iwlwifi-mvm-firmware \
    iwlwifi-dvm-firmware \
    alsa-sof-firmware \
    tuned-ppd \
    brightnessctl \
    && dnf5 clean all

# 4. Layer in configurations and desktop shortcuts
COPY rootfs/ /

# 5. Hide launchers the kid should not see (general browser, shell internals)
RUN for app in chromium-browser dev.noctalia.Noctalia; do \
      desktop-file-edit --set-key=NoDisplay --set-value=true /usr/share/applications/${app}.desktop; \
    done

# 6. App defaults: Tux Paint fills the screen at native resolution
RUN printf '\n# Lighthouse\nfullscreen=yes\nnative=yes\n' >> /etc/tuxpaint/tuxpaint.conf

# 7. Enable systemd services
RUN systemctl enable greetd.service && \
    systemctl enable sshd.service && \
    systemctl enable tuned.service tuned-ppd.service && \
    bootc container lint
