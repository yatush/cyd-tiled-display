# Stage 1: Build React Frontend
FROM --platform=$BUILDPLATFORM node:20-alpine AS build-frontend
WORKDIR /app
COPY configurator/package.json configurator/package-lock.json ./
RUN npm install --legacy-peer-deps
COPY configurator/ ./
RUN npm run build

# Stage 2: Final Image
FROM python:3.11-alpine
WORKDIR /app

# Install system dependencies
# gcompat provides glibc compatibility layer needed by PlatformIO's prebuilt binaries
# cmake and ninja are installed natively (musl-compatible) to replace PlatformIO's
# glibc binaries which hang on Alpine during "Reading CMake configuration..."
RUN apk add --no-cache g++ gcc musl-dev python3-dev \
    sdl2-dev sdl2_image-dev sdl2_ttf-dev linux-headers \
    xvfb x11vnc fluxbox bash git coreutils nginx procps net-tools \
    gcompat cmake ninja

# We install esphome first so we can download toolchains
RUN apk add --no-cache --virtual .build-deps rust cargo openssl-dev libffi-dev jpeg-dev zlib-dev \
    && pip3 install --no-cache-dir esphome aioesphomeapi \
    && apk del .build-deps \
    # We must keep some runtime libraries that were previously pulled by dev packages
    && apk add --no-cache openssl libffi jpeg zlib

# Install noVNC
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /app/novnc && \
    git clone --depth 1 https://github.com/novnc/websockify /app/novnc/utils/websockify && \
    ln -s /app/novnc/vnc_lite.html /app/novnc/index.html

# Copy fix script early — needed inside the toolchain pre-download step below
COPY docker_debug/fix_pio_wrappers.sh /app/
RUN chmod +x /app/fix_pio_wrappers.sh

# Pre-download ESP32 toolchain and fix wrappers in one layer.
#
# Phase 1 (timeout 300s): trigger ESPHome/PlatformIO to download all packages.
#   All packages are downloaded BEFORE cmake starts, so we abort as soon as
#   the first cmake failure occurs. We do NOT retry — that's Phase 2's job.
#   The compile is expected to fail (Rust wrappers/cmake not yet fixed) — that's fine.
#
# Phase 2: immediately replace the broken PlatformIO binaries:
#   - Rust wrapper ELFs in the xtensa toolchain  → shell scripts via fix_pio_wrappers.sh
#   - PlatformIO's glibc cmake (hangs on musl)   → wrapper calling system cmake
#   - PlatformIO's glibc ninja                   → wrapper calling system ninja
#
# Runtime compilations (USB flash) will use the fixed binaries from this point on.
RUN mkdir -p /tmp/esp32_setup && \
    printf 'esphome:\n  name: dummy\nesp32:\n  board: esp32dev\n  framework:\n    type: esp-idf\n' \
    > /tmp/esp32_setup/dummy.yaml && \
    cd /tmp/esp32_setup && \
    echo "--- Phase 1: downloading packages (compile expected to fail) ---" && \
    (timeout 300s esphome compile dummy.yaml 2>&1 || true) && \
    echo "--- Phase 2: fixing wrappers ---" && \
    /app/fix_pio_wrappers.sh && \
    PIO_CMAKE=$(find /root/.platformio/packages -path '*/tool-cmake/bin/cmake' 2>/dev/null | head -1) && \
    if [ -n "$PIO_CMAKE" ]; then \
        echo "Replacing PlatformIO cmake at $PIO_CMAKE with system cmake"; \
        mv "$PIO_CMAKE" "${PIO_CMAKE}.orig"; \
        printf '#!/bin/sh\nexec /usr/bin/cmake "$@"\n' > "$PIO_CMAKE"; \
        chmod +x "$PIO_CMAKE"; \
    else \
        echo "WARNING: PlatformIO cmake not found"; \
    fi && \
    PIO_NINJA=$(find /root/.platformio/packages -path '*/tool-ninja/ninja' 2>/dev/null | head -1) && \
    if [ -n "$PIO_NINJA" ]; then \
        echo "Replacing PlatformIO ninja at $PIO_NINJA with system ninja"; \
        mv "$PIO_NINJA" "${PIO_NINJA}.orig"; \
        printf '#!/bin/sh\nexec /usr/bin/ninja "$@"\n' > "$PIO_NINJA"; \
        chmod +x "$PIO_NINJA"; \
    else \
        echo "PlatformIO ninja not found; skipping"; \
    fi && \
    rm -rf /tmp/esp32_setup

# Install remaining Python dependencies (done here to benefit from toolchain caching)
# If these change, we don't have to re-download the gigabyte-sized toolchains
RUN pip3 install --no-cache-dir flask flask-cors requests pyyaml gunicorn websockify

# Copy built frontend
COPY --from=build-frontend /app/dist /app/configurator/dist

# Copy VNC startup script
COPY docker_debug/vnc_startup.sh /app/
RUN chmod +x /app/vnc_startup.sh

# Copy Python backend and scripts
COPY configurator/generate_tiles_api.py /app/configurator/
COPY configurator/server.py /app/configurator/
COPY configurator/api_proxy.py /app/configurator/
COPY configurator/run_emulator.sh /app/configurator/
COPY configurator/run_session.sh /app/configurator/
RUN chmod +x /app/configurator/run_emulator.sh /app/configurator/run_session.sh

# Copy ESPHome files (needed for schema and scripts)
COPY esphome /app/esphome

# Pre-compile the emulator to speed up session starts (populates PlatformIO cache)
# We use || true because it might need a display for full run, but compile should work.
# CMAKE_BUILD_PARALLEL_LEVEL=2 limits parallel compilation jobs to avoid OOM in
# memory-constrained build environments.
RUN cd /app/esphome && CMAKE_BUILD_PARALLEL_LEVEL=2 esphome compile lib/emulator.yaml || true

# Copy nginx config
COPY docker_debug/nginx.conf /etc/nginx/nginx.conf

# Ensure nginx directories exist and have proper permissions
RUN mkdir -p /run/nginx /var/lib/nginx/tmp /var/log/nginx && \
    chmod -R 777 /var/lib/nginx /var/log/nginx /run/nginx

# Expose port for Ingress (nginx listens on PORT, proxies to internal services)
ENV PORT=8080
EXPOSE $PORT

# Set entrypoint to VNC startup script
ENTRYPOINT ["/app/vnc_startup.sh"]

# Set SDL to use X11
ENV SDL_VIDEODRIVER=x11

# Start gunicorn and nginx
# We use -b 127.0.0.1:8099 because nginx proxies to it
# Nginx uses the config generated in vnc_startup.sh
CMD ["sh", "-c", "gunicorn -w 1 --threads 4 --timeout 300 -b 127.0.0.1:8099 --chdir /app/configurator --error-logfile - server:app & nginx -c /tmp/nginx.conf -g 'daemon off;'"]
