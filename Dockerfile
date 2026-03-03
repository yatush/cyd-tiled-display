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
    gcompat cmake ninja && \
    # Remove large sanitizer/profiling static libraries — not needed for ESP32 compilation
    find /usr/lib /usr/local/lib -maxdepth 2 \( \
        -name 'libtsan.a' -o -name 'libasan.a' -o -name 'libubsan.a' -o \
        -name 'liblsan.a' -o -name 'libhwasan.a' -o -name 'libgcc_s_sjlj.a' -o \
        -name 'libstdc++fs.a' \) -delete 2>/dev/null; true

# We install esphome and all Python deps together to minimize layers
# Build deps (rust/cargo) are only needed during pip install of cryptography etc.
RUN apk add --no-cache --virtual .build-deps rust cargo openssl-dev libffi-dev jpeg-dev zlib-dev \
    && pip3 install --no-cache-dir esphome aioesphomeapi flask flask-cors requests pyyaml gunicorn websockify \
    && apk del .build-deps \
    # We must keep some runtime libraries that were previously pulled by dev packages
    && apk add --no-cache openssl libffi jpeg zlib \
    # Remove Python bytecode caches to save space
    && find /usr/lib/python3* /usr/local/lib/python3* -name '__pycache__' -exec rm -rf {} + 2>/dev/null; true

# Install noVNC
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /app/novnc && \
    git clone --depth 1 https://github.com/novnc/websockify /app/novnc/utils/websockify && \
    ln -s /app/novnc/vnc_lite.html /app/novnc/index.html

# Copy fix script — also invoked during image build (pre-bake step below).
# The ESP32 PlatformIO toolchain is pre-baked into the image at build time.
# This runs once on GitHub Actions (fast NVMe + network) so the RPi4 (slow SD
# card) never has to download or extract the toolchain at runtime.
# The .cyd_setup_done marker is written here so vnc_startup.sh skips the
# background first-time setup block entirely.
COPY docker_debug/fix_pio_wrappers.sh /app/
RUN chmod +x /app/fix_pio_wrappers.sh

# ---------------------------------------------------------------------------
# Pre-bake PlatformIO / ESP-IDF toolchain.
# esphome compile drives the full package + tool download.  On arm64/musl the
# PlatformIO-bundled cmake wrapper (a glibc Rust binary) will hang once the
# downloads finish, so we use a 900 s timeout: downloads complete in the first
# few minutes, the timeout fires during cmake configuration, and we continue.
# fix_pio_wrappers.sh and the cmake/ninja replacements below then make
# subsequent real compiles work correctly.
# ---------------------------------------------------------------------------
RUN apk add --no-cache ca-certificates && update-ca-certificates && \
    mkdir -p /root/.platformio/dist && \
    mkdir -p /tmp/esp32_setup && \
    printf 'esphome:\n  name: prebake\nesp32:\n  board: esp32dev\n  framework:\n    type: esp-idf\n' \
        > /tmp/esp32_setup/dummy.yaml && \
    cd /tmp/esp32_setup && \
    CMAKE_BUILD_PARALLEL_LEVEL=2 timeout 900s esphome compile dummy.yaml || true && \
    cd / && rm -rf /tmp/esp32_setup && \
    # Patch Rust/glibc wrapper binaries with Alpine-compatible shell wrappers. \
    /app/fix_pio_wrappers.sh || true && \
    # Replace PlatformIO's cmake binary with the system (musl) cmake wrapper. \
    PIO_CMAKE=$(find /root/.platformio/packages -path '*/tool-cmake/bin/cmake' 2>/dev/null | head -1) && \
    if [ -n "$PIO_CMAKE" ]; then \
        mv "$PIO_CMAKE" "${PIO_CMAKE}.orig" && \
        printf '#!/bin/sh\nexec /usr/bin/cmake "$@"\n' > "$PIO_CMAKE" && \
        chmod +x "$PIO_CMAKE"; \
    fi && \
    # Replace PlatformIO's ninja binary with the system (musl) ninja wrapper. \
    PIO_NINJA=$(find /root/.platformio/packages -path '*/tool-ninja/ninja' 2>/dev/null | head -1) && \
    if [ -n "$PIO_NINJA" ]; then \
        mv "$PIO_NINJA" "${PIO_NINJA}.orig" && \
        printf '#!/bin/sh\nexec /usr/bin/ninja "$@"\n' > "$PIO_NINJA" && \
        chmod +x "$PIO_NINJA"; \
    fi && \
    find /root/.platformio -name '*.orig' -delete 2>/dev/null || true && \
    # Mark setup done so vnc_startup.sh skips the background download phase. \
    touch /root/.platformio/.cyd_setup_done

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

# Note: emulator pre-compilation is done on first container start (see vnc_startup.sh)

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
