#!/bin/bash

# Set up display to match the container's main X server
export DISPLAY=:0
export PYTHONUNBUFFERED=1

# Device configuration (SCREEN_W, SCREEN_H, FONT_* etc.) is supplied by the
# caller via environment variables — see _DEVICE_CONFIG in server.py.
# Apply defaults so the script can also be run standalone (matches 3248s035).
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

# Kill any existing emulator instance to prevent duplicates
pkill -f "program" || true

# Navigate to esphome directory
if [ -d "/config/esphome" ]; then
    cd /config/esphome
else
    cd /app/esphome
fi

echo "Starting ESPHome Emulator..."

export PLATFORMIO_CACHEDIR="/tmp/pio_cache"
mkdir -p "$PLATFORMIO_CACHEDIR"

export CCACHE_DIR="/root/.platformio/.ccache"
export CCACHE_MAXSIZE="2G"
export CCACHE_COMPILERCHECK="content"
export CCACHE_SLOPPINESS="include_file_mtime,time_macros"
export CCACHE_NOHASHDIR="true"
mkdir -p "$CCACHE_DIR"
export PATH="/usr/local/lib/ccache:$PATH"

EMULATOR_ESPHOME="/tmp/esphome_emulator/.esphome"
export CCACHE_BASEDIR="$EMULATOR_ESPHOME"
if [ ! -d "$EMULATOR_ESPHOME/build/emulator" ] && [ -d "/app/esphome/lib/.esphome/build/emulator" ]; then
    echo "Seeding emulator build cache from pre-compiled image..."
    mkdir -p "$EMULATOR_ESPHOME"
    cp -a /app/esphome/lib/.esphome/build "$EMULATOR_ESPHOME/"
    cp -a /app/esphome/lib/.esphome/storage "$EMULATOR_ESPHOME/" 2>/dev/null || true

    STORAGE_FILE="$EMULATOR_ESPHOME/storage/emulator.yaml.json"
    if [ -f "$STORAGE_FILE" ]; then
        sed -i "s|/app/esphome/lib/.esphome/build/emulator|$EMULATOR_ESPHOME/build/emulator|g" "$STORAGE_FILE"
    fi

    find "$EMULATOR_ESPHOME/build/emulator/.pioenvs" -name '*.o' -exec touch {} +
fi

export ESPHOME_DATA_DIR="$EMULATOR_ESPHOME"
export CMAKE_BUILD_PARALLEL_LEVEL=$(nproc)

# Run ESPHome
# This will compile (if needed) and run the emulator on the existing display
# Use stdbuf to force line buffering for stdout/stderr to ensure logs appear immediately
stdbuf -oL -eL esphome \
  -s tiles_file "user_config.yaml" \
  -s api_port "6053" \
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
