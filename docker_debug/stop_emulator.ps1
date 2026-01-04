$ErrorActionPreference = "Stop"
$containerName = "cyd-emulator"

Write-Host "Stopping container '$containerName'..."
docker stop $containerName

Write-Host "Removing container '$containerName'..."
docker rm $containerName

Write-Host "Emulator stopped and removed."
