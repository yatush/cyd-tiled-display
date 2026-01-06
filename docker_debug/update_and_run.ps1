$ErrorActionPreference = "Stop"
$containerName = "cyd-emulator"
$imageName = "cyd-emulator-vnc"

# Ensure we are in the correct directory (check for Dockerfile)
if (-not (Test-Path "../Dockerfile")) {
    Write-Error "Dockerfile not found. Please run this script from the 'docker_debug' directory."
    exit 1
}

Write-Host "Building image..."
docker build -t $imageName ..

Write-Host "Checking for existing container..."
$containerExists = docker ps -aq -f "name=^/${containerName}$"

if ($containerExists) {
    Write-Host "Removing existing container to ensure fresh configuration..."
    docker rm -f $containerName
}

Write-Host "Starting container..."
# We mount a volume for the build cache so recompiling is fast across restarts
docker run -d --name $containerName `
  -v "${PWD}/vnc_startup.sh:/app/vnc_startup.sh" `
  -v "${PWD}/nginx.conf:/etc/nginx/nginx.conf" `
  -v "cyd_esphome_cache:/app/esphome/.esphome/build" `
  -p 6080:6080 -p 8080:8080 -p 8099:8099 -p 5900:5900 `
  $imageName

Write-Host "Container started."
Write-Host "Waiting for services to initialize..."
Start-Sleep -Seconds 5

Write-Host "Updating ESPHome files..."
docker cp ../esphome "${containerName}:/app/"

Write-Host "Updating Python backend scripts..."
docker cp ../configurator/server.py "${containerName}:/app/configurator/"
docker cp ../configurator/generate_tiles_api.py "${containerName}:/app/configurator/"
docker cp ../configurator/run_emulator.sh "${containerName}:/app/configurator/"

Write-Host ""
Write-Host "---------------------------------------------------"
Write-Host "Configurator (nginx):   http://localhost:8080"
Write-Host "Configurator (direct):  http://localhost:8099"
Write-Host "NoVNC (direct):         http://localhost:6080/vnc.html"
Write-Host "---------------------------------------------------"
Write-Host ""
Write-Host "Use port 8080 to test the same setup as Cloud Run."
Write-Host ""
Write-Host "To start the emulator, use the Web UI or run:"
Write-Host "docker exec -d $containerName sh -c '/app/configurator/run_emulator.sh > /tmp/emulator.log 2>&1'"

