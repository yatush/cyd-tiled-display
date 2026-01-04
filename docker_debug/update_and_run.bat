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
REM We mount a volume for the build cache so recompiling is fast across restarts
docker run -d --name %CONTAINER_NAME% ^
  -v "%cd%\vnc_startup.sh:/app/vnc_startup.sh" ^
  -v "cyd_esphome_cache:/app/esphome/.esphome/build" ^
  -p 6080:6080 -p 8099:8099 -p 5900:5900 ^
  %IMAGE_NAME%

echo Container started.
echo Waiting for services to initialize...
timeout /t 5 /nobreak >nul

echo Updating files (just in case)...
docker cp ..\esphome "%CONTAINER_NAME%:/app/"
docker cp ..\configurator "%CONTAINER_NAME%:/app/"

echo.
echo ---------------------------------------------------
echo NoVNC URL:      http://localhost:6080/vnc.html
echo Configurator:   http://localhost:8099
echo ---------------------------------------------------
echo.
echo To start the emulator, use the Web UI or run:
echo docker exec -d %CONTAINER_NAME% sh -c "/app/configurator/run_emulator.sh > /tmp/emulator.log 2>&1"
echo.
pause
goto :EOF

