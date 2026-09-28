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

# 3. Layer in configurations and desktop shortcuts
COPY rootfs/ /

# 4. Hide launchers the kid should not see (general browser, shell internals)
RUN for app in chromium-browser dev.noctalia.Noctalia; do \
      desktop-file-edit --set-key=NoDisplay --set-value=true /usr/share/applications/${app}.desktop; \
    done

# 5. Enable systemd services
RUN systemctl enable greetd.service && \
    systemctl enable sshd.service && \
    bootc container lint
