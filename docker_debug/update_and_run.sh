#!/bin/bash

CONTAINER_NAME="cyd-emulator"
IMAGE_NAME="cyd-emulator-vnc"

# Ensure we are in the correct directory
if [ ! -f "../Dockerfile" ]; then
    echo "Error: Dockerfile not found. Please run this script from the 'docker_debug' directory."
    exit 1
fi

# ---------------------------------------------------------------------------
# Ensure Docker daemon is running with the correct data-root.
# We use /tmp/docker-data (on /dev/sdc1, ~44GB) instead of /var/lib/docker
# (on /dev/loop4, ~32GB shared with the workspace) to avoid disk space issues.
# ---------------------------------------------------------------------------
DOCKER_DATA_ROOT="/tmp/docker-data"
DAEMON_JSON="/etc/docker/daemon.json"

# Write daemon.json if missing or has wrong data-root
if ! grep -q "$DOCKER_DATA_ROOT" "$DAEMON_JSON" 2>/dev/null; then
    echo "Configuring Docker data-root to $DOCKER_DATA_ROOT ..."
    sudo mkdir -p /etc/docker
    sudo tee "$DAEMON_JSON" > /dev/null << DAEMON_EOF
{
  "data-root": "$DOCKER_DATA_ROOT",
  "storage-driver": "overlay2"
}
DAEMON_EOF
fi

mkdir -p "$DOCKER_DATA_ROOT"

# ---------------------------------------------------------------------------
# Ensure containerd and dockerd are running and properly connected.
#
# We check actual processes (not socket files, which can be stale leftovers)
# and restart dockerd any time containerd had to be started, so dockerd always
# holds a live connection to containerd before we attempt `docker run`.
# ---------------------------------------------------------------------------

_start_containerd() {
    echo "Starting containerd..."
    sudo mkdir -p /run/containerd
    sudo containerd > /tmp/containerd.log 2>&1 &
    echo -n "Waiting for containerd "
    until pgrep -x containerd > /dev/null && sudo test -S /run/containerd/containerd.sock; do
        echo -n "."; sleep 1;
    done
    echo " ready!"
}

_start_dockerd() {
    echo "Starting Docker daemon (using data-root: $DOCKER_DATA_ROOT)..."
    sudo dockerd --dns 168.63.129.16 > /tmp/dockerd.log 2>&1 &
    echo -n "Waiting for Docker "
    until docker ps > /dev/null 2>&1; do echo -n "."; sleep 1; done
    echo " ready!"
}

_restart_dockerd() {
    echo "Restarting dockerd to connect to the newly started containerd..."
    sudo kill "$(pgrep -x dockerd | head -1)" 2>/dev/null
    sleep 2
    _start_dockerd
}

STARTED_CONTAINERD=false
if ! pgrep -x containerd > /dev/null; then
    _start_containerd
    STARTED_CONTAINERD=true
fi

if ! docker ps > /dev/null 2>&1; then
    _start_dockerd
elif [ "$STARTED_CONTAINERD" = true ]; then
    # dockerd was running before containerd — restart it so it connects properly
    _restart_dockerd
fi

# Parse flags
BAKE_ARG=""
for arg in "$@"; do
    case "$arg" in
        --bake)
            BAKE_ARG="--build-arg BAKE_TOOLCHAIN=1"
            echo "[--bake] Pre-baking toolchain into image (slow build, fully offline runtime)."
            ;;
    esac
done

echo "Detecting latest ESPHome version from PyPI..."
ESPHOME_VERSION=$(python3 -c "import urllib.request,json; d=json.load(urllib.request.urlopen('https://pypi.org/pypi/esphome/json')); print(d['info']['version'])" 2>/dev/null)
if [ -n "$ESPHOME_VERSION" ]; then
    echo "ESPHome version: $ESPHOME_VERSION"
    ESPHOME_VER_ARG="--build-arg ESPHOME_VERSION=$ESPHOME_VERSION"
else
    echo "Could not detect ESPHome version — installing latest"
    ESPHOME_VER_ARG=""
fi

echo "Building image..."
# shellcheck disable=SC2086
docker build $BAKE_ARG $ESPHOME_VER_ARG -t $IMAGE_NAME ..

echo "Checking for existing container..."
if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Removing existing container to ensure fresh configuration..."
    docker rm -f $CONTAINER_NAME
fi

echo "Starting container..."
# Mount volumes:
#   cyd_esphome_build: preserves the pre-compiled .esphome build cache across container restarts
#   cyd_pio_cache: caches PlatformIO downloaded packages
_docker_run() {
    docker run -d --name $CONTAINER_NAME \
      -v "$(pwd)/vnc_startup.sh:/app/vnc_startup.sh" \
      -v "$(pwd)/nginx.conf:/etc/nginx/nginx.conf" \
      -v "cyd_esphome_build:/app/esphome/lib/.esphome" \
      -v "cyd_pio_cache:/tmp/pio_cache" \
      -v "cyd_pio_packages:/root/.platformio" \
      -p 6080:6080 -p 8080:8080 -p 8099:8099 -p 5900:5900 \
      $IMAGE_NAME
}

_docker_run
DOCKER_RUN_EXIT=$?
# If docker run failed with a containerd connection error, recover and retry once.
if [ $DOCKER_RUN_EXIT -ne 0 ]; then
    if grep -q "containerd" /tmp/dockerd.log 2>/dev/null || \
       docker logs $CONTAINER_NAME 2>&1 | grep -q "containerd" || \
       ! pgrep -x containerd > /dev/null; then
        echo "Detected containerd issue — recovering..."
        docker rm -f $CONTAINER_NAME 2>/dev/null || true
        _start_containerd
        _restart_dockerd
        echo "Retrying container start..."
        _docker_run
    else
        echo "ERROR: docker run failed (exit $DOCKER_RUN_EXIT). See above for details."
        exit 1
    fi
fi

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

echo "Building frontend..."
(cd ../configurator && npm run build)
if [ $? -ne 0 ]; then
    echo "ERROR: Frontend build failed. Aborting."
    exit 1
fi

echo "Updating frontend build..."
docker cp ../configurator/dist/. "${CONTAINER_NAME}:/app/configurator/dist/"

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
