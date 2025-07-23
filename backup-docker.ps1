# MIDAS Docker Backup Script for Windows

param(
    [string]$BackupPath = "./backups",
    [switch]$IncludeModels = $false,
    [switch]$CompressOnly = $false
)

Write-Host "MIDAS Docker Backup Script" -ForegroundColor Cyan
Write-Host "==========================" -ForegroundColor Cyan

# Create timestamp for backup
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupDir = Join-Path $BackupPath "midas-backup-$timestamp"

# Create backup directory
if (-not (Test-Path $BackupPath)) {
    New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
}

if (-not $CompressOnly) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Write-Host "`nBackup directory: $backupDir" -ForegroundColor Yellow
}

# Check if services are running
$running = docker-compose ps --services --filter "status=running" 2>$null
if ($running) {
    Write-Host "`nWARNING: Services are running. For consistent backups, consider stopping services first." -ForegroundColor Yellow
    $continue = Read-Host "Continue anyway? (y/N)"
    if ($continue -ne 'y') {
        exit 0
    }
}

if (-not $CompressOnly) {
    # Backup PostgreSQL
    Write-Host "`nBacking up PostgreSQL database..." -ForegroundColor Yellow
    try {
        # Get database credentials from .env
        $env = Get-Content .env | Where-Object { $_ -match "^[^#].*=" } | ForEach-Object {
            $parts = $_.Split('=', 2)
            @{ $parts[0].Trim() = $parts[1].Trim() }
        }
        
        $dbName = if ($env.POSTGRES_DB) { $env.POSTGRES_DB } else { "midas" }
        $dbUser = if ($env.POSTGRES_USER) { $env.POSTGRES_USER } else { "midas_user" }
        
        # Create database dump
        docker-compose exec -T postgres pg_dump -U $dbUser -d $dbName > "$backupDir/postgres-dump.sql"
        Write-Host "  PostgreSQL backup completed" -ForegroundColor Green
    } catch {
        Write-Host "  PostgreSQL backup failed: $_" -ForegroundColor Red
    }

    # Backup Redis
    Write-Host "`nBacking up Redis data..." -ForegroundColor Yellow
    try {
        docker-compose exec -T redis redis-cli BGSAVE
        Start-Sleep -Seconds 2
        docker cp midas-redis:/data/dump.rdb "$backupDir/redis-dump.rdb"
        Write-Host "  Redis backup completed" -ForegroundColor Green
    } catch {
        Write-Host "  Redis backup failed: $_" -ForegroundColor Red
    }

    # Backup Qdrant
    Write-Host "`nBacking up Qdrant vector database..." -ForegroundColor Yellow
    $qdrantSource = "volumes/qdrant-storage"
    if (Test-Path $qdrantSource) {
        $qdrantDest = Join-Path $backupDir "qdrant-storage"
        Copy-Item -Path $qdrantSource -Destination $qdrantDest -Recurse
        Write-Host "  Qdrant backup completed" -ForegroundColor Green
    } else {
        Write-Host "  Qdrant data not found" -ForegroundColor Yellow
    }

    # Backup Streamlit AppData
    Write-Host "`nBacking up Streamlit AppData..." -ForegroundColor Yellow
    $streamlitSource = "volumes/streamlit-appdata"
    if (Test-Path $streamlitSource) {
        $streamlitDest = Join-Path $backupDir "streamlit-appdata"
        Copy-Item -Path $streamlitSource -Destination $streamlitDest -Recurse
        Write-Host "  Streamlit AppData backup completed" -ForegroundColor Green
    } else {
        Write-Host "  Streamlit AppData not found" -ForegroundColor Yellow
    }

    # Optionally backup Ollama models
    if ($IncludeModels) {
        Write-Host "`nBacking up Ollama models (this may take a while)..." -ForegroundColor Yellow
        $ollamaSource = "volumes/ollama-models"
        if (Test-Path $ollamaSource) {
            $ollamaDest = Join-Path $backupDir "ollama-models"
            Copy-Item -Path $ollamaSource -Destination $ollamaDest -Recurse
            Write-Host "  Ollama models backup completed" -ForegroundColor Green
        } else {
            Write-Host "  Ollama models not found" -ForegroundColor Yellow
        }
    }

    # Backup configuration files
    Write-Host "`nBacking up configuration files..." -ForegroundColor Yellow
    $configFiles = @(
        ".env",
        "docker-compose.yml",
        "nginx/nginx.conf",
        "nginx/conf.d",
        "redis/redis.conf",
        "postgres/init"
    )

    $configDest = Join-Path $backupDir "config"
    New-Item -ItemType Directory -Path $configDest -Force | Out-Null

    foreach ($file in $configFiles) {
        if (Test-Path $file) {
            $dest = Join-Path $configDest $file
            $destDir = Split-Path $dest -Parent
            if (-not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Copy-Item -Path $file -Destination $dest -Recurse -Force
        }
    }
    Write-Host "  Configuration backup completed" -ForegroundColor Green
}

# Compress backup
Write-Host "`nCompressing backup..." -ForegroundColor Yellow
$archivePath = Join-Path $BackupPath "midas-backup-$timestamp.zip"

if ($CompressOnly) {
    # Find the most recent backup directory
    $backupDir = Get-ChildItem -Path $BackupPath -Directory | 
                 Where-Object { $_.Name -like "midas-backup-*" } | 
                 Sort-Object LastWriteTime -Descending | 
                 Select-Object -First 1
    
    if (-not $backupDir) {
        Write-Host "No backup directory found to compress" -ForegroundColor Red
        exit 1
    }
    $backupDir = $backupDir.FullName
}

try {
    Compress-Archive -Path "$backupDir/*" -DestinationPath $archivePath -CompressionLevel Optimal
    Write-Host "  Backup compressed to: $archivePath" -ForegroundColor Green
    
    # Calculate sizes
    $backupSize = (Get-Item $archivePath).Length / 1MB
    Write-Host "  Compressed size: $([math]::Round($backupSize, 2)) MB" -ForegroundColor Gray
    
    # Remove uncompressed backup directory
    if (-not $CompressOnly) {
        Remove-Item -Path $backupDir -Recurse -Force
        Write-Host "  Cleaned up temporary files" -ForegroundColor Gray
    }
} catch {
    Write-Host "  Compression failed: $_" -ForegroundColor Red
}

# Clean up old backups (keep last 7 by default)
Write-Host "`nCleaning up old backups..." -ForegroundColor Yellow
$keepCount = 7
$backups = Get-ChildItem -Path $BackupPath -Filter "midas-backup-*.zip" | 
           Sort-Object LastWriteTime -Descending

if ($backups.Count -gt $keepCount) {
    $toDelete = $backups | Select-Object -Skip $keepCount
    foreach ($backup in $toDelete) {
        Remove-Item $backup.FullName -Force
        Write-Host "  Removed old backup: $($backup.Name)" -ForegroundColor Gray
    }
}

Write-Host "`nBackup completed successfully!" -ForegroundColor Green
Write-Host "Backup location: $archivePath" -ForegroundColor Cyan