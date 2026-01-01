#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo "Stopping servers..."
    if [ -n "$PYTHON_PID" ]; then
        kill $PYTHON_PID 2>/dev/null
    fi
    exit
}

# Trap SIGINT (Ctrl+C) and call cleanup
trap cleanup SIGINT

echo "Starting Python Backend..."
# Run python server from the project root
cd "$PROJECT_ROOT"
python3 configurator/server.py &
PYTHON_PID=$!

# Wait a moment for the server to initialize
sleep 2

echo "Starting Frontend Dev Server..."
cd "$SCRIPT_DIR"
npm run dev

# Wait for background process
wait $PYTHON_PID
