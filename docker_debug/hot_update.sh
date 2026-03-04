#!/bin/bash
# hot_update.sh — update files in the running container WITHOUT rebuilding the image.
# Use this after code changes when the Docker image itself hasn't changed.
# Run update_and_run.sh instead if you've changed the Dockerfile or need a fresh container.

CONTAINER_NAME="cyd-emulator"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "ERROR: Container '${CONTAINER_NAME}' is not running."
    echo "Run ./update_and_run.sh first to build and start it."
    exit 1
fi

echo "Updating ESPHome files (preserving build cache)..."
tar -C .. -cf - --exclude='esphome/lib/.esphome' esphome | docker exec -i $CONTAINER_NAME tar -C /app -xf -

echo "Updating Python backend scripts..."
docker cp ../configurator/server.py "${CONTAINER_NAME}:/app/configurator/"
docker cp ../configurator/generate_tiles_api.py "${CONTAINER_NAME}:/app/configurator/"
docker cp ../configurator/run_emulator.sh "${CONTAINER_NAME}:/app/configurator/"
docker cp ../configurator/run_session.sh "${CONTAINER_NAME}:/app/configurator/"
docker exec $CONTAINER_NAME chmod +x /app/configurator/run_session.sh

echo "Building frontend..."
(cd ../configurator && npm run build)
if [ $? -ne 0 ]; then
    echo "ERROR: Frontend build failed. Aborting."
    exit 1
fi

echo "Updating frontend build..."
docker cp ../configurator/dist/. "${CONTAINER_NAME}:/app/configurator/dist/"

# Gunicorn auto-reloads when server.py changes; wait for it
echo -n "Waiting for server to be ready "
WAITED=0
while ! curl -s -o /dev/null -w '' --max-time 2 http://localhost:8080/api/schema 2>/dev/null; do
    echo -n "."
    sleep 2
    WAITED=$((WAITED + 2))
    if [ $WAITED -ge 30 ]; then
        echo ""
        echo "WARNING: Server did not become ready within 30s."
        break
    fi
done
if [ $WAITED -lt 30 ]; then
    echo " ready! (${WAITED}s)"
fi

echo ""
echo "---------------------------------------------------"
echo "Configurator (nginx):   http://localhost:8080"
echo "Configurator (direct):  http://localhost:8099"
echo "NoVNC (direct):         http://localhost:6080/vnc.html"
echo "---------------------------------------------------"
