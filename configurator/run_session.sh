#!/bin/bash
# Usage: ./run_session.sh <session_id> <display_num> <vnc_port> <websockify_port> <tiles_file> <api_port>

SESSION_ID=$1
DISPLAY_NUM=$2
VNC_PORT=$3
WEBSOCKIFY_PORT=$4
TILES_FILE=$5
API_PORT=$6

if [ -z "$TILES_FILE" ]; then
    TILES_FILE="user_config.yaml"
fi

export DISPLAY=:$DISPLAY_NUM
export PYTHONUNBUFFERED=1

echo "Starting session $SESSION_ID on display $DISPLAY, VNC port $VNC_PORT, Websockify port $WEBSOCKIFY_PORT"

# Cleanup any stale locks for this display
rm -f /tmp/.X$DISPLAY_NUM-lock

# Start Xvfb
# Redirect stdout/stderr to /dev/null to suppress xkbcomp warnings
Xvfb :$DISPLAY_NUM -screen 0 480x320x16 -ac -noreset >/dev/null 2>&1 &
XVFB_PID=$!

# Function to clean up background processes
cleanup() {
    echo "Cleaning up session $SESSION_ID on display $DISPLAY..."
    kill $XVFB_PID 2>/dev/null
    # Kill other processes started by this script
    pkill -P $$
}
trap cleanup EXIT

# Wait for Xvfb
for i in $(seq 1 10); do
    if [ -S /tmp/.X11-unix/X$DISPLAY_NUM ]; then
        echo "Xvfb ready on $DISPLAY"
        break
    fi
    sleep 0.5
done

# Start x11vnc
# Filter out the DPMS missing warning which is harmless on Xvfb
x11vnc -display :$DISPLAY_NUM -forever -nopw -shared -bg -rfbport $VNC_PORT -quiet -noxkb -noxdamage -no6 2>&1 | grep -v 'extension "DPMS" missing'

# Start websockify
# Use the installed websockify from pip or the one in /app/novnc
if command -v websockify >/dev/null 2>&1; then
    websockify --web /app/novnc $WEBSOCKIFY_PORT localhost:$VNC_PORT 2>&1 &
else
    /app/novnc/utils/websockify/run --web /app/novnc $WEBSOCKIFY_PORT localhost:$VNC_PORT 2>&1 &
fi

# Navigate to esphome directory
if [ -d "/config/esphome" ]; then
    cd /config/esphome
else
    cd /app/esphome
fi

echo "Starting ESPHome Emulator for session $SESSION_ID..."
# Sanitize session ID for ESPHome device name (must be lowercase alphanumeric/hyphen)
SAFE_SESSION_ID=$(echo "$SESSION_ID" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')

# Use a shared cache directory to speed up builds across different session names
export PLATFORMIO_CACHEDIR="/tmp/pio_cache"
mkdir -p "$PLATFORMIO_CACHEDIR"

# Use unique device_name to avoid build directory conflicts
# The -s substitutions must come before the 'run' command
stdbuf -oL -eL esphome -s tiles_file "$TILES_FILE" -s device_name "emulator-$SAFE_SESSION_ID" -s api_port "$API_PORT" run lib/emulator.yaml
