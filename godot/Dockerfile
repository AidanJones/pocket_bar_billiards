# Godot 4.3, headless, for the desk bar billiards viewer and physics tests.
#
# Adapted from the Skiagraph project's Godot image, which already solved the
# awkward parts: Godot 4.x ships one Linux binary that switches to a null
# display driver with --headless, so there is no separate server build, and
# its config/cache want a writable HOME whatever UID docker picks.
#
#   base (default) — headless runs and the physics test, ~250 MB
#   vnc            — x11vnc + noVNC, so you can watch and play it in a browser
#   web            — adds the Web export templates (~1 GB); build on demand
FROM debian:bookworm-slim AS base

ARG GODOT_VERSION=4.3
ARG GODOT_BUILD=stable

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl unzip \
        libx11-6 libxcursor1 libxinerama1 libxi6 libxrandr2 libxrender1 \
        libgl1 libglu1-mesa libasound2 libpulse0 libudev1 libdbus-1-3 \
        libfontconfig1 xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/godot.zip \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-${GODOT_BUILD}/Godot_v${GODOT_VERSION}-${GODOT_BUILD}_linux.x86_64.zip" \
    && unzip -q /tmp/godot.zip -d /tmp/godot_extracted \
    && mv /tmp/godot_extracted/Godot_v${GODOT_VERSION}-${GODOT_BUILD}_linux.x86_64 /usr/local/bin/godot \
    && chmod +x /usr/local/bin/godot \
    && rm -rf /tmp/godot.zip /tmp/godot_extracted

ENV HOME=/tmp/godot_home
RUN mkdir -p "$HOME" && chmod 777 "$HOME"

WORKDIR /project
ENTRYPOINT ["godot"]
CMD ["--headless", "--version"]

# ---------------------------------------------------------------- vnc ----
FROM base AS vnc
RUN apt-get update && apt-get install -y --no-install-recommends \
        x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*
COPY docker/vnc_entrypoint.sh /usr/local/bin/vnc_entrypoint.sh
RUN chmod +x /usr/local/bin/vnc_entrypoint.sh
ENTRYPOINT ["/usr/local/bin/vnc_entrypoint.sh"]
CMD []

# ---------------------------------------------------------------- web ----
FROM base AS web
ARG GODOT_VERSION=4.3
ARG GODOT_BUILD=stable
RUN mkdir -p /tmp/templates \
    && curl -fsSL -o /tmp/templates.tpz \
        "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-${GODOT_BUILD}/Godot_v${GODOT_VERSION}-${GODOT_BUILD}_export_templates.tpz" \
    && unzip -q /tmp/templates.tpz -d /tmp/templates \
    && mkdir -p "$HOME/.local/share/godot/export_templates/${GODOT_VERSION}.${GODOT_BUILD}" \
    && cp /tmp/templates/templates/web_*.zip \
        "$HOME/.local/share/godot/export_templates/${GODOT_VERSION}.${GODOT_BUILD}/" \
    && chmod -R a+rwX "$HOME/.local" \
    && rm -rf /tmp/templates.tpz /tmp/templates
