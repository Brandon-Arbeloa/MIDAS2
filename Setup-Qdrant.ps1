# Setup-Qdrant.ps1
# Qdrant vector database setup for Windows 11 with persistent storage
# Usage: .\Setup-Qdrant.ps1 -Method Docker -DataPath "C:\QdrantData"

param(
    [ValidateSet("Docker", "Binary", "Both")]
    [string]$Method = "Docker",
    [string]$DataPath = "C:\QdrantData",
    [string]$Port = "6333",
    [switch]$CreateService = $false
)

Write-Host "=== Qdrant Vector Database Setup for Windows 11 ===" -ForegroundColor Green
Write-Host "Method: $Method" -ForegroundColor Yellow
Write-Host "Data Path: $DataPath" -ForegroundColor Yellow
Write-Host "Port: $Port" -ForegroundColor Yellow
Write-Host ""

# Create data directory with proper permissions
Write-Host "📁 Setting up data directory..." -ForegroundColor Cyan
try {
    New-Item -ItemType Directory -Path $DataPath -Force | Out-Null
    New-Item -ItemType Directory -Path "$DataPath\storage" -Force | Out-Null
    New-Item -ItemType Directory -Path "$DataPath\snapshots" -Force | Out-Null
    New-Item -ItemType Directory -Path "$DataPath\logs" -Force | Out-Null
    
    # Set directory permissions for current user
    $acl = Get-Acl $DataPath
    $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
    $acl.SetAccessRule($accessRule)
    Set-Acl $DataPath $acl
    
    Write-Host "✅ Data directory created: $DataPath" -ForegroundColor Green
} catch {
    Write-Host "❌ Failed to create data directory: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Docker Installation Method
if ($Method -eq "Docker" -or $Method -eq "Both") {
    Write-Host "`n1. Setting up Qdrant with Docker..." -ForegroundColor Cyan
    
    # Check if Docker is available
    try {
        $dockerVersion = docker --version 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker not found"
        }
        Write-Host "   ✅ Docker available: $dockerVersion" -ForegroundColor Green
    } catch {
        Write-Host "   ❌ Docker not found. Please install Docker Desktop for Windows first." -ForegroundColor Red
        Write-Host "   💡 Download from: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
        if ($Method -eq "Docker") { exit 1 }
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   📥 Pulling Qdrant Docker image..." -ForegroundColor Yellow
        docker pull qdrant/qdrant:latest
        
        # Stop existing container if running
        $existingContainer = docker ps -a --format "{{.Names}}" | Select-String "qdrant-midas"
        if ($existingContainer) {
            Write-Host "   🔄 Stopping existing Qdrant container..." -ForegroundColor Yellow
            docker stop qdrant-midas | Out-Null
            docker rm qdrant-midas | Out-Null
        }
        
        # Create Qdrant configuration file
        $configContent = @"
storage:
  storage_path: /qdrant/storage
  snapshots_path: /qdrant/snapshots
  
service:
  http_port: 6333
  grpc_port: 6334
  
cluster:
  enabled: false

telemetry_disabled: true

log_level: INFO
"@
        
        $configPath = "$DataPath\config.yaml"
        $configContent | Out-File $configPath -Encoding UTF8
        Write-Host "   ✅ Configuration created: $configPath" -ForegroundColor Green
        
        # Start Qdrant container with Windows path mapping
        $windowsDataPath = $DataPath.Replace('\', '/')
        Write-Host "   🚀 Starting Qdrant container..." -ForegroundColor Yellow
        
        $dockerCommand = @(
            "run", "-d"
            "--name", "qdrant-midas"
            "--restart", "unless-stopped"
            "-p", "${Port}:6333"
            "-p", "6334:6334"
            "-v", "${DataPath}:/qdrant/storage"
            "-v", "${configPath}:/qdrant/config/production.yaml"
            "qdrant/qdrant:latest"
        )
        
        $containerId = & docker @dockerCommand
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Qdrant container started: $($containerId.Substring(0,12))" -ForegroundColor Green
            
            # Wait for service to start
            Write-Host "   ⏳ Waiting for Qdrant to initialize..." -ForegroundColor Yellow
            $attempts = 0
            do {
                Start-Sleep -Seconds 2
                $attempts++
                try {
                    $response = Invoke-RestMethod -Uri "http://localhost:${Port}/collections" -Method Get -TimeoutSec 5
                    $serviceReady = $true
                    break
                } catch {
                    $serviceReady = $false
                }
            } while ($attempts -lt 15)
            
            if ($serviceReady) {
                Write-Host "   ✅ Qdrant API accessible on http://localhost:${Port}" -ForegroundColor Green
            } else {
                Write-Host "   ⚠️  Qdrant started but API not yet accessible" -ForegroundColor Yellow
            }
        } else {
            Write-Host "   ❌ Failed to start Qdrant container" -ForegroundColor Red
        }
    }
}

# Binary Installation Method
if ($Method -eq "Binary" -or $Method -eq "Both") {
    Write-Host "`n2. Setting up Qdrant Windows Binary..." -ForegroundColor Cyan
    
    $binaryPath = "$DataPath\qdrant.exe"
    
    if (!(Test-Path $binaryPath)) {
        Write-Host "   📥 Downloading Qdrant Windows binary..." -ForegroundColor Yellow
        try {
            # Get latest release info
            $releaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/qdrant/qdrant/releases/latest"
            $windowsAsset = $releaseInfo.assets | Where-Object { $_.name -like "*windows*" -and $_.name -like "*.zip" }
            
            if ($windowsAsset) {
                $downloadUrl = $windowsAsset.browser_download_url
                $zipPath = "$DataPath\qdrant-windows.zip"
                
                Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath
                Write-Host "   ✅ Downloaded: $($windowsAsset.name)" -ForegroundColor Green
                
                # Extract binary
                Expand-Archive -Path $zipPath -DestinationPath $DataPath -Force
                
                # Find the executable
                $extractedExe = Get-ChildItem -Path $DataPath -Name "*.exe" -Recurse | Select-Object -First 1
                if ($extractedExe) {
                    Move-Item "$DataPath\$extractedExe" $binaryPath -Force
                    Write-Host "   ✅ Binary extracted to: $binaryPath" -ForegroundColor Green
                }
                
                Remove-Item $zipPath -Force
            } else {
                Write-Host "   ❌ Windows binary not found in latest release" -ForegroundColor Red
            }
        } catch {
            Write-Host "   ❌ Failed to download Qdrant binary: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "   ✅ Qdrant binary already exists: $binaryPath" -ForegroundColor Green
    }
    
    # Create configuration for binary
    if (Test-Path $binaryPath) {
        $binaryConfigPath = "$DataPath\config-binary.yaml"
        $binaryConfig = @"
storage:
  storage_path: $($DataPath.Replace('\', '\\'))\\storage
  snapshots_path: $($DataPath.Replace('\', '\\'))\\snapshots
  
service:
  http_port: 6334
  grpc_port: 6335
  
cluster:
  enabled: false

telemetry_disabled: true

log_level: INFO
"@
        $binaryConfig | Out-File $binaryConfigPath -Encoding UTF8
        Write-Host "   ✅ Binary configuration created: $binaryConfigPath" -ForegroundColor Green
        
        Write-Host "   💡 To start binary version manually:" -ForegroundColor Yellow
        Write-Host "      cd `"$DataPath`"" -ForegroundColor Gray
        Write-Host "      .\qdrant.exe --config-path config-binary.yaml" -ForegroundColor Gray
    }
}

# Test connectivity and create initial collection
Write-Host "`n3. Testing Qdrant Connection..." -ForegroundColor Cyan
$testPorts = @($Port)
if ($Method -eq "Both") { $testPorts += @("6334") }

foreach ($testPort in $testPorts) {
    try {
        Start-Sleep -Seconds 2
        $response = Invoke-RestMethod -Uri "http://localhost:${testPort}/collections" -Method Get -TimeoutSec 10
        Write-Host "   ✅ Qdrant accessible on port $testPort" -ForegroundColor Green
        
        # Create initial collection for documents
        $collectionConfig = @{
            vectors = @{
                size = 384
                distance = "Cosine"
            }
            optimizers_config = @{
                default_segment_number = 2
            }
            replication_factor = 1
        } | ConvertTo-Json -Depth 3
        
        try {
            $createResponse = Invoke-RestMethod -Uri "http://localhost:${testPort}/collections/documents" -Method PUT -Body $collectionConfig -ContentType "application/json"
            Write-Host "   ✅ Created 'documents' collection" -ForegroundColor Green
        } catch {
            if ($_.Exception.Message -like "*already exists*") {
                Write-Host "   ℹ️  'documents' collection already exists" -ForegroundColor Yellow
            } else {
                Write-Host "   ⚠️  Failed to create collection: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
        
        # Test collection info
        try {
            $collectionInfo = Invoke-RestMethod -Uri "http://localhost:${testPort}/collections/documents" -Method Get
            Write-Host "   📊 Collection info:" -ForegroundColor Cyan
            Write-Host "      Vectors: $($collectionInfo.result.vectors_count)" -ForegroundColor Gray
            Write-Host "      Points: $($collectionInfo.result.points_count)" -ForegroundColor Gray
            Write-Host "      Status: $($collectionInfo.result.status)" -ForegroundColor Gray
        } catch {
            Write-Host "   ⚠️  Could not retrieve collection info" -ForegroundColor Yellow
        }
        
    } catch {
        Write-Host "   ❌ Qdrant not accessible on port $testPort" -ForegroundColor Red
        Write-Host "      Error: $($_.Exception.Message)" -ForegroundColor Gray
    }
}

# Create management scripts
Write-Host "`n4. Creating Management Scripts..." -ForegroundColor Cyan

# Docker management script
if ($Method -eq "Docker" -or $Method -eq "Both") {
    $dockerManageScript = @"
# Qdrant Docker Management Script
param([string]`$Action = "status")

switch (`$Action.ToLower()) {
    "start" {
        Write-Host "Starting Qdrant container..." -ForegroundColor Green
        docker start qdrant-midas
    }
    "stop" {
        Write-Host "Stopping Qdrant container..." -ForegroundColor Yellow
        docker stop qdrant-midas
    }
    "restart" {
        Write-Host "Restarting Qdrant container..." -ForegroundColor Yellow
        docker restart qdrant-midas
    }
    "status" {
        Write-Host "Qdrant Container Status:" -ForegroundColor Cyan
        docker ps -a --filter name=qdrant-midas --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        
        Write-Host "`nAPI Status:" -ForegroundColor Cyan
        try {
            `$response = Invoke-RestMethod -Uri "http://localhost:${Port}/collections" -Method Get -TimeoutSec 5
            Write-Host "✅ API accessible" -ForegroundColor Green
        } catch {
            Write-Host "❌ API not accessible" -ForegroundColor Red
        }
    }
    "logs" {
        docker logs qdrant-midas --tail 50 -f
    }
    default {
        Write-Host "Usage: .\Manage-Qdrant.ps1 -Action [start|stop|restart|status|logs]" -ForegroundColor Yellow
    }
}
"@
    $dockerManageScript | Out-File "$DataPath\Manage-Qdrant.ps1" -Encoding UTF8
    Write-Host "   ✅ Docker management script: $DataPath\Manage-Qdrant.ps1" -ForegroundColor Green
}

# Create test script
$testScript = @"
# Test Qdrant connectivity and performance
Write-Host "=== Qdrant Connection Test ===" -ForegroundColor Green

`$ports = @($Port)
foreach (`$port in `$ports) {
    Write-Host "`nTesting port `$port..." -ForegroundColor Cyan
    try {
        `$response = Invoke-RestMethod -Uri "http://localhost:`$port/collections" -Method Get -TimeoutSec 5
        Write-Host "✅ Connected to Qdrant on port `$port" -ForegroundColor Green
        
        # Test collection
        try {
            `$collections = `$response.result.collections
            Write-Host "📦 Collections: `$(`$collections.Count)" -ForegroundColor Gray
            `$collections | ForEach-Object { Write-Host "   - `$(`$_.name)" -ForegroundColor Gray }
            
            if (`$collections | Where-Object { `$_.name -eq "documents" }) {
                `$docCollection = Invoke-RestMethod -Uri "http://localhost:`$port/collections/documents" -Method Get
                Write-Host "📊 Documents collection:" -ForegroundColor Cyan
                Write-Host "   Points: `$(`$docCollection.result.points_count)" -ForegroundColor Gray
                Write-Host "   Vectors: `$(`$docCollection.result.vectors_count)" -ForegroundColor Gray
                Write-Host "   Status: `$(`$docCollection.result.status)" -ForegroundColor Gray
            }
        } catch {
            Write-Host "⚠️  Collection test failed: `$(`$_.Exception.Message)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "❌ Cannot connect to port `$port" -ForegroundColor Red
        Write-Host "   Error: `$(`$_.Exception.Message)" -ForegroundColor Gray
    }
}
"@

$testScript | Out-File "$DataPath\Test-Qdrant.ps1" -Encoding UTF8
Write-Host "   ✅ Test script: $DataPath\Test-Qdrant.ps1" -ForegroundColor Green

# Final summary
Write-Host "`n=== Qdrant Setup Complete ===" -ForegroundColor Green
Write-Host "📁 Data Directory: $DataPath" -ForegroundColor White
Write-Host "🔗 API Endpoint: http://localhost:$Port" -ForegroundColor White
Write-Host "📊 Web UI: http://localhost:$Port/dashboard" -ForegroundColor White

Write-Host "`n🔧 Management Commands:" -ForegroundColor Cyan
if ($Method -eq "Docker" -or $Method -eq "Both") {
    Write-Host "   Docker: .\Manage-Qdrant.ps1 -Action [start|stop|status|logs]" -ForegroundColor Gray
}
Write-Host "   Test:   .\Test-Qdrant.ps1" -ForegroundColor Gray

Write-Host "`n📦 Collections:" -ForegroundColor Cyan
Write-Host "   documents: 384-dimensional vectors with Cosine distance" -ForegroundColor Gray

Write-Host "`n🗂️  Storage Paths:" -ForegroundColor Cyan
Write-Host "   Data: $DataPath\storage" -ForegroundColor Gray
Write-Host "   Snapshots: $DataPath\snapshots" -ForegroundColor Gray
Write-Host "   Logs: $DataPath\logs" -ForegroundColor Gray

Write-Host "`n🎉 Qdrant vector database is ready for document indexing!" -ForegroundColor Green
"