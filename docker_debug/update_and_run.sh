#!/bin/bash

CONTAINER_NAME="cyd-emulator"
IMAGE_NAME="cyd-emulator-vnc"

# Ensure we are in the correct directory
if [ ! -f "../Dockerfile" ]; then
    echo "Error: Dockerfile not found. Please run this script from the 'docker_debug' directory."
    exit 1
fi

echo "Building image..."
docker build -t $IMAGE_NAME ..

echo "Checking for existing container..."
if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Removing existing container to ensure fresh configuration..."
    docker rm -f $CONTAINER_NAME
fi

echo "Starting container..."
# Mount volumes:
#   cyd_esphome_build: preserves the pre-compiled .esphome build cache across container restarts
#   cyd_pio_cache: caches PlatformIO downloaded packages
docker run -d --name $CONTAINER_NAME \
  -v "$(pwd)/vnc_startup.sh:/app/vnc_startup.sh" \
  -v "$(pwd)/nginx.conf:/etc/nginx/nginx.conf" \
  -v "cyd_esphome_build:/app/esphome/lib/.esphome" \
  -v "cyd_pio_cache:/tmp/pio_cache" \
  -p 6080:6080 -p 8080:8080 -p 8099:8099 -p 5900:5900 \
  $IMAGE_NAME

echo "Container started."

# Helper: check if container is still running (not crashed/exited)
check_container_alive() {
    local state
    state=$(docker inspect -f '{{.State.Running}}' $CONTAINER_NAME 2>/dev/null)
    if [ "$state" != "true" ]; then
        echo ""
        echo "ERROR: Container exited unexpectedly!"
        echo "Container logs:"
        docker logs --tail 40 $CONTAINER_NAME
        echo ""
        echo "Tip: Run 'docker rm -f $CONTAINER_NAME' and try again."
        exit 1
    fi
}

# Wait for port 8080 (nginx + gunicorn) to become reachable
MAX_WAIT=60
WAITED=0
echo -n "Waiting for port 8080 to become reachable "
while ! curl -s -o /dev/null -w '' --max-time 2 http://localhost:8080/ 2>/dev/null; do
    check_container_alive
    echo -n "."
    sleep 2
    WAITED=$((WAITED + 2))
    if [ $WAITED -ge $MAX_WAIT ]; then
        echo ""
        echo "WARNING: Port 8080 did not become reachable within ${MAX_WAIT}s."
        echo "Container logs:"
        docker logs --tail 30 $CONTAINER_NAME
        echo ""
        echo "Continuing anyway — the container may still be starting."
        break
    fi
done
if [ $WAITED -lt $MAX_WAIT ]; then
    echo " ready! (${WAITED}s)"
fi

echo "Updating ESPHome files (preserving build cache)..."
# Copy esphome files but exclude the .esphome build cache directory
# We use tar to selectively copy, excluding the build cache
tar -C .. -cf - --exclude='esphome/lib/.esphome' esphome | docker exec -i $CONTAINER_NAME tar -C /app -xf -

echo "Updating Python backend scripts..."
docker cp ../configurator/server.py "${CONTAINER_NAME}:/app/configurator/"
docker cp ../configurator/generate_tiles_api.py "${CONTAINER_NAME}:/app/configurator/"
docker cp ../configurator/run_emulator.sh "${CONTAINER_NAME}:/app/configurator/"
docker cp ../configurator/run_session.sh "${CONTAINER_NAME}:/app/configurator/"
docker exec $CONTAINER_NAME chmod +x /app/configurator/run_session.sh

echo "Updating frontend build..."
if [ -d "../configurator/dist" ]; then
    docker cp ../configurator/dist/. "${CONTAINER_NAME}:/app/configurator/dist/"
else
    echo "WARNING: No dist/ folder found. Run 'npx vite build' in configurator/ first."
fi

# Gunicorn auto-reloads workers when server.py changes, wait for it to be ready again
echo -n "Waiting for server to be ready after file updates "
WAITED=0
while ! curl -s -o /dev/null -w '' --max-time 2 http://localhost:8080/api/schema 2>/dev/null; do
    check_container_alive
    echo -n "."
    sleep 2
    WAITED=$((WAITED + 2))
    if [ $WAITED -ge 30 ]; then
        echo ""
        echo "WARNING: Server did not become ready within 30s after file update."
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
echo ""
echo "Use port 8080 to test the same setup as Cloud Run."
echo ""
echo "To start the emulator, use the Web UI or run:"
echo "docker exec -d $CONTAINER_NAME sh -c '/app/configurator/run_emulator.sh > /tmp/emulator.log 2>&1'"
