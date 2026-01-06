#!/bin/bash
set -e

echo "Starting VNC environment..."

export DISPLAY=:0

# Start Xvfb
echo "Starting Xvfb..."
Xvfb :0 -screen 0 480x320x16 2>&1 &
XVFB_PID=$!
sleep 2

# Verify Xvfb is running
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "ERROR: Xvfb failed to start"
    exit 1
fi
echo "Xvfb started (PID: $XVFB_PID)"


# Start x11vnc
echo "Starting x11vnc on port 5900..."
x11vnc -display :0 -forever -nopw -shared -bg -o /tmp/x11vnc.log
sleep 1

# Verify x11vnc is listening
if ! netstat -ln | grep -q ':5900'; then
    echo "ERROR: x11vnc is not listening on port 5900"
    cat /tmp/x11vnc.log
    exit 1
fi
echo "x11vnc started successfully"

# Start websockify instances
echo "Starting websockify on port 6080..."
/app/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 2>&1 &

echo "Starting websockify on port 6081 (for Cloud Run nginx proxy)..."
websockify --web /app/novnc 6081 localhost:5900 2>&1 &

echo "VNC environment ready"

exec "$@"
