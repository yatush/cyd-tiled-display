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

# Copy fix script — run at container startup (not at build time)
# The ESP32 PlatformIO toolchain is NOT pre-downloaded in this image.
# It is downloaded on first container start into the cyd_pio_packages named volume,
# which persists it across container/image rebuilds. This keeps the image ~1-2GB
# instead of ~7GB.
COPY docker_debug/fix_pio_wrappers.sh /app/
RUN chmod +x /app/fix_pio_wrappers.sh

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
