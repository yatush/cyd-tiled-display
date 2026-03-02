#!/bin/bash
containerName="cyd-emulator"

# Ensure Docker daemon is running before attempting commands
if ! docker ps > /dev/null 2>&1; then
    DOCKER_DATA_ROOT="/tmp/docker-data"
    mkdir -p "$DOCKER_DATA_ROOT"
    echo "Starting Docker daemon..."
    sudo dockerd > /tmp/dockerd.log 2>&1 &
    until docker ps > /dev/null 2>&1; do sleep 1; done
fi

if [ "$(docker ps -aq -f name=^/${containerName}$)" ]; then
    echo "Stopping container '$containerName'..."
    docker stop "$containerName" 2>/dev/null || true

    echo "Removing container '$containerName'..."
    docker rm "$containerName" 2>/dev/null || true

    echo "Emulator stopped and removed."
else
    echo "Container '$containerName' is not running."
fi
