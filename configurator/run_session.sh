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

# Use a shared cache directory to speed up builds across different session names
export PLATFORMIO_CACHEDIR="/tmp/pio_cache"
mkdir -p "$PLATFORMIO_CACHEDIR"

# Create a session-specific build directory by copying from the pre-compiled cache
# This allows concurrent sessions without conflicts, while reusing compiled objects
SESSION_ESPHOME="/tmp/esphome_sessions/$SESSION_ID/.esphome"
if [ ! -d "$SESSION_ESPHOME/build/emulator" ] && [ -d "/app/esphome/lib/.esphome/build/emulator" ]; then
    echo "Seeding session build cache from pre-compiled image..."
    mkdir -p "$SESSION_ESPHOME"
    cp -a /app/esphome/lib/.esphome/build "$SESSION_ESPHOME/"
    cp -a /app/esphome/lib/.esphome/storage "$SESSION_ESPHOME/" 2>/dev/null || true

    # Update build_path in storage JSON so ESPHome doesn't trigger a clean rebuild
    # ESPHome compares old build_path vs new and deletes .pioenvs if they differ
    STORAGE_FILE="$SESSION_ESPHOME/storage/emulator.yaml.json"
    if [ -f "$STORAGE_FILE" ]; then
        sed -i "s|/app/esphome/lib/.esphome/build/emulator|$SESSION_ESPHOME/build/emulator|g" "$STORAGE_FILE"
    fi
fi

# Point ESPHome to the session-specific build directory
export ESPHOME_DATA_DIR="$SESSION_ESPHOME"

# Use the same device name as the pre-compiled build to maximize cache reuse
stdbuf -oL -eL esphome -s tiles_file "$TILES_FILE" -s api_port "$API_PORT" run lib/emulator.yaml
