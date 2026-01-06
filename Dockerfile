# Stage 1: Build React Frontend
FROM node:20-alpine AS build-frontend
WORKDIR /app
COPY configurator/package.json configurator/package-lock.json ./
RUN npm install --legacy-peer-deps
COPY configurator/ ./
RUN npm run build

# Stage 2: Final Image
FROM python:3.11-alpine
WORKDIR /app

# Install dependencies
RUN apk add --no-cache g++ gcc musl-dev python3-dev \
    sdl2-dev sdl2_image-dev sdl2_ttf-dev linux-headers \
    xvfb x11vnc fluxbox bash git coreutils nginx \
    && pip3 install --no-cache-dir flask flask-cors requests pyyaml gunicorn esphome websockify

# Install noVNC
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /app/novnc && \
    git clone --depth 1 https://github.com/novnc/websockify /app/novnc/utils/websockify && \
    ln -s /app/novnc/vnc.html /app/novnc/index.html

# Copy built frontend
COPY --from=build-frontend /app/dist /app/configurator/dist

# Copy VNC startup script
COPY docker_debug/vnc_startup.sh /app/
RUN chmod +x /app/vnc_startup.sh

# Copy Python backend and scripts
COPY configurator/generate_tiles_api.py /app/configurator/
COPY configurator/server.py /app/configurator/
COPY configurator/run_emulator.sh /app/configurator/
RUN chmod +x /app/configurator/run_emulator.sh

# Copy ESPHome files (needed for schema and scripts)
COPY esphome /app/esphome

# Copy nginx config
COPY docker_debug/nginx.conf /etc/nginx/nginx.conf

# Expose port for Ingress (nginx listens on PORT, proxies to internal services)
ENV PORT=8080
EXPOSE $PORT

# Set entrypoint to VNC startup script
ENTRYPOINT ["/app/vnc_startup.sh"]

# Set SDL to use X11
ENV SDL_VIDEODRIVER=x11

# Start nginx (foreground) and gunicorn (background)
CMD sh -c "gunicorn -w 1 --threads 4 -b 127.0.0.1:8099 --chdir /app/configurator server:app & nginx -g 'daemon off;'"
