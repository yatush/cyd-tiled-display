#!/bin/bash
# Usage: ./run_session.sh <session_id> <display_num> <vnc_port> <websockify_port> <tiles_file> <api_port>
# Device configuration (SCREEN_W, SCREEN_H, FONT_* etc.) is supplied by the
# caller via environment variables — see _DEVICE_CONFIG in server.py.

SESSION_ID=$1
DISPLAY_NUM=$2
VNC_PORT=$3
WEBSOCKIFY_PORT=$4
TILES_FILE=$5
API_PORT=$6

# Apply defaults so the script can also be run standalone (matches 3248s035)
SCREEN_W=${SCREEN_W:-480}
SCREEN_H=${SCREEN_H:-320}
FONT_TINY=${FONT_TINY:-32}
FONT_SMALL=${FONT_SMALL:-60}
FONT_MEDIUM=${FONT_MEDIUM:-80}
FONT_BIG=${FONT_BIG:-100}
FONT_TEXT_REGULAR=${FONT_TEXT_REGULAR:-30}
FONT_TEXT_BOLD=${FONT_TEXT_BOLD:-30}
FONT_TEXT_BIG_BOLD=${FONT_TEXT_BIG_BOLD:-40}
FONT_TEXT_SMALL=${FONT_TEXT_SMALL:-18}
TILE_BORDER_WIDTH=${TILE_BORDER_WIDTH:-2}

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
Xvfb :$DISPLAY_NUM -screen 0 ${SCREEN_W}x${SCREEN_H}x16 -ac -noreset >/dev/null 2>&1 &
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

# Enable ccache so unchanged translation units are served from cache on every
# recompile (tile config changes only touch screens.h / main.cpp, not the
# hundreds of ESPHome framework files).
export CCACHE_DIR="/root/.platformio/.ccache"
export CCACHE_MAXSIZE="2G"
# Normalize absolute paths so the CI cachewarm entries hit here too.
# CCACHE_BASEDIR strips the base dir prefix from all -I flags before hashing.
export CCACHE_BASEDIR="$(pwd)"
mkdir -p "$CCACHE_DIR"
export PATH="/usr/local/lib/ccache:$PATH"

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

# Use all available cores; ccache makes each unchanged .o a near-instant cache hit.
export CMAKE_BUILD_PARALLEL_LEVEL=$(nproc)

# Use the same device name as the pre-compiled build to maximize cache reuse
stdbuf -oL -eL esphome \
  -s tiles_file "$TILES_FILE" \
  -s api_port "$API_PORT" \
  -s screen_w "$SCREEN_W" \
  -s screen_h "$SCREEN_H" \
  -s font_tiny "$FONT_TINY" \
  -s font_small "$FONT_SMALL" \
  -s font_medium "$FONT_MEDIUM" \
  -s font_big "$FONT_BIG" \
  -s font_text_regular "$FONT_TEXT_REGULAR" \
  -s font_text_bold "$FONT_TEXT_BOLD" \
  -s font_text_big_bold "$FONT_TEXT_BIG_BOLD" \
  -s font_text_small "$FONT_TEXT_SMALL" \
  -s tile_border_width "$TILE_BORDER_WIDTH" \
  run lib/emulator.yaml
