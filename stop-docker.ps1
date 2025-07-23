# MIDAS Docker Stop Script for Windows

Write-Host "MIDAS Docker Shutdown Script" -ForegroundColor Cyan
Write-Host "============================" -ForegroundColor Cyan

# Show current service status
Write-Host "`nCurrent service status:" -ForegroundColor Yellow
docker-compose ps

# Ask for confirmation
$confirmation = Read-Host "`nDo you want to stop all MIDAS services? (y/N)"
if ($confirmation -ne 'y') {
    Write-Host "Shutdown cancelled." -ForegroundColor Yellow
    exit 0
}

# Stop services gracefully
Write-Host "`nStopping MIDAS services..." -ForegroundColor Yellow
docker-compose stop

# Ask about removing containers
$removeContainers = Read-Host "`nDo you want to remove containers? (y/N)"
if ($removeContainers -eq 'y') {
    Write-Host "Removing containers..." -ForegroundColor Yellow
    docker-compose down
    
    # Ask about removing volumes
    $removeVolumes = Read-Host "`nDo you want to remove data volumes? WARNING: This will delete all data! (y/N)"
    if ($removeVolumes -eq 'y') {
        Write-Host "Removing volumes..." -ForegroundColor Red
        docker-compose down -v
        
        # Clean up bind mount directories
        $cleanDirs = Read-Host "`nDo you want to clean bind mount directories? (y/N)"
        if ($cleanDirs -eq 'y') {
            $directories = @(
                "volumes/ollama-models",
                "volumes/qdrant-storage",
                "volumes/postgres-data",
                "volumes/redis-data",
                "volumes/streamlit-appdata",
                "volumes/celery-logs",
                "volumes/celery-beat-schedule",
                "volumes/nginx-cache",
                "volumes/nginx-logs"
            )
            
            foreach ($dir in $directories) {
                if (Test-Path $dir) {
                    Remove-Item -Path $dir -Recurse -Force
                    Write-Host "  Removed: $dir" -ForegroundColor Red
                }
            }
        }
    }
}

Write-Host "`nShutdown complete." -ForegroundColor Green