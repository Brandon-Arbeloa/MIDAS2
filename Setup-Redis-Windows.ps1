# Setup Redis for Windows 11
# This script downloads and configures Redis for Windows

Write-Host "Setting up Redis for Windows..." -ForegroundColor Green

# Create Redis directory
$redisPath = "C:\Redis"
if (!(Test-Path $redisPath)) {
    New-Item -ItemType Directory -Path $redisPath -Force
    Write-Host "Created Redis directory at $redisPath" -ForegroundColor Yellow
}

# Download Redis for Windows (using Memurai as alternative)
$downloadUrl = "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.msi"
$installerPath = "$env:TEMP\redis-installer.msi"

Write-Host "Downloading Redis for Windows..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath
    Write-Host "Redis downloaded successfully" -ForegroundColor Green
} catch {
    Write-Host "Failed to download Redis. Please download manually from:" -ForegroundColor Red
    Write-Host $downloadUrl -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Alternative: Install Memurai (Redis for Windows) from https://www.memurai.com" -ForegroundColor Yellow
    exit 1
}

# Install Redis
Write-Host "Installing Redis..." -ForegroundColor Yellow
Start-Process msiexec.exe -ArgumentList "/i", $installerPath, "/quiet" -Wait

# Create Redis configuration for Windows
$redisConfig = @"
# Redis configuration for Windows
bind 127.0.0.1
port 6379
timeout 0
tcp-keepalive 300
databases 16
save 900 1
save 300 10
save 60 10000
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb
dir C:\Redis\data
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
no-appendfsync-on-rewrite no
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
maxmemory 256mb
maxmemory-policy allkeys-lru
"@

# Save configuration
$configPath = "$redisPath\redis.windows.conf"
$redisConfig | Out-File -FilePath $configPath -Encoding UTF8
Write-Host "Redis configuration saved to $configPath" -ForegroundColor Green

# Create data directory
$dataPath = "$redisPath\data"
if (!(Test-Path $dataPath)) {
    New-Item -ItemType Directory -Path $dataPath -Force
}

# Create Windows service for Redis
Write-Host "Creating Redis Windows service..." -ForegroundColor Yellow
$serviceName = "Redis"
$redisServerPath = "C:\Program Files\Redis\redis-server.exe"

if (Test-Path $redisServerPath) {
    sc.exe create $serviceName binPath= "$redisServerPath $configPath" start= auto
    Write-Host "Redis service created" -ForegroundColor Green
    
    # Start the service
    Start-Service -Name $serviceName
    Write-Host "Redis service started" -ForegroundColor Green
} else {
    Write-Host "Redis server not found at expected location" -ForegroundColor Red
    Write-Host "Please verify installation path" -ForegroundColor Yellow
}

# Test Redis connection
Write-Host "`nTesting Redis connection..." -ForegroundColor Yellow
$redisCliPath = "C:\Program Files\Redis\redis-cli.exe"
if (Test-Path $redisCliPath) {
    & $redisCliPath ping
} else {
    Write-Host "Redis CLI not found. Please verify installation." -ForegroundColor Red
}

Write-Host "`nRedis setup complete!" -ForegroundColor Green
Write-Host "Redis is running on localhost:6379" -ForegroundColor Cyan