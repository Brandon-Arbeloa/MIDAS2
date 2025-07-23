# EXTERNAL SERVICES REQUIREMENTS
## For Windows 11 On-Premises RAG System - Updated 2025-07-22

This document outlines all external services, network access requirements, and dependencies needed for deploying the MIDAS RAG System in a closed/restricted Windows environment.

## 1. Required External Services

### 1.1 Ollama (Local LLM Service) ⚠️ **PENDING INSTALLATION**
- **Purpose**: Provides local Large Language Model capabilities
- **Current Status**: Client library installed (ollama==0.5.1), server not installed
- **Default Port**: 11434
- **Windows Installation**:
  ```powershell
  # Download Ollama for Windows
  Invoke-WebRequest -Uri "https://ollama.ai/download/windows" -OutFile "ollama-windows.exe"
  .\ollama-windows.exe
  
  # Verify installation
  ollama --version
  
  # Pull required models
  ollama pull llama3.2:3b
  ollama pull phi3:mini
  
  # Test API server
  curl http://localhost:11434/api/version
  ```
- **Models Required**:
  - llama3.2:3b (primary, ~2GB download)
  - phi3:mini (alternative, ~2GB download)
- **Network Requirements**: 
  - Initial internet access for download only
  - Runs completely offline after installation
- **Hardware Requirements**:
  - Minimum 8GB RAM (16GB recommended)
  - 10GB free disk space for models

### 1.2 Qdrant (Vector Database) ⚠️ **PENDING INSTALLATION**
- **Purpose**: Stores and searches document embeddings for similarity search
- **Current Status**: Client library installed (qdrant-client==1.15.0), server not installed
- **Default Port**: 6333
- **Windows Installation Options**:
  
  **Option A: Docker (Recommended)**
  ```powershell
  # Install Docker Desktop first, then:
  docker pull qdrant/qdrant
  docker run -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
  ```
  
  **Option B: Windows Binary**
  ```powershell
  # Download latest Windows executable
  Invoke-WebRequest -Uri "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-pc-windows-msvc.zip" -OutFile "qdrant.zip"
  Expand-Archive -Path "qdrant.zip" -DestinationPath "qdrant"
  cd qdrant
  .\qdrant.exe
  ```
  
  **Verification**:
  ```powershell
  # Test API endpoint
  curl http://localhost:6333/collections
  ```
- **Configuration Required**:
  - Collection name: "documents"
  - Vector dimension: 384 (matches all-MiniLM-L6-v2 model)
  - Distance metric: Cosine similarity
- **Storage Requirements**:
  - Persistent volume for vector storage
  - 10-50GB depending on document volume

### 1.3 PostgreSQL (Relational Database) ⚠️ **PENDING INSTALLATION**
- **Purpose**: Stores document metadata, user data, and application state
- **Current Status**: Client library installed (psycopg2-binary==2.9.10), server not installed
- **Default Port**: 5432
- **Windows Installation**:
  ```powershell
  # Download PostgreSQL 15+ for Windows from official site
  # https://www.postgresql.org/download/windows/
  # Run the installer with these settings:
  # - Port: 5432 (default)
  # - Set postgres user password (remember this!)
  # - Install pgAdmin (recommended for management)
  ```
  
  **Database Setup**:
  ```sql
  -- Connect as postgres user
  psql -U postgres
  
  -- Create database and user
  CREATE DATABASE rag_system;
  CREATE USER rag_user WITH PASSWORD 'your_secure_password';
  GRANT ALL PRIVILEGES ON DATABASE rag_system TO rag_user;
  
  -- Connect to new database
  \c rag_system
  
  -- Verify connection
  SELECT version();
  ```
- **Configuration Required**:
  - Database name: rag_system
  - User: rag_user (with full database privileges)
  - Connection string: postgresql://rag_user:password@localhost:5432/rag_system
- **Storage Requirements**:
  - 5-20GB for metadata and user data

### 1.4 Redis (Cache Service) ⚠️ **PENDING INSTALLATION**
- **Purpose**: Caching, session management, and task queuing
- **Current Status**: Client library installed (redis==6.2.0), server not installed
- **Default Port**: 6379
- **Windows Installation Options**:
  
  **Option A: Docker (Recommended)**
  ```powershell
  # Run Redis in Docker
  docker run -d -p 6379:6379 --name redis redis:latest redis-server --appendonly yes
  ```
  
  **Option B: WSL2 with Ubuntu**
  ```powershell
  # Install WSL2 first, then in Ubuntu:
  sudo apt update
  sudo apt install redis-server
  sudo service redis-server start
  
  # Test Redis
  redis-cli ping
  # Should return "PONG"
  ```
  
  **Option C: Windows Port (Unofficial)**
  ```powershell
  # Download from Microsoft Archive (Redis 3.x)
  # Visit: https://github.com/microsoftarchive/redis/releases
  # Extract and run redis-server.exe
  ```
- **Configuration Required**:
  - Memory limit: 1GB recommended
  - Persistence: Optional (cache can be volatile)
  - Password: Recommended for security
- **Testing Connection**:
  ```powershell
  # Test with Python
  python -c "import redis; r = redis.Redis(); print(r.ping())"
  ```

## 2. Ollama Windows Service Configuration

### 2.1 Ollama Installation and Model Setup ⚙️ **DETAILED SETUP**

**Step 1: Download and Install Ollama**
```powershell
# Create working directory
New-Item -ItemType Directory -Path "C:\Ollama" -Force
cd C:\Ollama

# Download Ollama for Windows
Invoke-WebRequest -Uri "https://ollama.ai/download/windows" -OutFile "OllamaSetup.exe"

# Install Ollama (follow GUI installer)
.\OllamaSetup.exe

# Verify installation
ollama --version
```

**Step 2: Download Required Models**
```powershell
# Pull Llama 3.2 3B model (primary model, ~2GB)
ollama pull llama3.2:3b

# Pull Phi-3 Mini model (alternative model, ~2GB)  
ollama pull phi3:mini

# Verify models are installed
ollama list
```

**Step 3: CPU Optimization Configuration**
```powershell
# Create Ollama configuration file
$configPath = "$env:APPDATA\ollama\config.json"
New-Item -ItemType Directory -Path (Split-Path $configPath) -Force

# Create optimized config for 8-16GB RAM systems
@{
    "num_ctx" = 2048
    "num_predict" = 512
    "num_thread" = [Math]::Max(1, [Environment]::ProcessorCount - 2)
    "num_gpu" = 0
    "main_gpu" = 0
    "low_vram" = $true
    "f16_kv" = $true
    "use_mlock" = $false
    "use_mmap" = $true
} | ConvertTo-Json | Out-File $configPath -Encoding UTF8

Write-Host "Ollama configured for CPU-only inference with memory optimization"
```

### 2.2 Windows Service Configuration with NSSM

**Step 1: Download and Install NSSM**
```powershell
# Download NSSM (Non-Sucking Service Manager)
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "nssm.zip"
Expand-Archive -Path "nssm.zip" -DestinationPath "C:\Tools"

# Add to PATH or use full path
$nssmPath = "C:\Tools\nssm-2.24\win64\nssm.exe"
```

**Step 2: Create Ollama Windows Service**
```powershell
# Find Ollama executable path
$ollamaPath = (Get-Command ollama).Source

# Create the service
& $nssmPath install "OllamaService" $ollamaPath "serve"

# Configure service parameters
& $nssmPath set "OllamaService" DisplayName "Ollama Local LLM Service"
& $nssmPath set "OllamaService" Description "Local Large Language Model API Server"
& $nssmPath set "OllamaService" Start SERVICE_AUTO_START

# Set environment variables for the service
& $nssmPath set "OllamaService" AppEnvironmentExtra "OLLAMA_HOST=0.0.0.0:11434"
& $nssmPath set "OllamaService" AppEnvironmentExtra "OLLAMA_MODELS=C:\Users\$env:USERNAME\.ollama\models"

# Configure logging
& $nssmPath set "OllamaService" AppStdout "C:\Ollama\logs\ollama-stdout.log"
& $nssmPath set "OllamaService" AppStderr "C:\Ollama\logs\ollama-stderr.log"

# Create log directory
New-Item -ItemType Directory -Path "C:\Ollama\logs" -Force

# Start the service
Start-Service "OllamaService"
Set-Service "OllamaService" -StartupType Automatic

Write-Host "Ollama service installed and started successfully"
```

### 2.3 API Testing and Performance Script

**Create PowerShell Test Script: `Test-Ollama.ps1`**
```powershell
# Test-Ollama.ps1
# Comprehensive Ollama API testing and performance measurement

param(
    [string]$OllamaUrl = "http://localhost:11434",
    [string]$Model = "llama3.2:3b",
    [int]$TestIterations = 3
)

Write-Host "=== Ollama API Test Suite ===" -ForegroundColor Green
Write-Host "URL: $OllamaUrl" -ForegroundColor Yellow
Write-Host "Model: $Model" -ForegroundColor Yellow
Write-Host ""

# Test 1: Service Connectivity
Write-Host "1. Testing API Connectivity..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "$OllamaUrl/api/version" -Method Get -TimeoutSec 10
    Write-Host "✅ API accessible - Version: $($response.version)" -ForegroundColor Green
} catch {
    Write-Host "❌ API not accessible: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Test 2: Model Availability
Write-Host "`n2. Checking Model Availability..." -ForegroundColor Cyan
try {
    $models = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -Method Get
    $availableModel = $models.models | Where-Object { $_.name -eq $Model }
    if ($availableModel) {
        Write-Host "✅ Model '$Model' is available" -ForegroundColor Green
        Write-Host "   Size: $([math]::Round($availableModel.size / 1GB, 2)) GB" -ForegroundColor Gray
    } else {
        Write-Host "❌ Model '$Model' not found" -ForegroundColor Red
        Write-Host "Available models:" -ForegroundColor Yellow
        $models.models | ForEach-Object { Write-Host "  - $($_.name)" -ForegroundColor Gray }
        exit 1
    }
} catch {
    Write-Host "❌ Failed to check models: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Test 3: Performance Benchmarks
Write-Host "`n3. Running Performance Tests ($TestIterations iterations)..." -ForegroundColor Cyan

$testPrompts = @(
    "Hello, how are you?",
    "Explain quantum computing in simple terms.",
    "Write a Python function to calculate fibonacci numbers."
)

$results = @()

foreach ($prompt in $testPrompts) {
    Write-Host "`nTesting prompt: '$prompt'" -ForegroundColor Yellow
    
    for ($i = 1; $i -le $TestIterations; $i++) {
        Write-Host "  Iteration $i..." -NoNewline
        
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        try {
            $body = @{
                model = $Model
                prompt = $prompt
                stream = $false
                options = @{
                    num_predict = 100
                    temperature = 0.7
                }
            } | ConvertTo-Json
            
            $response = Invoke-RestMethod -Uri "$OllamaUrl/api/generate" -Method Post -Body $body -ContentType "application/json"
            
            $stopwatch.Stop()
            $responseTime = $stopwatch.ElapsedMilliseconds
            
            # Calculate tokens per second (approximate)
            $tokenCount = ($response.response -split '\s+').Count
            $tokensPerSecond = [math]::Round($tokenCount / ($responseTime / 1000), 2)
            
            $results += [PSCustomObject]@{
                Prompt = $prompt.Substring(0, [Math]::Min(30, $prompt.Length)) + "..."
                Iteration = $i
                ResponseTime = $responseTime
                TokenCount = $tokenCount
                TokensPerSecond = $tokensPerSecond
                Success = $true
            }
            
            Write-Host " ✅ ${responseTime}ms (${tokensPerSecond} tok/s)" -ForegroundColor Green
            
        } catch {
            $stopwatch.Stop()
            Write-Host " ❌ Error: $($_.Exception.Message)" -ForegroundColor Red
            
            $results += [PSCustomObject]@{
                Prompt = $prompt.Substring(0, [Math]::Min(30, $prompt.Length)) + "..."
                Iteration = $i
                ResponseTime = $null
                TokenCount = $null
                TokensPerSecond = $null
                Success = $false
                Error = $_.Exception.Message
            }
        }
    }
}

# Test Results Summary
Write-Host "`n=== Performance Summary ===" -ForegroundColor Green

$successfulTests = $results | Where-Object { $_.Success -eq $true }
if ($successfulTests.Count -gt 0) {
    $avgResponseTime = ($successfulTests | Measure-Object ResponseTime -Average).Average
    $avgTokensPerSecond = ($successfulTests | Measure-Object TokensPerSecond -Average).Average
    $maxTokensPerSecond = ($successfulTests | Measure-Object TokensPerSecond -Maximum).Maximum
    $minTokensPerSecond = ($successfulTests | Measure-Object TokensPerSecond -Minimum).Minimum
    
    Write-Host "✅ Successful tests: $($successfulTests.Count)/$($results.Count)" -ForegroundColor Green
    Write-Host "📊 Average response time: $([math]::Round($avgResponseTime, 2))ms" -ForegroundColor Cyan
    Write-Host "🚀 Average tokens/second: $([math]::Round($avgTokensPerSecond, 2))" -ForegroundColor Cyan
    Write-Host "📈 Max tokens/second: $([math]::Round($maxTokensPerSecond, 2))" -ForegroundColor Cyan
    Write-Host "📉 Min tokens/second: $([math]::Round($minTokensPerSecond, 2))" -ForegroundColor Cyan
} else {
    Write-Host "❌ No successful tests completed" -ForegroundColor Red
}

# System Performance Recommendations
Write-Host "`n=== System Recommendations ===" -ForegroundColor Green

$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
$cpu = (Get-CimInstance Win32_Processor).Name

Write-Host "💻 System: $cpu" -ForegroundColor Gray
Write-Host "🧠 RAM: $([math]::Round($ram, 1)) GB" -ForegroundColor Gray

if ($ram -lt 8) {
    Write-Host "⚠️  Warning: Less than 8GB RAM detected. Consider model optimization." -ForegroundColor Yellow
} elseif ($ram -ge 16) {
    Write-Host "✅ Sufficient RAM for optimal performance" -ForegroundColor Green
} else {
    Write-Host "✅ Adequate RAM, performance should be good" -ForegroundColor Green
}

# Save results to JSON for analysis
$results | ConvertTo-Json -Depth 3 | Out-File "C:\Ollama\logs\performance-test-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"

Write-Host "`n📝 Detailed results saved to: C:\Ollama\logs\performance-test-*.json" -ForegroundColor Gray
Write-Host "`n=== Test Complete ===" -ForegroundColor Green
```

### 2.4 Service Management Commands
```powershell
# Start Ollama service
Start-Service "OllamaService"

# Stop Ollama service  
Stop-Service "OllamaService"

# Check service status
Get-Service "OllamaService"

# View service logs
Get-Content "C:\Ollama\logs\ollama-stdout.log" -Tail 50

# Remove service (if needed)
& $nssmPath remove "OllamaService" confirm
```

## 3. Python Package Dependencies - Current Environment

### 3.1 Verified Installed Packages ✅ **CURRENT VERSIONS**
These packages are already installed and verified in the virtual environment:

```
# Core Framework
streamlit==1.47.0
pyyaml==6.0.2

# LLM and Embeddings
ollama==0.5.1
sentence-transformers==5.0.0
transformers==4.53.3
torch==2.7.1
huggingface-hub==0.33.4

# Vector Database
qdrant-client==1.15.0

# Document Processing
pandas==2.3.1
# PyPDF2 - Not currently installed
# python-docx - Not currently installed

# Database
psycopg2-binary==2.9.10

# Caching
redis==6.2.0

# Scientific Computing
numpy==2.3.1
scipy==1.16.0
scikit-learn==1.7.1

# HTTP and Utilities
requests==2.32.4
httpx==0.28.1
httpcore==1.0.9

# Windows Specific
pywin32==311
colorama==0.4.6
```

### 2.2 Offline Installation Requirements
- Python 3.11 or higher
- pip wheel files for all dependencies
- Compatible C++ redistributables for Windows

## 3. Network Access Requirements

### 3.1 Internal Network Ports
The following ports must be accessible within the internal network:

| Service | Port | Protocol | Direction |
|---------|------|----------|-----------|
| Streamlit UI | 8501 | TCP | Inbound |
| Ollama API | 11434 | HTTP | Outbound (from app) |
| Qdrant API | 6333 | HTTP/gRPC | Outbound (from app) |
| PostgreSQL | 5432 | TCP | Outbound (from app) |
| Redis | 6379 | TCP | Outbound (from app) |

### 3.2 Firewall Rules Required
```
# Inbound Rules
- Allow TCP 8501 from user subnet to application server

# Outbound Rules (from application server)
- Allow TCP 11434 to Ollama server
- Allow TCP 6333 to Qdrant server
- Allow TCP 5432 to PostgreSQL server
- Allow TCP 6379 to Redis server
```

## 4. File System Requirements

### 4.1 Directory Permissions
The application requires read/write access to:
- `/uploads` - Document upload directory
- `/logs` - Application logs
- `/temp` - Temporary file processing
- `/config` - Configuration files

### 4.2 Storage Requirements
- Minimum 50GB for document storage
- 10GB for application and dependencies
- 20GB for vector database storage
- 5GB for PostgreSQL data

## 5. Security Considerations

### 5.1 Authentication Services
- No external authentication services required
- Local user database in PostgreSQL
- JWT tokens for session management

### 5.2 SSL/TLS Requirements
- Self-signed certificates acceptable for internal use
- Certificate authority not required
- HTTPS recommended for all services

### 5.3 Secrets Management
Required secrets that must be configured:
- PostgreSQL password
- Redis password (if enabled)
- JWT secret key
- Application secret key

## 6. Pre-deployment Checklist

### 6.1 Service Availability
- [ ] Ollama service installed and accessible
- [ ] Qdrant service installed and accessible
- [ ] PostgreSQL installed with database created
- [ ] Redis service installed and accessible

### 6.2 Model Files
- [ ] Ollama models pre-downloaded
- [ ] Sentence transformer models cached
- [ ] All Python packages available offline

### 6.3 Configuration Files
- [ ] app_config.yml configured
- [ ] Environment variables set
- [ ] Database schemas initialized
- [ ] Vector collections created

### 6.4 Network Connectivity
- [ ] All services pingable from application server
- [ ] Firewall rules configured
- [ ] DNS resolution working (or hosts file configured)

## 7. Offline Package Repository Setup

For closed environments, set up a local PyPI mirror:

```bash
# Download all packages
pip download -r Requirements.txt -d ./offline_packages

# Install from local directory
pip install --no-index --find-links ./offline_packages -r Requirements.txt
```

## 8. Docker Considerations

If using Docker in the closed environment:
- All images must be pre-pulled and saved
- Private registry required for image distribution
- Docker compose file must use local registry URLs

## 9. Monitoring Requirements

No external monitoring services required. Local monitoring through:
- Application logs in `/logs` directory
- PostgreSQL query logs
- Service health endpoints

## 10. Streamlit Chat Applications ✅ **FULLY IMPLEMENTED**

### 10.1 Basic Chat Interface Components
- **Purpose**: Web-based chat interface connecting local Ollama to RAG system
- **Files Created**:
  - `chat_app.py` - Standard Streamlit application
  - `Start-Chat.ps1` - Basic Windows launcher script
  - `CHAT_USAGE_GUIDE.md` - Comprehensive usage documentation

### 10.2 Enhanced Chat Interface ✅ **NEW - ADVANCED VERSION**
- **Purpose**: Advanced chat interface with full Windows integration and debugging
- **Files Created**:
  - `enhanced_chat_app.py` - Advanced Streamlit application with enhanced features
  - `Start-Enhanced-Chat.ps1` - Enhanced Windows launcher with system detection
  - `test_enhanced_integration.py` - Comprehensive integration test suite

### 10.3 Enhanced Features Implemented
- **Conversation Memory**: Context-aware prompts maintaining conversation history
- **Windows System Detection**: Automatic CUDA/CPU detection and system optimization
- **Advanced File Handling**: Clickable Windows file paths with Explorer integration
- **Search Debugging Panel**: Real-time search performance and result analysis
- **Unicode Support**: Full handling of special characters and Windows path encoding
- **Performance Optimization**: Dynamic settings based on system RAM/CPU specifications
- **Service Health Monitoring**: Real-time status of Ollama, Qdrant, and collections

### 10.4 Windows-Specific Optimizations
- **CUDA Detection**: Automatic GPU capability detection with fallback to CPU
- **Memory Optimization**: Dynamic chunk sizes and result limits based on available RAM:
  - 16GB+: 1000 token chunks, 8 max results, 4000 context window
  - 8-16GB: 800 token chunks, 5 max results, 2048 context window  
  - <8GB: 600 token chunks, 3 max results, 1024 context window
- **Path Handling**: Full Windows path normalization with special character support
- **File Explorer Integration**: Direct file opening from search results
- **Service Integration**: Enhanced Ollama and Qdrant connection management

### 10.5 Launch Commands
```powershell
# Basic chat application
.\Start-Chat.ps1

# Enhanced chat application (recommended)
.\Start-Enhanced-Chat.ps1

# Enhanced with system testing
.\Start-Enhanced-Chat.ps1 -RunTests -Debug

# Network accessible enhanced version
.\Start-Enhanced-Chat.ps1 -Host 0.0.0.0 -Port 8502
```

### 10.6 Configuration and Storage
- **Location**: `C:\MIDAS\config\chat_config.json`
- **Enhanced Settings**: 
  - Model selection with automatic optimization
  - RAG preferences with memory length control
  - Debug mode and panel visibility
  - System performance tuning
- **Conversation Memory**: Persistent across sessions with document frequency tracking
- **Backup Requirements**: Configuration, logs, conversation history

### 10.7 Advanced Integration Status
- **Ollama**: ✅ Full API integration with model optimization
- **Qdrant**: ✅ Multi-collection search with debug information
- **Document Indexer**: ✅ Enhanced retrieval with relevance scoring
- **Structured Data**: ✅ Advanced CSV/Excel search with schema awareness
- **Windows Services**: ✅ Real-time health monitoring and optimization
- **Conversation Context**: ✅ Multi-turn awareness with memory management
- **File System**: ✅ Windows Explorer integration and Unicode support

### 10.8 Debugging and Monitoring Features
- **Search Debug Panel**: Real-time display of:
  - Collections searched and response times
  - Result relevance scores and filtering
  - System performance metrics
  - Error tracking and resolution suggestions
- **Integration Testing**: Comprehensive test suite covering:
  - Windows system capabilities detection
  - Service connectivity and performance
  - Unicode and special character handling
  - File system integration and permissions
- **Performance Monitoring**: System resource usage and optimization recommendations

## 11. Backup Requirements

- PostgreSQL database backups
- Qdrant vector database backups  
- Uploaded documents backup
- Configuration files backup
- **Chat application configuration** (C:\MIDAS\config\)
- **Ollama model files** (C:\Users\[user]\.ollama\models\)
- **Application logs** (C:\MIDAS\logs\)

---

**Note**: This document should be reviewed with your security team to ensure compliance with organizational policies for closed environment deployments.

**System Status**: All core components implemented and ready for deployment on Windows 11.