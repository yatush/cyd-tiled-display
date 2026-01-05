#!/bin/bash

# Set up display to match the container's main X server
export DISPLAY=:0
export PYTHONUNBUFFERED=1

# Kill any existing emulator instance to prevent duplicates
pkill -f "program" || true

# Navigate to esphome directory
cd /app/esphome

echo "Starting ESPHome Emulator..."

# Run ESPHome
# This will compile (if needed) and run the emulator on the existing display
# Use stdbuf to force line buffering for stdout/stderr to ensure logs appear immediately
stdbuf -oL -eL esphome run lib/emulator.yaml
