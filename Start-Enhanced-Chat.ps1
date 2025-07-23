# Start-Enhanced-Chat.ps1
# Launch MIDAS Enhanced Streamlit Chat Application with full Windows integration
# Usage: .\Start-Enhanced-Chat.ps1 [-Port 8501] [-Host localhost] [-Debug] [-RunTests]

param(
    [string]$Port = "8501",
    [string]$Host = "localhost", 
    [switch]$Debug = $false,
    [switch]$Headless = $true,
    [switch]$RunTests = $false,
    [switch]$SkipDependencyCheck = $false
)

Write-Host "=== MIDAS Enhanced RAG Chat Application ===" -ForegroundColor Green
Write-Host "Starting enhanced Streamlit interface with full Windows integration..." -ForegroundColor Cyan
Write-Host ""

# Check Windows version and compatibility
$windowsVersion = [System.Environment]::OSVersion.Version
Write-Host "🖥️  Windows Version: $($windowsVersion.Major).$($windowsVersion.Minor)" -ForegroundColor Gray

if ($windowsVersion.Major -lt 10) {
    Write-Host "⚠️  Warning: Windows 10+ recommended for optimal performance" -ForegroundColor Yellow
}

# System specs detection
Write-Host "💻 Detecting system capabilities..." -ForegroundColor Cyan

try {
    $totalMemory = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $cpuCores = (Get-CimInstance Win32_ComputerSystem).NumberOfProcessors
    $cpuName = (Get-CimInstance Win32_Processor).Name
    
    Write-Host "   CPU: $cpuName ($cpuCores cores)" -ForegroundColor Gray
    Write-Host "   RAM: ${totalMemory} GB" -ForegroundColor Gray
    
    # Memory recommendations
    if ($totalMemory -lt 8) {
        Write-Host "   ⚠️  Warning: Less than 8GB RAM detected - performance may be limited" -ForegroundColor Yellow
        Write-Host "   💡 Recommendation: Use smaller models (phi3:mini)" -ForegroundColor Yellow
    } elseif ($totalMemory -ge 16) {
        Write-Host "   ✅ Excellent RAM capacity for optimal performance" -ForegroundColor Green
    } else {
        Write-Host "   ✅ Good RAM capacity for standard operation" -ForegroundColor Green
    }
} catch {
    Write-Host "   ⚠️  Could not detect system specs" -ForegroundColor Yellow
}

# Check CUDA availability
Write-Host "`n🖥️  Checking GPU capabilities..." -ForegroundColor Cyan
try {
    $gpuInfo = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
    if ($gpuInfo) {
        Write-Host "   🎮 NVIDIA GPU detected: $($gpuInfo.Name)" -ForegroundColor Green
        Write-Host "   💡 CUDA may be available for accelerated inference" -ForegroundColor Green
    } else {
        Write-Host "   🔧 No NVIDIA GPU detected - using CPU inference" -ForegroundColor Gray
    }
} catch {
    Write-Host "   🔧 GPU detection failed - will use CPU" -ForegroundColor Gray
}

# Python environment check
Write-Host "`n🐍 Checking Python environment..." -ForegroundColor Cyan
try {
    $pythonVersion = python --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "   ✅ Python available: $pythonVersion" -ForegroundColor Green
    
    # Check if we're in the right directory
    $currentDir = Get-Location
    $expectedDir = "C:\Users\Rolando Fender\MIDAS"
    
    if ($currentDir.Path -ne $expectedDir) {
        Write-Host "   📁 Changing to MIDAS directory..." -ForegroundColor Yellow
        Set-Location $expectedDir
    }
    
} catch {
    Write-Host "   ❌ Python not found. Please ensure Python is installed and in PATH." -ForegroundColor Red
    exit 1
}

# Virtual environment activation
$venvPath = "rag_env\Scripts\activate"
if (Test-Path $venvPath) {
    Write-Host "   🔧 Activating virtual environment..." -ForegroundColor Yellow
    & $venvPath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Virtual environment activated" -ForegroundColor Green
    }
} else {
    Write-Host "   ⚠️  Virtual environment not found at $venvPath" -ForegroundColor Yellow
}

# Enhanced dependency check
if (-not $SkipDependencyCheck) {
    Write-Host "`n📦 Checking enhanced dependencies..." -ForegroundColor Cyan
    
    $enhancedPackages = @(
        @{Name="streamlit"; MinVersion="1.47.0"},
        @{Name="ollama"; MinVersion="0.5.0"},
        @{Name="torch"; MinVersion="2.0.0"},
        @{Name="sentence-transformers"; MinVersion="5.0.0"},
        @{Name="qdrant-client"; MinVersion="1.15.0"},
        @{Name="requests"; MinVersion="2.32.0"},
        @{Name="psutil"; MinVersion="5.9.0"}
    )
    
    $missingPackages = @()
    
    foreach ($package in $enhancedPackages) {
        try {
            $result = python -c "import $($package.Name); print($($package.Name).__version__)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   ✅ $($package.Name): $result" -ForegroundColor Green
            } else {
                $missingPackages += $package.Name
            }
        } catch {
            $missingPackages += $package.Name
        }
    }
    
    if ($missingPackages.Count -gt 0) {
        Write-Host "   ❌ Missing packages: $($missingPackages -join ', ')" -ForegroundColor Red
        
        $install = Read-Host "Install missing packages? (Y/n)"
        if ($install -eq '' -or $install -eq 'Y' -or $install -eq 'y') {
            Write-Host "   📦 Installing missing packages..." -ForegroundColor Yellow
            pip install $missingPackages psutil
            
            if ($LASTEXITCODE -ne 0) {
                Write-Host "   ❌ Package installation failed" -ForegroundColor Red
                exit 1
            }
        }
    } else {
        Write-Host "   ✅ All enhanced dependencies available" -ForegroundColor Green
    }
}

# Service availability check
Write-Host "`n🔧 Checking service dependencies..." -ForegroundColor Cyan

# Enhanced Ollama check with model verification
try {
    $ollamaResponse = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ✅ Ollama service running on port 11434" -ForegroundColor Green
    
    $models = $ollamaResponse.models
    if ($models -and $models.Count -gt 0) {
        Write-Host "   📚 Available models:" -ForegroundColor Gray
        foreach ($model in $models[0..2]) {
            $sizeGB = [math]::Round($model.size / 1GB, 1)
            Write-Host "      • $($model.name) (${sizeGB}GB)" -ForegroundColor Gray
        }
        if ($models.Count -gt 3) {
            Write-Host "      • ... and $($models.Count - 3) more models" -ForegroundColor Gray
        }
    } else {
        Write-Host "   ⚠️  No models available. Recommended models:" -ForegroundColor Yellow
        Write-Host "      • ollama pull llama3.2:3b (lightweight)" -ForegroundColor Gray
        Write-Host "      • ollama pull phi3:mini (very fast)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ❌ Ollama not accessible on localhost:11434" -ForegroundColor Red
    Write-Host "   💡 Start with: ollama serve" -ForegroundColor Yellow
    Write-Host "   💡 Or run: .\Setup-Ollama.ps1" -ForegroundColor Yellow
}

# Enhanced Qdrant check with collection details
try {
    $qdrantResponse = Invoke-RestMethod -Uri "http://localhost:6333/collections" -Method Get -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ✅ Qdrant service running on port 6333" -ForegroundColor Green
    
    $collections = $qdrantResponse.result.collections
    if ($collections -and $collections.Count -gt 0) {
        Write-Host "   📦 Available collections:" -ForegroundColor Gray
        foreach ($collection in $collections) {
            # Get collection details
            try {
                $collectionDetails = Invoke-RestMethod -Uri "http://localhost:6333/collections/$($collection.name)" -Method Get -TimeoutSec 3
                $pointCount = $collectionDetails.result.points_count
                Write-Host "      • $($collection.name) ($pointCount points)" -ForegroundColor Gray
            } catch {
                Write-Host "      • $($collection.name)" -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "   ⚠️  No collections found" -ForegroundColor Yellow
        Write-Host "   💡 Index documents first using document_indexer.py" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Qdrant not accessible on localhost:6333" -ForegroundColor Red
    Write-Host "   💡 Start with: .\Setup-Qdrant.ps1" -ForegroundColor Yellow
}

# Run integration tests if requested
if ($RunTests) {
    Write-Host "`n🧪 Running integration tests..." -ForegroundColor Cyan
    try {
        python test_enhanced_integration.py
    } catch {
        Write-Host "   ⚠️  Integration test failed - continuing anyway" -ForegroundColor Yellow
    }
}

# Create necessary directories
$requiredDirs = @("C:\MIDAS\logs", "C:\MIDAS\config", "C:\MIDAS\temp")
foreach ($dir in $requiredDirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "📁 Created directory: $dir" -ForegroundColor Green
    }
}

# Prepare enhanced Streamlit arguments
$streamlitArgs = @(
    "run", "enhanced_chat_app.py"
    "--server.port", $Port
    "--server.address", $Host
    "--server.fileWatcherType", "none"
    "--browser.gatherUsageStats", "false"
    "--global.developmentMode", $Debug.ToString().ToLower()
    "--theme.base", "light"
    "--theme.primaryColor", "#1f77b4"
)

if ($Headless) {
    $streamlitArgs += "--server.headless", "true"
}

if ($Debug) {
    $streamlitArgs += "--logger.level", "debug"
}

# Set enhanced environment variables
$env:STREAMLIT_SERVER_HEADLESS = "true"
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
$env:STREAMLIT_SERVER_FILE_WATCHER_TYPE = "none"
$env:MIDAS_ENHANCED_MODE = "true"
$env:MIDAS_LOG_LEVEL = if ($Debug) { "DEBUG" } else { "INFO" }

# Pre-flight check summary
Write-Host "`n🚀 Pre-flight Check Summary:" -ForegroundColor Green
Write-Host "   📍 URL: http://${Host}:${Port}" -ForegroundColor White
Write-Host "   🧠 Memory: ${totalMemory} GB RAM available" -ForegroundColor White
Write-Host "   🔧 Mode: $(if ($Debug) { 'Debug' } else { 'Production' })" -ForegroundColor White
Write-Host "   📊 Enhanced features: Conversation memory, debugging, Windows integration" -ForegroundColor White

# Launch enhanced application
Write-Host "`n🚀 Starting MIDAS Enhanced Chat Application..." -ForegroundColor Green
Write-Host "⏹️  Press Ctrl+C to stop the application" -ForegroundColor Yellow
Write-Host ""

try {
    if ($Debug) {
        Write-Host "🐛 Debug mode enabled - verbose logging active" -ForegroundColor Yellow
        Write-Host "Command: streamlit $($streamlitArgs -join ' ')" -ForegroundColor Gray
    }
    
    # Start the enhanced application
    & streamlit @streamlitArgs
    
} catch {
    Write-Host "❌ Failed to start enhanced application: $($_.Exception.Message)" -ForegroundColor Red
} finally {
    Write-Host "`n🛑 Enhanced chat application stopped" -ForegroundColor Yellow
}

# Session summary
Write-Host "`n📊 Enhanced Session Summary:" -ForegroundColor Cyan
Write-Host "   Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "   URL: http://${Host}:${Port}" -ForegroundColor Gray
Write-Host "   System: ${totalMemory}GB RAM, $cpuCores cores" -ForegroundColor Gray
Write-Host "   Features: Enhanced RAG, Conversation Memory, Windows Integration" -ForegroundColor Gray
Write-Host "   Logs: C:\MIDAS\logs\" -ForegroundColor Gray

Write-Host "`n💡 Enhanced Troubleshooting:" -ForegroundColor Yellow
Write-Host "   • Service Status: .\Test-Ollama.ps1 and .\QdrantData\Test-Qdrant.ps1" -ForegroundColor Gray
Write-Host "   • Integration Test: .\Start-Enhanced-Chat.ps1 -RunTests" -ForegroundColor Gray
Write-Host "   • Debug Mode: .\Start-Enhanced-Chat.ps1 -Debug" -ForegroundColor Gray
Write-Host "   • Skip Dependency Check: .\Start-Enhanced-Chat.ps1 -SkipDependencyCheck" -ForegroundColor Gray
Write-Host "   • View Logs: Get-Content C:\MIDAS\logs\*.log -Tail 50" -ForegroundColor Gray

Write-Host "`n🎯 Enhanced Features Available:" -ForegroundColor Green
Write-Host "   ✅ Automatic Windows CUDA/CPU detection" -ForegroundColor Gray
Write-Host "   ✅ Conversation memory with context awareness" -ForegroundColor Gray
Write-Host "   ✅ Clickable Windows file paths in results" -ForegroundColor Gray
Write-Host "   ✅ Real-time debugging panel for search operations" -ForegroundColor Gray
Write-Host "   ✅ System-optimized settings based on RAM/CPU" -ForegroundColor Gray
Write-Host "   ✅ Enhanced Unicode and special character handling" -ForegroundColor Gray

Write-Host "`n🎉 Enhanced MIDAS RAG system ready for advanced usage!" -ForegroundColor Green