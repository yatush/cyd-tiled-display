@echo off
REM hot_update.bat — update files in the running container WITHOUT rebuilding the image.
REM Use this after code changes when the Docker image itself hasn't changed.
REM Run update_and_run.bat instead if you've changed the Dockerfile or need a fresh container.
setlocal

set "CONTAINER_NAME=cyd-emulator"

REM Check container is running
set "RUNNING_ID="
for /f "tokens=*" %%i in ('docker ps -q -f "name=^/%CONTAINER_NAME%$"') do set "RUNNING_ID=%%i"
if not defined RUNNING_ID (
    echo ERROR: Container '%CONTAINER_NAME%' is not running.
    echo Run update_and_run.bat first to build and start it.
    exit /b 1
)

echo Updating ESPHome files (preserving build cache)...
tar -C .. -cf - --exclude=esphome/lib/.esphome esphome | docker exec -i %CONTAINER_NAME% tar -C /app -xf -

echo Updating Python backend scripts...
docker cp ..\configurator\server.py "%CONTAINER_NAME%:/app/configurator/"
docker cp ..\configurator\generate_tiles_api.py "%CONTAINER_NAME%:/app/configurator/"
docker cp ..\configurator\run_emulator.sh "%CONTAINER_NAME%:/app/configurator/"
docker cp ..\configurator\run_session.sh "%CONTAINER_NAME%:/app/configurator/"
docker exec %CONTAINER_NAME% chmod +x /app/configurator/run_session.sh

echo Updating toolchain setup script...
docker cp ..\container\toolchain_setup.py "%CONTAINER_NAME%:/app/toolchain_setup.py"

echo Building frontend...
pushd ..\configurator
call npm run build
if errorlevel 1 (
    popd
    echo ERROR: Frontend build failed. Aborting.
    exit /b 1
)
popd

echo Reloading gunicorn...
docker exec %CONTAINER_NAME% sh -c "kill -HUP $(pgrep -of 'gunicorn.*server:app')" >nul 2>&1

echo Updating frontend build...
docker cp ..\configurator\dist\. "%CONTAINER_NAME%:/app/configurator/dist/"

echo Waiting for server to be ready...
set WAITED=0
:wait_loop
curl -s -o nul --max-time 2 http://localhost:8080/api/schema >nul 2>&1
if not errorlevel 1 goto ready
timeout /t 2 /nobreak >nul
set /a WAITED+=2
if %WAITED% geq 30 (
    echo WARNING: Server did not become ready within 30s.
    goto done
)
goto wait_loop

:ready
echo Server ready! (%WAITED%s)

:done
echo.
echo ---------------------------------------------------
echo Configurator (nginx):   http://localhost:8080
echo Configurator (direct):  http://localhost:8099
echo NoVNC (direct):         http://localhost:6080/vnc.html
echo ---------------------------------------------------
