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
    gcompat cmake ninja ccache && \
    # Create transparent ccache symlinks so every gcc/g++ invocation is cached
    mkdir -p /usr/local/lib/ccache && \
    ln -sf /usr/bin/ccache /usr/local/lib/ccache/gcc && \
    ln -sf /usr/bin/ccache /usr/local/lib/ccache/g++ && \
    ln -sf /usr/bin/ccache /usr/local/lib/ccache/cc && \
    ln -sf /usr/bin/ccache /usr/local/lib/ccache/c++ && \
    # Remove large sanitizer/profiling static libraries — not needed for ESP32 compilation
    find /usr/lib /usr/local/lib -maxdepth 2 \( \
        -name 'libtsan.a' -o -name 'libasan.a' -o -name 'libubsan.a' -o \
        -name 'liblsan.a' -o -name 'libhwasan.a' -o -name 'libgcc_s_sjlj.a' -o \
        -name 'libstdc++fs.a' \) -delete 2>/dev/null; true

# We install esphome and all Python deps together to minimize layers
# Build deps (rust/cargo) are only needed during pip install of cryptography etc.
# Pass --build-arg ESPHOME_VERSION=X.Y.Z to pin a specific version; omit to install latest.
ARG ESPHOME_VERSION
RUN apk add --no-cache --virtual .build-deps rust cargo openssl-dev libffi-dev jpeg-dev zlib-dev \
    && pip3 install --no-cache-dir esphome${ESPHOME_VERSION:+==$ESPHOME_VERSION} aioesphomeapi flask flask-cors requests pyyaml gunicorn websockify \
    && apk del .build-deps \
    # We must keep some runtime libraries that were previously pulled by dev packages
    && apk add --no-cache openssl libffi jpeg zlib \
    # Remove Python bytecode caches to save space
    && find /usr/lib/python3* /usr/local/lib/python3* -name '__pycache__' -exec rm -rf {} + 2>/dev/null; true

# Install noVNC
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /app/novnc && \
    git clone --depth 1 https://github.com/novnc/websockify /app/novnc/utils/websockify && \
    ln -s /app/novnc/vnc_lite.html /app/novnc/index.html

# ─── Toolchain setup scripts ────────────────────────────────────────────────
# fix_pio_wrappers.sh: patches PlatformIO's glibc Rust binaries for Alpine/musl.
# toolchain_setup.py: at container start, downloads the pre-built toolchain
#   tarball from GitHub Releases (fast) or falls back to a local compile.
COPY docker_debug/fix_pio_wrappers.sh  /app/
COPY docker_debug/toolchain_setup.py   /app/
COPY docker_debug/prepare_precache.py  /app/
RUN chmod +x /app/fix_pio_wrappers.sh

# Write the ESPHome version and GitHub repository into the image so
# toolchain_setup.py knows which release tarball to download at runtime.
ARG GITHUB_REPO=yatush/cyd-tiled-display
RUN python3 -c "from importlib.metadata import version; print(version('esphome'))" > /app/esphome_version.txt && \
    echo "${GITHUB_REPO}" > /app/github_repo.txt && \
    echo "ESPHome version baked into image: $(cat /app/esphome_version.txt)"

# ─── Optional: pre-bake toolchain at image build time (local dev only) ───────
# Default: BAKE_TOOLCHAIN=0 — toolchain is downloaded at container start.
# Set BAKE_TOOLCHAIN=1 via:  docker build --build-arg BAKE_TOOLCHAIN=1 ...
# This is used by update_and_run.sh --bake for fully-offline local dev.
ARG BAKE_TOOLCHAIN=0
RUN if [ "$BAKE_TOOLCHAIN" = "1" ]; then \
      echo "Pre-baking PlatformIO toolchain into image (BAKE_TOOLCHAIN=1)..." && \
      apk add --no-cache ca-certificates && update-ca-certificates && \
      mkdir -p /tmp/esp32_setup && \
      printf 'esphome:\n  name: prebake\nesp32:\n  board: esp32dev\n  framework:\n    type: esp-idf\n' \
          > /tmp/esp32_setup/dummy.yaml && \
      cd /tmp/esp32_setup && \
      CMAKE_BUILD_PARALLEL_LEVEL=2 timeout 900s esphome compile dummy.yaml || true && \
      cd / && rm -rf /tmp/esp32_setup && \
      /app/fix_pio_wrappers.sh || true && \
      PIO_CMAKE=$(find /root/.platformio/packages -path '*/tool-cmake/bin/cmake' 2>/dev/null | head -1) && \
      [ -n "$PIO_CMAKE" ] && mv "$PIO_CMAKE" "${PIO_CMAKE}.orig" && \
        printf '#!/bin/sh\nexec /usr/bin/cmake "$@"\n' > "$PIO_CMAKE" && chmod +x "$PIO_CMAKE" || true && \
      PIO_NINJA=$(find /root/.platformio/packages -path '*/tool-ninja/ninja' 2>/dev/null | head -1) && \
      [ -n "$PIO_NINJA" ] && mv "$PIO_NINJA" "${PIO_NINJA}.orig" && \
        printf '#!/bin/sh\nexec /usr/bin/ninja "$@"\n' > "$PIO_NINJA" && chmod +x "$PIO_NINJA" || true && \
      find /root/.platformio -name '*.orig' -delete 2>/dev/null || true && \
      ESPHOME_VER=$(cat /app/esphome_version.txt) && \
      echo "$ESPHOME_VER" > /root/.platformio/.cyd_esphome_version && \
      touch /root/.platformio/.cyd_setup_done && \
      echo "Toolchain pre-bake complete."; \
    else \
      echo "Skipping toolchain pre-bake (BAKE_TOOLCHAIN=0). Will download at container start."; \
    fi

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
