# MIDAS Docker Health Check Script for Windows

Write-Host "MIDAS Service Health Check" -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan
Write-Host ""

# Function to check service health
function Check-ServiceHealth {
    param(
        [string]$ServiceName,
        [string]$ContainerName,
        [string]$HealthCheckUrl = $null,
        [int]$Port = 0
    )
    
    Write-Host "${ServiceName}:" -NoNewline
    
    # Check if container is running
    $container = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>$null
    if (-not $container) {
        Write-Host " STOPPED" -ForegroundColor Red
        return $false
    }
    
    # Check container health status
    $health = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>$null
    if ($health -eq "healthy") {
        Write-Host " HEALTHY" -ForegroundColor Green
        
        # Additional endpoint check if URL provided
        if ($HealthCheckUrl) {
            try {
                $response = Invoke-WebRequest -Uri $HealthCheckUrl -Method Head -TimeoutSec 5 -ErrorAction Stop
                Write-Host "  Endpoint: Responding" -ForegroundColor Gray
            } catch {
                Write-Host "  Endpoint: Not responding" -ForegroundColor Yellow
            }
        }
        
        return $true
    } elseif ($health -eq "starting") {
        Write-Host " STARTING" -ForegroundColor Yellow
        return $false
    } elseif ($health -eq "unhealthy") {
        Write-Host " UNHEALTHY" -ForegroundColor Red
        
        # Get last health check logs
        $logs = docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' $ContainerName 2>$null
        if ($logs) {
            Write-Host "  Last check: $logs" -ForegroundColor Gray
        }
        
        return $false
    } else {
        # No health check defined, check if running
        $status = docker inspect --format='{{.State.Status}}' $ContainerName 2>$null
        if ($status -eq "running") {
            Write-Host " RUNNING" -ForegroundColor Green -NoNewline
            Write-Host " (no health check)" -ForegroundColor Gray
            
            # Try port check if provided
            if ($Port -gt 0) {
                $connection = Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
                if ($connection) {
                    Write-Host "  Port $Port`: Open" -ForegroundColor Gray
                } else {
                    Write-Host "  Port $Port`: Closed" -ForegroundColor Yellow
                }
            }
            
            return $true
        } else {
            Write-Host " $status" -ForegroundColor Red
            return $false
        }
    }
}

# Check all services
$services = @(
    @{Name="PostgreSQL"; Container="midas-postgres"; Port=5432},
    @{Name="Redis"; Container="midas-redis"; Port=6379},
    @{Name="Qdrant"; Container="midas-qdrant"; Url="http://localhost:6333/health"; Port=6333},
    @{Name="Ollama"; Container="midas-ollama"; Url="http://localhost:11434/api/tags"; Port=11434},
    @{Name="Streamlit"; Container="midas-streamlit"; Url="http://localhost:8501/_stcore/health"; Port=8501},
    @{Name="Celery Worker (Docs)"; Container="midas-celery-docs"},
    @{Name="Celery Worker (Analysis)"; Container="midas-celery-analysis"},
    @{Name="Celery Beat"; Container="midas-celery-beat"},
    @{Name="Flower"; Container="midas-flower"; Url="http://localhost:5555/api/workers"; Port=5555},
    @{Name="Nginx"; Container="midas-nginx"; Url="http://localhost/health"; Port=80},
    @{Name="Backup Service"; Container="midas-backup"}
)

$healthyCount = 0
$totalCount = $services.Count

foreach ($service in $services) {
    $isHealthy = Check-ServiceHealth -ServiceName $service.Name `
                                     -ContainerName $service.Container `
                                     -HealthCheckUrl $service.Url `
                                     -Port $service.Port
    if ($isHealthy) {
        $healthyCount++
    }
}

# Summary
Write-Host "`nSummary:" -ForegroundColor Cyan
Write-Host "  Healthy services: $healthyCount/$totalCount" -ForegroundColor $(if ($healthyCount -eq $totalCount) { "Green" } elseif ($healthyCount -gt $totalCount/2) { "Yellow" } else { "Red" })

# Check disk usage for volumes
Write-Host "`nVolume Usage:" -ForegroundColor Cyan
$volumes = @(
    "volumes/postgres-data",
    "volumes/qdrant-storage",
    "volumes/redis-data",
    "volumes/ollama-models",
    "volumes/streamlit-appdata"
)

foreach ($volume in $volumes) {
    if (Test-Path $volume) {
        $size = (Get-ChildItem -Path $volume -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
        $name = Split-Path $volume -Leaf
        Write-Host "  ${name}: $([math]::Round($size, 2)) MB" -ForegroundColor Gray
    }
}

# Check for recent errors in logs
Write-Host "`nRecent Errors (last 5 minutes):" -ForegroundColor Cyan
$fiveMinutesAgo = (Get-Date).AddMinutes(-5).ToString("yyyy-MM-ddTHH:mm:ss")

$containersToCheck = @("midas-streamlit", "midas-celery-docs", "midas-celery-analysis")
$errorFound = $false

foreach ($container in $containersToCheck) {
    $errors = docker logs $container --since $fiveMinutesAgo 2>&1 | Select-String -Pattern "ERROR|CRITICAL|Exception" -CaseSensitive
    if ($errors) {
        Write-Host "  $container`:" -ForegroundColor Yellow
        $errors | Select-Object -First 3 | ForEach-Object {
            Write-Host "    $_" -ForegroundColor Red
        }
        $errorFound = $true
    }
}

if (-not $errorFound) {
    Write-Host "  No recent errors found" -ForegroundColor Green
}

# Performance metrics
Write-Host "`nPerformance Metrics:" -ForegroundColor Cyan
$stats = docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>$null
if ($stats) {
    $stats | Where-Object { $_ -like "*midas-*" } | ForEach-Object {
        Write-Host "  $_" -ForegroundColor Gray
    }
}

Write-Host "`nHealth check completed." -ForegroundColor Green