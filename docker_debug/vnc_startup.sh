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

# Start Xvfb
echo "Starting Xvfb..."
Xvfb :0 -screen 0 480x320x16 -ac -noreset 2>&1 &
XVFB_PID=$!

# Wait for Xvfb to be ready by checking for the Unix socket
echo "Waiting for Xvfb to initialize on $DISPLAY..."
for i in $(seq 1 10); do
    if [ -S /tmp/.X11-unix/X0 ]; then
        echo "Xvfb socket /tmp/.X11-unix/X0 is ready"
        break
    fi
    echo "Waiting for Xvfb socket... ($i/10)"
    sleep 1
done

# Verify Xvfb socket exists
if [ ! -S /tmp/.X11-unix/X0 ]; then
    echo "ERROR: Xvfb failed to create socket /tmp/.X11-unix/X0"
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

exec "$@"
