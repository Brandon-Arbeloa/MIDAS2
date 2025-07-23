# Start Celery Services for MIDAS
# This script starts all required Celery components for background processing

Write-Host "Starting MIDAS Celery Services..." -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Cyan

# Check if Redis is running
$redisService = Get-Service -Name "Redis" -ErrorAction SilentlyContinue
if ($redisService) {
    if ($redisService.Status -ne 'Running') {
        Write-Host "Starting Redis service..." -ForegroundColor Yellow
        Start-Service -Name "Redis"
        Start-Sleep -Seconds 2
    }
    Write-Host "✅ Redis is running" -ForegroundColor Green
} else {
    Write-Host "❌ Redis service not found. Please run Setup-Redis-Windows.ps1 first" -ForegroundColor Red
    exit 1
}

# Set Python path
$pythonPath = (Get-Command python).Source
Write-Host "Using Python: $pythonPath" -ForegroundColor Cyan

# Create logs directory
$logsDir = Join-Path $PSScriptRoot "logs"
if (!(Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}

# Function to start a process in a new window
function Start-CeleryProcess {
    param(
        [string]$Name,
        [string]$Arguments,
        [string]$LogFile
    )
    
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "cmd.exe"
    $processInfo.Arguments = "/k title $Name && cd /d `"$PSScriptRoot`" && $pythonPath $Arguments 2>&1 | tee `"$LogFile`""
    $processInfo.UseShellExecute = $true
    $processInfo.CreateNoWindow = $false
    
    $process = [System.Diagnostics.Process]::Start($processInfo)
    Write-Host "✅ Started $Name (PID: $($process.Id))" -ForegroundColor Green
    
    return $process
}

# Start Celery Worker
Write-Host "`nStarting Celery Worker..." -ForegroundColor Yellow
$workerLog = Join-Path $logsDir "celery_worker.log"
$workerProcess = Start-CeleryProcess `
    -Name "MIDAS Celery Worker" `
    -Arguments "-m celery -A celery_config worker --loglevel=info --pool=solo --concurrency=1 -Q default,documents,analysis,monitoring -n midas-worker@%h" `
    -LogFile $workerLog

Start-Sleep -Seconds 3

# Start Celery Beat (Scheduler)
Write-Host "`nStarting Celery Beat..." -ForegroundColor Yellow
$beatLog = Join-Path $logsDir "celery_beat.log"
$beatProcess = Start-CeleryProcess `
    -Name "MIDAS Celery Beat" `
    -Arguments "-m celery -A celery_config beat --loglevel=info" `
    -LogFile $beatLog

Start-Sleep -Seconds 2

# Start Flower (Monitoring)
Write-Host "`nStarting Flower (Web Monitoring)..." -ForegroundColor Yellow
$flowerLog = Join-Path $logsDir "celery_flower.log"
$flowerProcess = Start-CeleryProcess `
    -Name "MIDAS Celery Flower" `
    -Arguments "-m flower -A celery_config --port=5555 --url_prefix=flower" `
    -LogFile $flowerLog

Start-Sleep -Seconds 2

# Start File Watcher
Write-Host "`nStarting File Watcher..." -ForegroundColor Yellow
$watcherLog = Join-Path $logsDir "file_watcher.log"
$watcherProcess = Start-CeleryProcess `
    -Name "MIDAS File Watcher" `
    -Arguments "-m background_tasks.file_watcher" `
    -LogFile $watcherLog

Write-Host "`n=================================" -ForegroundColor Cyan
Write-Host "All Celery services started successfully!" -ForegroundColor Green
Write-Host "`nService URLs:" -ForegroundColor Yellow
Write-Host "  - Flower Web UI: http://localhost:5555/flower" -ForegroundColor Cyan
Write-Host "  - Task Monitoring: Run 'streamlit run Streamlit_Task_Monitoring.py'" -ForegroundColor Cyan

Write-Host "`nLog files location: $logsDir" -ForegroundColor Yellow
Write-Host "`nPress Ctrl+C in each window to stop services" -ForegroundColor Yellow

# Create stop script
$stopScript = @'
# Stop all Celery services
Write-Host "Stopping MIDAS Celery Services..." -ForegroundColor Red

# Find and stop processes by window title
$processes = @("MIDAS Celery Worker", "MIDAS Celery Beat", "MIDAS Celery Flower", "MIDAS File Watcher")

foreach ($procName in $processes) {
    $proc = Get-Process | Where-Object { $_.MainWindowTitle -like "*$procName*" }
    if ($proc) {
        Write-Host "Stopping $procName..." -ForegroundColor Yellow
        $proc | Stop-Process -Force
    }
}

Write-Host "All services stopped." -ForegroundColor Green
'@

$stopScriptPath = Join-Path $PSScriptRoot "Stop-Celery-Services.ps1"
$stopScript | Out-File -FilePath $stopScriptPath -Encoding UTF8
Write-Host "`nStop script created: $stopScriptPath" -ForegroundColor Green

# Test Celery connection
Write-Host "`nTesting Celery connection..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$testScript = @"
import sys
sys.path.append('$PSScriptRoot')
from celery_config import test_celery_connection
test_celery_connection()
"@

$testScript | & $pythonPath

Write-Host "`nSetup complete!" -ForegroundColor Green