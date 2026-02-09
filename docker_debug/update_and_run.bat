@echo off
setlocal

set "CONTAINER_NAME=cyd-emulator"
set "IMAGE_NAME=cyd-emulator-vnc"

if not exist "..\Dockerfile" (
    echo Error: Dockerfile not found. Please run this script from the 'docker_debug' directory.
    exit /b 1
)

echo Building image...
docker build -t %IMAGE_NAME% ..

echo Checking for existing container...
set "CONTAINER_ID="
for /f "tokens=*" %%i in ('docker ps -aq -f "name=^/%CONTAINER_NAME%$"') do set "CONTAINER_ID=%%i"

if defined CONTAINER_ID (
    echo Removing existing container to ensure fresh configuration...
    docker rm -f %CONTAINER_NAME%
)

echo Starting container...
REM Mount volumes:
REM   cyd_esphome_build: preserves the pre-compiled .esphome build cache across container restarts
REM   cyd_pio_cache: caches PlatformIO downloaded packages
docker run -d --name %CONTAINER_NAME% ^
  -v "%cd%\vnc_startup.sh:/app/vnc_startup.sh" ^
  -v "%cd%\nginx.conf:/etc/nginx/nginx.conf" ^
  -v "cyd_esphome_build:/app/esphome/lib/.esphome" ^
  -v "cyd_pio_cache:/tmp/pio_cache" ^
  -p 6080:6080 -p 8080:8080 -p 8099:8099 -p 5900:5900 ^
  %IMAGE_NAME%

echo Container started.
echo Waiting for services to initialize...
timeout /t 5 /nobreak >nul

echo Updating ESPHome files (preserving build cache)...
REM Copy esphome files but exclude the .esphome build cache directory
REM We use tar to selectively copy, excluding the build cache
tar -C .. -cf - --exclude=esphome/lib/.esphome esphome | docker exec -i %CONTAINER_NAME% tar -C /app -xf -

echo Updating Python backend scripts...
docker cp ..\configurator\server.py "%CONTAINER_NAME%:/app/configurator/"
docker cp ..\configurator\generate_tiles_api.py "%CONTAINER_NAME%:/app/configurator/"
docker cp ..\configurator\run_emulator.sh "%CONTAINER_NAME%:/app/configurator/"

echo.
echo ---------------------------------------------------
echo Configurator (nginx):   http://localhost:8080
echo Configurator (direct):  http://localhost:8099
echo NoVNC (direct):         http://localhost:6080/vnc.html
echo ---------------------------------------------------
echo.
echo Use port 8080 to test the same setup as Cloud Run.
echo.
echo To start the emulator, use the Web UI or run:
echo docker exec -d %CONTAINER_NAME% sh -c "/app/configurator/run_emulator.sh > /tmp/emulator.log 2>&1"
echo.
pause
goto :EOF

