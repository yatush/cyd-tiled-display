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
# We mount a volume for the build cache so recompiling is fast across restarts
docker run -d --name $CONTAINER_NAME \
  -v "$(pwd)/vnc_startup.sh:/app/vnc_startup.sh" \
  -v "cyd_esphome_cache:/app/esphome/.esphome/build" \
  -p 6080:6080 -p 8099:8099 -p 5900:5900 \
  $IMAGE_NAME

echo "Container started."
echo "Waiting for services to initialize..."
sleep 5

echo "Updating files (just in case)..."
docker cp ../esphome "${CONTAINER_NAME}:/app/"
docker cp ../configurator "${CONTAINER_NAME}:/app/"

echo ""
echo "---------------------------------------------------"
echo "NoVNC URL:      http://localhost:6080/vnc.html"
echo "Configurator:   http://localhost:8099"
echo "---------------------------------------------------"
echo ""
echo "To start the emulator, use the Web UI or run:"
echo "docker exec -d $CONTAINER_NAME sh -c '/app/configurator/run_emulator.sh > /tmp/emulator.log 2>&1'"

