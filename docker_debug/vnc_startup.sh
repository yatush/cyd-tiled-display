#!/bin/bash
set -e

echo "Starting VNC environment..."

# Cloud Run support: ensure nginx listens on the correct port if provided
# We create a runtime config to avoid "Resource busy" errors when /etc/nginx/nginx.conf is bind-mounted
echo "Generating runtime nginx configuration..."
if [ -n "$PORT" ]; then
    echo "Updating nginx configuration to listen on port $PORT"
    sed "s/__PORT__/${PORT}/g" /etc/nginx/nginx.conf > /tmp/nginx.conf
else
    echo "PORT environment variable not set, defaulting to 8080"
    sed "s/__PORT__/8080/g" /etc/nginx/nginx.conf > /tmp/nginx.conf
fi

# Ensure necessary directories for nginx and X11
mkdir -p /run/nginx /var/lib/nginx/tmp /var/log/nginx /tmp/.X11-unix
chmod -R 777 /var/lib/nginx /var/log/nginx /run/nginx /tmp/.X11-unix

export DISPLAY=:0

# Clean up stale X11 locks from previous runs (common in containers)
rm -f /tmp/.X0-lock
rm -f /tmp/.X11-unix/X0
# Also kill any leftover Xvfb processes
pkill -9 Xvfb 2>/dev/null || true
sleep 0.5

# Ensure the X11 unix socket directory exists and has correct permissions
rm -rf /tmp/.X11-unix
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# Start Xvfb
echo "Starting Xvfb..."
Xvfb :0 -screen 0 480x320x16 -ac -noreset > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!

# Wait for Xvfb to be ready by checking for the Unix socket
echo "Waiting for Xvfb to initialize on $DISPLAY..."
for i in $(seq 1 15); do
    if [ -S /tmp/.X11-unix/X0 ]; then
        echo "Xvfb socket /tmp/.X11-unix/X0 is ready"
        break
    fi
    # Check if Xvfb process died
    if ! kill -0 $XVFB_PID 2>/dev/null; then
        echo "ERROR: Xvfb process exited prematurely"
        echo "Xvfb log output:"
        cat /tmp/xvfb.log 2>/dev/null || true
        exit 1
    fi
    echo "Waiting for Xvfb socket... ($i/15)"
    sleep 1
done

# Verify Xvfb socket exists
if [ ! -S /tmp/.X11-unix/X0 ]; then
    echo "ERROR: Xvfb failed to create socket /tmp/.X11-unix/X0"
    echo "Xvfb log output:"
    cat /tmp/xvfb.log 2>/dev/null || true
    echo "Contents of /tmp/.X11-unix/:"
    ls -la /tmp/.X11-unix/ 2>/dev/null || true
    kill $XVFB_PID 2>/dev/null
    exit 1
fi

# Verify Xvfb is running
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "ERROR: Xvfb failed to start"
    exit 1
fi
echo "Xvfb started (PID: $XVFB_PID)"

# Start x11vnc
echo "Starting x11vnc on port 5900..."
x11vnc -display :0 -forever -nopw -shared -bg -o /tmp/x11vnc.log
sleep 2

# Verify x11vnc is listening (using a more robust check)
if ! command -v netstat >/dev/null 2>&1 || ! netstat -ln | grep -q ':5900'; then
    # If netstat is missing or doesn't show the port, check if process is still running at least
    if ! pgrep x11vnc >/dev/null; then
        echo "ERROR: x11vnc is not running"
        [ -f /tmp/x11vnc.log ] && cat /tmp/x11vnc.log
        exit 1
    fi
fi
echo "x11vnc started successfully"

# Start websockify instances
echo "Starting websockify on port 6080..."
/app/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 --web /app/novnc 2>&1 &

echo "Starting websockify on port 6081 (for Cloud Run nginx proxy)..."
websockify --web /app/novnc 6081 localhost:5900 2>&1 &

echo "VNC environment ready"

# Test nginx config before proceeding
echo "Testing nginx configuration..."
nginx -t -c /tmp/nginx.conf || (echo "Nginx config test failed!" && cat /tmp/nginx.conf && exit 1)

# ---- First-time PlatformIO + ESP32 toolchain setup (runs in background) --------
# The toolchain is NOT baked into the image — it lives in the cyd_pio_packages volume
# (/root/.platformio).  On first container start the volume is empty so we download
# everything here and leave a marker so subsequent starts skip this block.
PIO_SETUP_MARKER="/root/.platformio/.cyd_setup_done"
if [ ! -f "$PIO_SETUP_MARKER" ]; then
    echo "PlatformIO toolchain not found — running first-time setup in background."
    echo "The emulator will be available once setup completes (~5-10 min)."
    (
        set +e
        LOG=/tmp/pio_setup.log
        echo "[PIO SETUP] Starting at $(date)" > "$LOG"

        # Phase 1: trigger PlatformIO to download all ESP32 packages
        mkdir -p /tmp/esp32_setup
        printf 'esphome:\n  name: dummy\nesp32:\n  board: esp32dev\n  framework:\n    type: esp-idf\n' \
            > /tmp/esp32_setup/dummy.yaml
        echo "[PIO SETUP] Downloading ESP32 toolchain (Phase 1)…" >> "$LOG"
        timeout 900s esphome compile /tmp/esp32_setup/dummy.yaml >> "$LOG" 2>&1 || true

        # Phase 2: fix PlatformIO binaries for Alpine/musl compatibility
        echo "[PIO SETUP] Fixing wrappers (Phase 2)…" >> "$LOG"
        /app/fix_pio_wrappers.sh >> "$LOG" 2>&1 || true

        PIO_CMAKE=$(find /root/.platformio/packages -path '*/tool-cmake/bin/cmake' 2>/dev/null | head -1)
        if [ -n "$PIO_CMAKE" ]; then
            mv "$PIO_CMAKE" "${PIO_CMAKE}.orig"
            printf '#!/bin/sh\nexec /usr/bin/cmake "$@"\n' > "$PIO_CMAKE"
            chmod +x "$PIO_CMAKE"
            echo "[PIO SETUP] Replaced cmake wrapper" >> "$LOG"
        fi

        PIO_NINJA=$(find /root/.platformio/packages -path '*/tool-ninja/ninja' 2>/dev/null | head -1)
        if [ -n "$PIO_NINJA" ]; then
            mv "$PIO_NINJA" "${PIO_NINJA}.orig"
            printf '#!/bin/sh\nexec /usr/bin/ninja "$@"\n' > "$PIO_NINJA"
            chmod +x "$PIO_NINJA"
            echo "[PIO SETUP] Replaced ninja wrapper" >> "$LOG"
        fi

        # Remove the orig binaries now that wrappers are in place
        find /root/.platformio -name '*.orig' -delete 2>/dev/null

        rm -rf /tmp/esp32_setup

        # Phase 3: pre-compile the emulator to warm up the build cache.
        # We do NOT delete .esphome afterwards — the compiled artifacts are left in the
        # cyd_esphome_build volume so the first real emulator run is instant (incremental build).
        echo "[PIO SETUP] Pre-compiling emulator (Phase 3)…" >> "$LOG"
        # Ensure the images.yaml placeholder exists so the !include in lib_common.yaml resolves.
        touch /app/esphome/lib/images.yaml
        [ -s /app/esphome/lib/images.yaml ] || printf '{}\n' > /app/esphome/lib/images.yaml
        cd /app/esphome && CMAKE_BUILD_PARALLEL_LEVEL=2 esphome compile lib/emulator.yaml >> "$LOG" 2>&1 || true

        touch "$PIO_SETUP_MARKER"
        echo "[PIO SETUP] Done at $(date)" >> "$LOG"
        echo "PlatformIO setup complete. Emulator is now ready."
    ) &
else
    echo "PlatformIO toolchain already set up (volume populated)."
fi
# ---- End PlatformIO setup --------------------------------------------------------

exec "$@"
