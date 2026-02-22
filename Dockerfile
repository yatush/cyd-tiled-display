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

# Install dependencies
# gcompat provides glibc compatibility layer needed by PlatformIO's prebuilt binaries (cmake, ninja, toolchains)
RUN apk add --no-cache g++ gcc musl-dev python3-dev \
    sdl2-dev sdl2_image-dev sdl2_ttf-dev linux-headers \
    xvfb x11vnc fluxbox bash git coreutils nginx procps net-tools \
    gcompat \
    && pip3 install --no-cache-dir flask flask-cors requests pyyaml gunicorn esphome websockify aioesphomeapi

# Install noVNC
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /app/novnc && \
    git clone --depth 1 https://github.com/novnc/websockify /app/novnc/utils/websockify && \
    ln -s /app/novnc/vnc_lite.html /app/novnc/index.html

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
RUN cd /app/esphome && esphome compile lib/emulator.yaml || true

# Pre-download ESP32 toolchain (needed for USB flash compilation)
# A minimal ESP-IDF config triggers PlatformIO to install all required packages
# (platform-espressif32, toolchain-xtensa-esp-elf, framework-espidf, etc.)
# The compile itself will fail (Rust wrappers) but packages are cached.
RUN mkdir -p /tmp/esp32_setup && \
    printf 'esphome:\n  name: dummy\nesp32:\n  board: esp32dev\n  framework:\n    type: esp-idf\n' \
    > /tmp/esp32_setup/dummy.yaml && \
    cd /tmp/esp32_setup && esphome compile dummy.yaml 2>&1 || true && \
    rm -rf /tmp/esp32_setup

# Fix PlatformIO's Rust wrapper binaries for Alpine/musl compatibility
# The xtensa toolchain ships Rust-compiled wrappers that crash on musl;
# this replaces them with equivalent shell scripts.
COPY docker_debug/fix_pio_wrappers.sh /app/
RUN chmod +x /app/fix_pio_wrappers.sh && /app/fix_pio_wrappers.sh

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
CMD ["sh", "-c", "gunicorn -w 1 --threads 4 --timeout 300 -b 127.0.0.1:8099 --chdir /app/configurator --access-logfile - --error-logfile - server:app & nginx -c /tmp/nginx.conf -g 'daemon off;'"]
