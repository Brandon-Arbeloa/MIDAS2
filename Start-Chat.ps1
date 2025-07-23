# Start-Chat.ps1
# Launch MIDAS Streamlit Chat Application with Windows optimizations
# Usage: .\Start-Chat.ps1 [-Port 8501] [-Host localhost] [-Debug]

param(
    [string]$Port = "8501",
    [string]$Host = "localhost", 
    [switch]$Debug = $false,
    [switch]$Headless = $true
)

Write-Host "=== MIDAS RAG Chat Application Launcher ===" -ForegroundColor Green
Write-Host "Starting Streamlit chat interface..." -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "✅ Python available: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please ensure Python is installed and in PATH." -ForegroundColor Red
    exit 1
}

# Check if virtual environment is activated
$venvPath = "C:\Users\Rolando Fender\MIDAS\rag_env\Scripts\activate"
if (Test-Path $venvPath) {
    Write-Host "🐍 Activating virtual environment..." -ForegroundColor Yellow
    & $venvPath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Virtual environment activated" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Virtual environment activation failed, continuing..." -ForegroundColor Yellow
    }
} else {
    Write-Host "⚠️  Virtual environment not found, using system Python" -ForegroundColor Yellow
}

# Check dependencies
Write-Host "📦 Checking dependencies..." -ForegroundColor Cyan

$requiredPackages = @("streamlit", "ollama", "requests")
$missingPackages = @()

foreach ($package in $requiredPackages) {
    try {
        python -c "import $package" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ $package available" -ForegroundColor Green
        } else {
            $missingPackages += $package
        }
    } catch {
        $missingPackages += $package
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host "❌ Missing packages: $($missingPackages -join ', ')" -ForegroundColor Red
    Write-Host "💡 Install with: pip install $($missingPackages -join ' ')" -ForegroundColor Yellow
    
    $install = Read-Host "Install missing packages now? (Y/n)"
    if ($install -eq '' -or $install -eq 'Y' -or $install -eq 'y') {
        Write-Host "📦 Installing missing packages..." -ForegroundColor Yellow
        pip install $missingPackages
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Package installation failed" -ForegroundColor Red
            exit 1
        }
        Write-Host "✅ Packages installed successfully" -ForegroundColor Green
    } else {
        Write-Host "❌ Cannot proceed without required packages" -ForegroundColor Red
        exit 1
    }
}

# Check service dependencies
Write-Host "`n🔧 Checking service dependencies..." -ForegroundColor Cyan

# Check Ollama
try {
    $ollamaResponse = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ✅ Ollama service running" -ForegroundColor Green
    
    $models = $ollamaResponse.models
    if ($models -and $models.Count -gt 0) {
        Write-Host "   📚 Available models:" -ForegroundColor Gray
        foreach ($model in $models[0..2]) {  # Show first 3 models
            Write-Host "      - $($model.name)" -ForegroundColor Gray
        }
        if ($models.Count -gt 3) {
            Write-Host "      ... and $($models.Count - 3) more" -ForegroundColor Gray
        }
    } else {
        Write-Host "   ⚠️  No models available. Run: ollama pull llama3.2:3b" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Ollama not accessible on localhost:11434" -ForegroundColor Red
    Write-Host "   💡 Start with: .\Setup-Ollama.ps1 or 'ollama serve'" -ForegroundColor Yellow
}

# Check Qdrant
try {
    $qdrantResponse = Invoke-RestMethod -Uri "http://localhost:6333/collections" -Method Get -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ✅ Qdrant service running" -ForegroundColor Green
    
    $collections = $qdrantResponse.result.collections
    if ($collections -and $collections.Count -gt 0) {
        Write-Host "   📦 Available collections:" -ForegroundColor Gray
        foreach ($collection in $collections) {
            Write-Host "      - $($collection.name)" -ForegroundColor Gray
        }
    } else {
        Write-Host "   ⚠️  No collections found. Index some documents first." -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Qdrant not accessible on localhost:6333" -ForegroundColor Red
    Write-Host "   💡 Start with: .\Setup-Qdrant.ps1" -ForegroundColor Yellow
}

# Create logs directory
$logsDir = "C:\MIDAS\logs"
if (!(Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    Write-Host "📁 Created logs directory: $logsDir" -ForegroundColor Green
}

# Prepare Streamlit arguments
$streamlitArgs = @(
    "run", "chat_app.py"
    "--server.port", $Port
    "--server.address", $Host
    "--server.fileWatcherType", "none"  # Windows optimization
    "--browser.gatherUsageStats", "false"
    "--global.developmentMode", $Debug.ToString().ToLower()
)

if ($Headless) {
    $streamlitArgs += "--server.headless", "true"
}

if ($Debug) {
    $streamlitArgs += "--logger.level", "debug"
}

# Launch application
Write-Host "`n🚀 Starting MIDAS Chat Application..." -ForegroundColor Green
Write-Host "📍 URL: http://${Host}:${Port}" -ForegroundColor White
Write-Host "⏹️  Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Set Windows-specific environment variables
$env:STREAMLIT_SERVER_HEADLESS = "true"
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
$env:STREAMLIT_SERVER_FILE_WATCHER_TYPE = "none"

# Change to application directory
$originalLocation = Get-Location
Set-Location "C:\Users\Rolando Fender\MIDAS"

try {
    # Launch Streamlit with Windows optimizations
    if ($Debug) {
        Write-Host "🐛 Debug mode enabled - verbose output" -ForegroundColor Yellow
        Write-Host "Command: streamlit $($streamlitArgs -join ' ')" -ForegroundColor Gray
    }
    
    # Start the application
    & streamlit @streamlitArgs
    
} catch {
    Write-Host "❌ Failed to start application: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    # Restore original location
    Set-Location $originalLocation
    Write-Host "`n🛑 Application stopped" -ForegroundColor Yellow
}

Write-Host "`n📊 Session Summary:" -ForegroundColor Cyan
Write-Host "   Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "   URL: http://${Host}:${Port}" -ForegroundColor Gray
Write-Host "   Logs: $logsDir" -ForegroundColor Gray

Write-Host "`n💡 Troubleshooting:" -ForegroundColor Yellow
Write-Host "   • Ensure Ollama is running: ollama serve" -ForegroundColor Gray
Write-Host "   • Ensure Qdrant is running: .\Setup-Qdrant.ps1" -ForegroundColor Gray
Write-Host "   • Check logs in: $logsDir" -ForegroundColor Gray
Write-Host "   • For help: streamlit run chat_app.py --help" -ForegroundColor Gray