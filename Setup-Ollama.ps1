# Setup-Ollama.ps1
# Complete Ollama setup script for Windows 11 with NSSM service configuration
# Run as Administrator for service installation
# Usage: .\Setup-Ollama.ps1 -InstallModels -CreateService

param(
    [switch]$InstallModels = $false,
    [switch]$CreateService = $false,
    [switch]$OptimizeForRAM = $true,
    [string]$WorkingDirectory = "C:\Ollama",
    [string]$ServiceName = "OllamaService"
)

# Check if running as Administrator for service installation
if ($CreateService -and -not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ Administrator privileges required for service installation." -ForegroundColor Red
    Write-Host "💡 Re-run PowerShell as Administrator or omit -CreateService flag" -ForegroundColor Yellow
    exit 1
}

Write-Host "=== Ollama Setup for Windows 11 ===" -ForegroundColor Green
Write-Host "Working Directory: $WorkingDirectory" -ForegroundColor Yellow
Write-Host "Install Models: $InstallModels" -ForegroundColor Yellow
Write-Host "Create Service: $CreateService" -ForegroundColor Yellow
Write-Host ""

# Create working directory
Write-Host "📁 Creating working directory..." -ForegroundColor Cyan
try {
    New-Item -ItemType Directory -Path $WorkingDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path "$WorkingDirectory\logs" -Force | Out-Null
    Write-Host "✅ Directory created: $WorkingDirectory" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to create directory: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 1: Check if Ollama is already installed
Write-Host "`n1. Checking Ollama Installation..." -ForegroundColor Cyan
$ollamaInstalled = $false
try {
    $version = & ollama --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Ollama already installed: $version" -ForegroundColor Green
        $ollamaInstalled = $true
    }
} catch {
    Write-Host "ℹ️  Ollama not found, will proceed with installation" -ForegroundColor Yellow
}

# Step 2: Download and Install Ollama if not present
if (-not $ollamaInstalled) {
    Write-Host "`n2. Downloading Ollama for Windows..." -ForegroundColor Cyan
    try {
        $installerPath = "$WorkingDirectory\OllamaSetup.exe"
        Write-Host "   Downloading to: $installerPath" -ForegroundColor Gray
        
        # Download with progress
        $webClient = New-Object System.Net.WebClient
        $webClient.DownloadFile("https://ollama.ai/download/windows", $installerPath)
        
        Write-Host "✅ Download completed" -ForegroundColor Green
        
        Write-Host "`n   Installing Ollama..." -ForegroundColor Cyan
        Write-Host "   ⚠️  Please follow the GUI installer prompts" -ForegroundColor Yellow
        
        # Start installer and wait for completion
        $process = Start-Process -FilePath $installerPath -Wait -PassThru
        
        if ($process.ExitCode -eq 0) {
            Write-Host "✅ Ollama installation completed" -ForegroundColor Green
            
            # Verify installation
            Start-Sleep -Seconds 3
            $version = & ollama --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ Installation verified: $version" -ForegroundColor Green
            } else {
                Write-Host "⚠️  Installation may need PATH refresh. Please restart PowerShell." -ForegroundColor Yellow
            }
        } else {
            Write-Host "❌ Installation failed with exit code: $($process.ExitCode)" -ForegroundColor Red
            exit 1
        }
        
    } catch {
        Write-Host "❌ Failed to download/install Ollama: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "2. ✅ Ollama installation check passed" -ForegroundColor Green
}

# Step 3: System Resource Analysis
Write-Host "`n3. Analyzing System Resources..." -ForegroundColor Cyan
$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
$cpu = (Get-CimInstance Win32_Processor).Name
$cores = (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors

Write-Host "   💻 CPU: $cpu" -ForegroundColor Gray
Write-Host "   🔢 Logical Cores: $cores" -ForegroundColor Gray
Write-Host "   🧠 Total RAM: $([math]::Round($ram, 1)) GB" -ForegroundColor Gray

if ($ram -lt 8) {
    Write-Host "   ⚠️  Less than 8GB RAM - will use lightweight configuration" -ForegroundColor Yellow
    $OptimizeForRAM = $true
} elseif ($ram -ge 16) {
    Write-Host "   ✅ Excellent RAM for optimal performance" -ForegroundColor Green
} else {
    Write-Host "   ✅ Adequate RAM for good performance" -ForegroundColor Green
}

# Step 4: Create optimized configuration
if ($OptimizeForRAM) {
    Write-Host "`n4. Creating Optimized Configuration..." -ForegroundColor Cyan
    
    try {
        $configPath = "$env:APPDATA\ollama"
        New-Item -ItemType Directory -Path $configPath -Force | Out-Null
        
        # Create optimized config based on system RAM
        $config = if ($ram -lt 8) {
            @{
                "num_ctx" = 1024
                "num_predict" = 256
                "num_thread" = [Math]::Max(2, $cores - 2)
                "num_gpu" = 0
                "low_vram" = $true
                "f16_kv" = $true
                "use_mlock" = $false
                "use_mmap" = $true
                "numa" = $false
            }
        } elseif ($ram -lt 16) {
            @{
                "num_ctx" = 2048
                "num_predict" = 512
                "num_thread" = [Math]::Max(2, $cores - 2)
                "num_gpu" = 0
                "low_vram" = $true
                "f16_kv" = $true
                "use_mlock" = $false
                "use_mmap" = $true
                "numa" = $false
            }
        } else {
            @{
                "num_ctx" = 4096
                "num_predict" = 1024
                "num_thread" = [Math]::Max(4, $cores - 2)
                "num_gpu" = 0
                "low_vram" = $false
                "f16_kv" = $true
                "use_mlock" = $true
                "use_mmap" = $true
                "numa" = $true
            }
        }
        
        $configFile = "$configPath\config.json"
        $config | ConvertTo-Json -Depth 3 | Out-File $configFile -Encoding UTF8
        
        Write-Host "   ✅ Configuration saved to: $configFile" -ForegroundColor Green
        Write-Host "   📝 Settings:" -ForegroundColor Gray
        Write-Host "      Context length: $($config.num_ctx)" -ForegroundColor Gray
        Write-Host "      Prediction tokens: $($config.num_predict)" -ForegroundColor Gray
        Write-Host "      CPU threads: $($config.num_thread)" -ForegroundColor Gray
        
    } catch {
        Write-Host "   ⚠️  Failed to create configuration: $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Host "4. ⏭️  Skipping configuration optimization" -ForegroundColor Gray
}

# Step 5: Download Models
if ($InstallModels) {
    Write-Host "`n5. Downloading Language Models..." -ForegroundColor Cyan
    
    # Start Ollama service temporarily for model download
    Write-Host "   Starting Ollama service for model download..." -ForegroundColor Gray
    $ollamaProcess = Start-Process -FilePath "ollama" -ArgumentList "serve" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 5  # Wait for service to start
    
    try {
        # Test if service is running
        $response = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -Method Get -TimeoutSec 5
        Write-Host "   ✅ Ollama service started successfully" -ForegroundColor Green
        
        # Download Llama 3.2 3B
        Write-Host "`n   📥 Downloading Llama 3.2 3B model (~2GB)..." -ForegroundColor Yellow
        Write-Host "   ⏳ This may take several minutes depending on your internet connection" -ForegroundColor Gray
        
        $pullProcess = Start-Process -FilePath "ollama" -ArgumentList "pull", "llama3.2:3b" -Wait -PassThru -NoNewWindow
        if ($pullProcess.ExitCode -eq 0) {
            Write-Host "   ✅ Llama 3.2 3B downloaded successfully" -ForegroundColor Green
        } else {
            Write-Host "   ❌ Failed to download Llama 3.2 3B" -ForegroundColor Red
        }
        
        # Download Phi-3 Mini
        Write-Host "`n   📥 Downloading Phi-3 Mini model (~2GB)..." -ForegroundColor Yellow
        $pullProcess2 = Start-Process -FilePath "ollama" -ArgumentList "pull", "phi3:mini" -Wait -PassThru -NoNewWindow
        if ($pullProcess2.ExitCode -eq 0) {
            Write-Host "   ✅ Phi-3 Mini downloaded successfully" -ForegroundColor Green
        } else {
            Write-Host "   ⚠️  Failed to download Phi-3 Mini (optional)" -ForegroundColor Yellow
        }
        
        # List installed models
        Write-Host "`n   📋 Installed models:" -ForegroundColor Cyan
        & ollama list
        
    } catch {
        Write-Host "   ❌ Failed to start Ollama service: $($_.Exception.Message)" -ForegroundColor Red
    } finally {
        # Stop the temporary service
        if ($ollamaProcess -and !$ollamaProcess.HasExited) {
            Write-Host "   Stopping temporary Ollama service..." -ForegroundColor Gray
            Stop-Process -Id $ollamaProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Host "5. ⏭️  Skipping model installation (use -InstallModels to download)" -ForegroundColor Gray
}

# Step 6: Create Windows Service with NSSM
if ($CreateService) {
    Write-Host "`n6. Setting up Windows Service with NSSM..." -ForegroundColor Cyan
    
    # Download NSSM if not present
    $nssmPath = "C:\Tools\nssm-2.24\win64\nssm.exe"
    if (!(Test-Path $nssmPath)) {
        Write-Host "   📥 Downloading NSSM..." -ForegroundColor Yellow
        try {
            $nssmZip = "$WorkingDirectory\nssm.zip"
            Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $nssmZip
            Expand-Archive -Path $nssmZip -DestinationPath "C:\Tools" -Force
            Write-Host "   ✅ NSSM downloaded and extracted" -ForegroundColor Green
        } catch {
            Write-Host "   ❌ Failed to download NSSM: $($_.Exception.Message)" -ForegroundColor Red
            return
        }
    }
    
    try {
        # Find Ollama executable
        $ollamaPath = (Get-Command ollama -ErrorAction Stop).Source
        Write-Host "   📍 Ollama executable: $ollamaPath" -ForegroundColor Gray
        
        # Remove existing service if present
        $existingService = Get-Service $ServiceName -ErrorAction SilentlyContinue
        if ($existingService) {
            Write-Host "   🔄 Removing existing service..." -ForegroundColor Yellow
            & $nssmPath remove $ServiceName confirm
            Start-Sleep -Seconds 2
        }
        
        # Install service
        Write-Host "   🔧 Installing Ollama as Windows service..." -ForegroundColor Yellow
        & $nssmPath install $ServiceName $ollamaPath "serve"
        
        # Configure service
        & $nssmPath set $ServiceName DisplayName "Ollama Local LLM Service"
        & $nssmPath set $ServiceName Description "Local Large Language Model API Server for MIDAS RAG System"
        & $nssmPath set $ServiceName Start SERVICE_AUTO_START
        & $nssmPath set $ServiceName AppRestartDelay 5000
        
        # Set environment variables
        & $nssmPath set $ServiceName AppEnvironmentExtra "OLLAMA_HOST=0.0.0.0:11434`nOLLAMA_MODELS=$env:USERPROFILE\.ollama\models"
        
        # Configure logging
        & $nssmPath set $ServiceName AppStdout "$WorkingDirectory\logs\ollama-stdout.log"
        & $nssmPath set $ServiceName AppStderr "$WorkingDirectory\logs\ollama-stderr.log"
        & $nssmPath set $ServiceName AppStdoutCreationDisposition 4
        & $nssmPath set $ServiceName AppStderrCreationDisposition 4
        
        # Set working directory
        & $nssmPath set $ServiceName AppDirectory $WorkingDirectory
        
        Write-Host "   ✅ Service configured successfully" -ForegroundColor Green
        
        # Start the service
        Write-Host "   🚀 Starting Ollama service..." -ForegroundColor Yellow
        Start-Service $ServiceName -ErrorAction Stop
        
        # Verify service is running
        Start-Sleep -Seconds 5
        $service = Get-Service $ServiceName
        if ($service.Status -eq "Running") {
            Write-Host "   ✅ Ollama service started successfully" -ForegroundColor Green
            
            # Test API connectivity
            try {
                Start-Sleep -Seconds 3
                $apiResponse = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -Method Get -TimeoutSec 10
                Write-Host "   ✅ API accessible - Version: $($apiResponse.version)" -ForegroundColor Green
            } catch {
                Write-Host "   ⚠️  Service started but API not yet accessible (may need more time)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "   ❌ Failed to start service. Status: $($service.Status)" -ForegroundColor Red
        }
        
    } catch {
        Write-Host "   ❌ Failed to create service: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "6. ⏭️  Skipping service creation (use -CreateService to install)" -ForegroundColor Gray
}

# Step 7: Create startup verification script
Write-Host "`n7. Creating Verification Script..." -ForegroundColor Cyan
$verifyScript = @"
# Quick Ollama verification
Write-Host "Checking Ollama service..." -ForegroundColor Cyan
try {
    `$response = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -Method Get -TimeoutSec 5
    Write-Host "✅ Ollama API accessible - Version: `$(`$response.version)" -ForegroundColor Green
    
    `$models = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get
    Write-Host "📦 Available models: `$(`$models.models.Count)" -ForegroundColor Green
    `$models.models | ForEach-Object { Write-Host "   - `$(`$_.name)" -ForegroundColor Gray }
} catch {
    Write-Host "❌ Ollama not accessible: `$(`$_.Exception.Message)" -ForegroundColor Red
    Write-Host "💡 Try: ollama serve" -ForegroundColor Yellow
}
"@

$verifyScriptPath = "$WorkingDirectory\Verify-Ollama.ps1"
$verifyScript | Out-File $verifyScriptPath -Encoding UTF8
Write-Host "   ✅ Verification script created: $verifyScriptPath" -ForegroundColor Green

# Final Summary
Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host "📁 Working Directory: $WorkingDirectory" -ForegroundColor White
Write-Host "📄 Log Directory: $WorkingDirectory\logs" -ForegroundColor White

if ($CreateService) {
    Write-Host "🔧 Service Management Commands:" -ForegroundColor Cyan
    Write-Host "   Start:   Start-Service $ServiceName" -ForegroundColor Gray
    Write-Host "   Stop:    Stop-Service $ServiceName" -ForegroundColor Gray
    Write-Host "   Status:  Get-Service $ServiceName" -ForegroundColor Gray
    Write-Host "   Logs:    Get-Content '$WorkingDirectory\logs\ollama-stdout.log' -Tail 20" -ForegroundColor Gray
}

Write-Host "🔗 API Endpoint: http://localhost:11434" -ForegroundColor Cyan
Write-Host "📋 Test Scripts:" -ForegroundColor Cyan
Write-Host "   Verify:  .$verifyScriptPath" -ForegroundColor Gray
Write-Host "   Test:    .\Test-Ollama.ps1" -ForegroundColor Gray

if ($InstallModels) {
    Write-Host "🤖 Test your installation:" -ForegroundColor Yellow
    Write-Host '   ollama run llama3.2:3b "Hello, how are you?"' -ForegroundColor Gray
} else {
    Write-Host "📦 Next steps:" -ForegroundColor Yellow
    Write-Host "   1. Download models: ollama pull llama3.2:3b" -ForegroundColor Gray
    Write-Host "   2. Test: ollama run llama3.2:3b 'Hello!'" -ForegroundColor Gray
}

Write-Host "`n🎉 Ollama setup completed successfully!" -ForegroundColor Green