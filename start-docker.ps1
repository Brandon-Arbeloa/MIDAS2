# MIDAS Docker Startup Script for Windows
# Ensures all required directories and files exist before starting

Write-Host "MIDAS Docker Deployment Startup Script" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan

# Check if Docker Desktop is running
$docker = Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "Docker Desktop is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Create required directories
Write-Host "`nCreating required directories..." -ForegroundColor Yellow

$directories = @(
    "volumes/ollama-models",
    "volumes/qdrant-storage",
    "volumes/postgres-data",
    "volumes/redis-data",
    "volumes/streamlit-appdata",
    "volumes/celery-logs",
    "volumes/celery-beat-schedule",
    "volumes/nginx-cache",
    "volumes/nginx-logs",
    "postgres/backups",
    "backups",
    "data",
    "nginx/ssl",
    "ollama/models",
    "qdrant/config"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Green
    } else {
        Write-Host "  Exists: $dir" -ForegroundColor Gray
    }
}

# Check for secrets
Write-Host "`nChecking secrets..." -ForegroundColor Yellow

$secrets = @(
    "secrets/postgres_password.txt",
    "secrets/app_secret_key.txt"
)

$missing_secrets = $false
foreach ($secret in $secrets) {
    if (-not (Test-Path $secret)) {
        Write-Host "  Missing: $secret" -ForegroundColor Red
        $missing_secrets = $true
    } else {
        Write-Host "  Found: $secret" -ForegroundColor Green
    }
}

if ($missing_secrets) {
    Write-Host "`nPlease create the missing secret files. See secrets/README.md for instructions." -ForegroundColor Red
    exit 1
}

# Check for .env file
Write-Host "`nChecking environment configuration..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  Created .env from .env.example" -ForegroundColor Green
        Write-Host "  Please edit .env with your configuration" -ForegroundColor Yellow
    } else {
        Write-Host "  Missing .env file" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  Found .env file" -ForegroundColor Green
}

# Create default Qdrant config if not exists
$qdrantConfig = "qdrant/config/config.yaml"
if (-not (Test-Path $qdrantConfig)) {
    @"
storage:
  storage_path: /qdrant/storage
  wal:
    wal_capacity_mb: 256
  optimizers:
    memmap_threshold_kb: 200000

service:
  http_port: 6333
  grpc_port: 6334

log_level: INFO
"@ | Out-File -FilePath $qdrantConfig -Encoding utf8
    Write-Host "  Created default Qdrant configuration" -ForegroundColor Green
}

# Pull latest images
Write-Host "`nPulling Docker images..." -ForegroundColor Yellow
docker-compose pull

# Build custom images
Write-Host "`nBuilding custom Docker images..." -ForegroundColor Yellow
docker-compose build

# Start services
Write-Host "`nStarting MIDAS services..." -ForegroundColor Yellow

# Start infrastructure services first
Write-Host "  Starting infrastructure services..." -ForegroundColor Gray
docker-compose up -d postgres redis qdrant ollama

# Wait for services to be healthy
Write-Host "  Waiting for infrastructure services to be ready..." -ForegroundColor Gray
Start-Sleep -Seconds 10

# Check service health
$services = @("postgres", "redis", "qdrant", "ollama")
foreach ($service in $services) {
    $health = docker inspect --format='{{.State.Health.Status}}' "midas-$service" 2>$null
    if ($health -eq "healthy") {
        Write-Host "    $service is healthy" -ForegroundColor Green
    } else {
        Write-Host "    $service is not ready yet" -ForegroundColor Yellow
    }
}

# Start application services
Write-Host "  Starting application services..." -ForegroundColor Gray
docker-compose up -d

# Show service status
Write-Host "`nService Status:" -ForegroundColor Yellow
docker-compose ps

# Display access URLs
Write-Host "`nAccess URLs:" -ForegroundColor Cyan
Write-Host "  Streamlit App:    http://localhost:8501" -ForegroundColor Green
Write-Host "  Flower Monitor:   http://localhost:5555" -ForegroundColor Green
Write-Host "  Ollama API:       http://localhost:11434" -ForegroundColor Green
Write-Host "  Qdrant API:       http://localhost:6333" -ForegroundColor Green
Write-Host "  PostgreSQL:       localhost:5432" -ForegroundColor Green
Write-Host "  Redis:            localhost:6379" -ForegroundColor Green

Write-Host "`nTo view logs: docker-compose logs -f [service-name]" -ForegroundColor Gray
Write-Host "To stop all services: docker-compose down" -ForegroundColor Gray
Write-Host "To stop and remove volumes: docker-compose down -v" -ForegroundColor Gray