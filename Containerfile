FROM quay.io/fedora/fedora-bootc:44

# 1. Session, shell, graphics, audio, fonts, and kid apps.
#    niri recommends a terminal (alacritty), a launcher that runs anything
#    (fuzzel), a lock screen and a bar; the kid must get none of them.
#    tests/test_image.py checks that no terminal is installed.
RUN dnf5 -y --setopt=timeout=60 install \
    --exclude=alacritty,fuzzel,swaylock,waybar \
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
    google-noto-color-emoji-fonts \
    flatpak \
    openssh-server \
    desktop-file-utils \
    dbus-daemon \
    && dnf5 clean all

# 2. Runtimes: lighthouse-webapp (Blink via QtWebEngine) and the GTK theme picker
RUN dnf5 -y --setopt=timeout=60 install \
    python3-pyside6 \
    python3-gobject \
    gtk4 \
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

# 5. Hide launchers the kid should not see (general browser, shell internals).
#    Chromium also stops handling web links; lighthouse-open-url.desktop does.
RUN for app in chromium-browser dev.noctalia.Noctalia; do \
      desktop-file-edit --set-key=NoDisplay --set-value=true /usr/share/applications/${app}.desktop; \
    done && \
    desktop-file-edit --remove-key=MimeType /usr/share/applications/chromium-browser.desktop && \
    update-desktop-database /usr/share/applications

# 6. App defaults: Tux Paint fills the screen at native resolution
RUN printf '\n# Lighthouse\nfullscreen=yes\nnative=yes\n' >> /etc/tuxpaint/tuxpaint.conf

# 7. Enable systemd services
RUN systemctl enable greetd.service && \
    systemctl enable sshd.service && \
    systemctl enable tuned.service tuned-ppd.service && \
    systemctl enable lighthouse-hardware.service lighthouse-parent.service && \
    bootc container lint
