# MIDAS Docker Restore Script for Windows

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,
    [switch]$SkipConfirmation = $false
)

Write-Host "MIDAS Docker Restore Script" -ForegroundColor Cyan
Write-Host "===========================" -ForegroundColor Cyan

# Verify backup file exists
if (-not (Test-Path $BackupFile)) {
    Write-Host "Backup file not found: $BackupFile" -ForegroundColor Red
    exit 1
}

Write-Host "`nBackup file: $BackupFile" -ForegroundColor Yellow

# Warning
if (-not $SkipConfirmation) {
    Write-Host "`nWARNING: This will overwrite all existing data!" -ForegroundColor Red
    Write-Host "Make sure you have stopped all services with: ./stop-docker.ps1" -ForegroundColor Yellow
    $confirm = Read-Host "`nDo you want to continue? (y/N)"
    if ($confirm -ne 'y') {
        exit 0
    }
}

# Create temporary extraction directory
$tempDir = "temp-restore-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

Write-Host "`nExtracting backup..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $BackupFile -DestinationPath $tempDir -Force
    Write-Host "  Extraction completed" -ForegroundColor Green
} catch {
    Write-Host "  Extraction failed: $_" -ForegroundColor Red
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

# Stop services if running
$running = docker-compose ps --services --filter "status=running" 2>$null
if ($running) {
    Write-Host "`nStopping running services..." -ForegroundColor Yellow
    docker-compose down
}

# Restore configuration files
Write-Host "`nRestoring configuration files..." -ForegroundColor Yellow
if (Test-Path "$tempDir/config") {
    # Backup current .env if exists
    if (Test-Path ".env") {
        Copy-Item ".env" ".env.backup-$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Host "  Backed up current .env" -ForegroundColor Gray
    }
    
    # Restore config files
    $configFiles = Get-ChildItem -Path "$tempDir/config" -Recurse -File
    foreach ($file in $configFiles) {
        $relativePath = $file.FullName.Substring("$tempDir/config/".Length)
        $destPath = $relativePath
        $destDir = Split-Path $destPath -Parent
        
        if ($destDir -and -not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        
        Copy-Item -Path $file.FullName -Destination $destPath -Force
        Write-Host "  Restored: $relativePath" -ForegroundColor Green
    }
}

# Restore Qdrant data
Write-Host "`nRestoring Qdrant vector database..." -ForegroundColor Yellow
if (Test-Path "$tempDir/qdrant-storage") {
    $qdrantDest = "volumes/qdrant-storage"
    if (Test-Path $qdrantDest) {
        Remove-Item -Path $qdrantDest -Recurse -Force
    }
    Copy-Item -Path "$tempDir/qdrant-storage" -Destination $qdrantDest -Recurse -Force
    Write-Host "  Qdrant data restored" -ForegroundColor Green
} else {
    Write-Host "  No Qdrant backup found" -ForegroundColor Yellow
}

# Restore Streamlit AppData
Write-Host "`nRestoring Streamlit AppData..." -ForegroundColor Yellow
if (Test-Path "$tempDir/streamlit-appdata") {
    $streamlitDest = "volumes/streamlit-appdata"
    if (Test-Path $streamlitDest) {
        Remove-Item -Path $streamlitDest -Recurse -Force
    }
    Copy-Item -Path "$tempDir/streamlit-appdata" -Destination $streamlitDest -Recurse -Force
    Write-Host "  Streamlit AppData restored" -ForegroundColor Green
} else {
    Write-Host "  No Streamlit AppData backup found" -ForegroundColor Yellow
}

# Restore Ollama models if present
if (Test-Path "$tempDir/ollama-models") {
    Write-Host "`nRestoring Ollama models (this may take a while)..." -ForegroundColor Yellow
    $ollamaDest = "volumes/ollama-models"
    if (Test-Path $ollamaDest) {
        Remove-Item -Path $ollamaDest -Recurse -Force
    }
    Copy-Item -Path "$tempDir/ollama-models" -Destination $ollamaDest -Recurse -Force
    Write-Host "  Ollama models restored" -ForegroundColor Green
}

# Start infrastructure services for database restore
Write-Host "`nStarting database services..." -ForegroundColor Yellow
docker-compose up -d postgres redis

# Wait for services to be ready
Write-Host "  Waiting for services to be ready..." -ForegroundColor Gray
Start-Sleep -Seconds 15

# Restore PostgreSQL
if (Test-Path "$tempDir/postgres-dump.sql") {
    Write-Host "`nRestoring PostgreSQL database..." -ForegroundColor Yellow
    try {
        # Get database credentials
        $env = Get-Content .env | Where-Object { $_ -match "^[^#].*=" } | ForEach-Object {
            $parts = $_.Split('=', 2)
            @{ $parts[0].Trim() = $parts[1].Trim() }
        }
        
        $dbName = if ($env.POSTGRES_DB) { $env.POSTGRES_DB } else { "midas" }
        $dbUser = if ($env.POSTGRES_USER) { $env.POSTGRES_USER } else { "midas_user" }
        
        # Drop and recreate database
        docker-compose exec -T postgres psql -U $dbUser -c "DROP DATABASE IF EXISTS $dbName;"
        docker-compose exec -T postgres psql -U $dbUser -c "CREATE DATABASE $dbName;"
        
        # Restore dump
        Get-Content "$tempDir/postgres-dump.sql" | docker-compose exec -T postgres psql -U $dbUser -d $dbName
        Write-Host "  PostgreSQL database restored" -ForegroundColor Green
    } catch {
        Write-Host "  PostgreSQL restore failed: $_" -ForegroundColor Red
    }
} else {
    Write-Host "`nNo PostgreSQL backup found" -ForegroundColor Yellow
}

# Restore Redis
if (Test-Path "$tempDir/redis-dump.rdb") {
    Write-Host "`nRestoring Redis data..." -ForegroundColor Yellow
    try {
        # Stop Redis to restore data
        docker-compose stop redis
        
        # Copy dump file
        docker cp "$tempDir/redis-dump.rdb" midas-redis:/data/dump.rdb
        
        # Restart Redis
        docker-compose up -d redis
        Write-Host "  Redis data restored" -ForegroundColor Green
    } catch {
        Write-Host "  Redis restore failed: $_" -ForegroundColor Red
    }
} else {
    Write-Host "`nNo Redis backup found" -ForegroundColor Yellow
}

# Clean up temporary directory
Write-Host "`nCleaning up..." -ForegroundColor Yellow
Remove-Item -Path $tempDir -Recurse -Force
Write-Host "  Temporary files removed" -ForegroundColor Green

Write-Host "`nRestore completed!" -ForegroundColor Green
Write-Host "`nTo start all services, run: ./start-docker.ps1" -ForegroundColor Cyan