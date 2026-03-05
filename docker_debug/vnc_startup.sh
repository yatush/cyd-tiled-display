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

# ---- Persist PlatformIO directory across addon updates ----------------------
# In the HA addon, /data is a persistent volume (map: data:rw) but
# /root/.platformio is ephemeral and wiped on every addon update.
# We redirect it to /data/.platformio via symlink so the downloaded toolchain
# survives upgrades without re-downloading.
# Only done in HA addon mode (detected via $SUPERVISOR_TOKEN injected by the
# HA supervisor). In plain Docker (update_and_run.sh) the named volume is
# already mounted directly at /root/.platformio so no redirect is needed.
if [ -n "$SUPERVISOR_TOKEN" ] && [ ! -L /root/.platformio ]; then
    mkdir -p /data
    if [ -d /root/.platformio ]; then
        # Carry over any toolchain baked into the image (BAKE_TOOLCHAIN=1)
        cp -a /root/.platformio/. /data/.platformio/ 2>/dev/null || true
        rm -rf /root/.platformio
    fi
    mkdir -p /data/.platformio
    ln -sf /data/.platformio /root/.platformio
    echo "Linked /root/.platformio → /data/.platformio (HA persistent storage)"
fi
# ---- End PlatformIO persistence ----------------------------------------------

# ---- Toolchain setup (runs in background) ---------------------------------------
# toolchain_setup.py checks whether the pre-built toolchain already matches the
# ESPHome version baked into this image.  If not, it:
#   1. Downloads the pre-built tarball from GitHub Releases (fast, with UI progress)
#   2. Falls back to a local compile if the release isn't available yet
# Progress is written to /tmp/toolchain_setup_progress.json and exposed to the
# React UI via /api/toolchain/status so users see a real-time progress bar.
echo "Starting toolchain setup (background)..."
python3 /app/toolchain_setup.py > /tmp/toolchain_setup.log 2>&1 &

# ---- Toolchain update watchdog --------------------------------------------------
# Checks for a new ESPHome release every 6 hours while the container is running.
# If a newer pre-built tarball is available it downloads it in the background,
# showing the amber badge in the TopBar just like startup does.
# Skips the check if toolchain_setup.py is already running.
(
  # Wait for the initial setup to finish before starting the watchdog loop.
  WATCHDOG_MARKER="/root/.platformio/.cyd_setup_done"
  WAIT=0
  while [ ! -f "$WATCHDOG_MARKER" ] && [ $WAIT -lt 1800 ]; do
    sleep 10; WAIT=$((WAIT + 10))
  done
  while true; do
    sleep 21600  # 6 hours
    # Skip if a toolchain_setup.py is already running (e.g. user triggered local build)
    if pgrep -f "toolchain_setup.py" > /dev/null 2>&1; then
      continue
    fi
    echo "[watchdog] Checking for toolchain update..." >> /tmp/toolchain_setup.log
    python3 /app/toolchain_setup.py >> /tmp/toolchain_setup.log 2>&1
  done
) &
# ---- End toolchain update watchdog ----------------------------------------------
# ---- End toolchain setup --------------------------------------------------------

exec "$@"
