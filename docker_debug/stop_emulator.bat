@echo off
set containerName=cyd-emulator

echo Stopping container '%containerName%'...
docker stop %containerName%

echo Removing container '%containerName%'...
docker rm %containerName%

echo Emulator stopped and removed.
