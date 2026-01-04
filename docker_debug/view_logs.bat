@echo off
echo Waiting for emulator logs... (Start the emulator in the web UI if you haven't)
docker exec -it cyd-emulator tail -n 50 -F /tmp/emulator.log