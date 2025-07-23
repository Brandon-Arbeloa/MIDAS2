# Windows 11 RAG System Setup Guide
Complete step-by-step setup for on-premises RAG system with no cloud dependencies

## ✅ Completed Steps

### 1. Python Environment ✅ DONE
- **Python 3.11.9** installed and verified
- **Virtual environment** `rag_env` created and configured
- **Core packages** installed: streamlit, sentence-transformers, ollama, qdrant-client, psycopg2-binary, redis

### 2. Streamlit Application ✅ RUNNING
- Application successfully running on http://localhost:8501
- All import errors fixed and modules loading properly

## 🔧 Required External Services Setup

### 3. Ollama (Local LLM Server)
**Status**: ⏳ PENDING

#### Download and Install:
```powershell
# Download Ollama for Windows
Invoke-WebRequest -Uri "https://ollama.ai/download/windows" -OutFile "ollama-windows.exe"

# Install Ollama
.\ollama-windows.exe

# Verify installation
ollama --version
```

#### Pull Required Models:
```powershell
# Pull Llama 3.2 3B model (primary)
ollama pull llama3.2:3b

# Pull Phi-3 Mini model (alternative)
ollama pull phi3:mini

# List installed models
ollama list
```

#### Test Ollama:
```powershell
# Test basic functionality
ollama run llama3.2:3b "Hello, world!"

# Check if API server is running
curl http://localhost:11434/api/version
```

### 4. Qdrant Vector Database
**Status**: ⏳ PENDING

#### Option A: Docker Desktop (Recommended)
```powershell
# Install Docker Desktop for Windows first, then:
docker pull qdrant/qdrant

# Run Qdrant container
docker run -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

#### Option B: Windows Executable
```powershell
# Download Qdrant for Windows
Invoke-WebRequest -Uri "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-pc-windows-msvc.zip" -OutFile "qdrant.zip"

# Extract and run
Expand-Archive -Path "qdrant.zip" -DestinationPath "qdrant"
cd qdrant
.\qdrant.exe
```

#### Verify Qdrant:
```powershell
# Test API endpoint
curl http://localhost:6333/collections

# Create test collection
curl -X PUT http://localhost:6333/collections/test -H "Content-Type: application/json" -d '{"vectors": {"size": 384, "distance": "Cosine"}}'
```

### 5. PostgreSQL Database
**Status**: ⏳ PENDING

#### Download and Install:
```powershell
# Download PostgreSQL for Windows
# Visit: https://www.postgresql.org/download/windows/
# Download version 15+ installer

# During installation:
# - Set password for postgres user
# - Remember the password for later configuration
# - Use default port 5432
# - Install pgAdmin (optional but helpful)
```

#### Configure Database:
```sql
-- Connect as postgres user
psql -U postgres

-- Create database
CREATE DATABASE rag_system;

-- Create user
CREATE USER rag_user WITH PASSWORD 'your_secure_password';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE rag_system TO rag_user;

-- Connect to new database
\c rag_system

-- Verify connection
SELECT version();
```

### 6. Redis for Windows
**Status**: ⏳ PENDING

#### Option A: Docker (Recommended)
```powershell
# Run Redis in Docker
docker run -d -p 6379:6379 redis:latest redis-server --appendonly yes
```

#### Option B: WSL2 with Redis
```powershell
# Install WSL2 first, then in Ubuntu:
sudo apt update
sudo apt install redis-server

# Start Redis
sudo service redis-server start

# Test Redis
redis-cli ping
```

#### Option C: Windows Port (Unofficial)
```powershell
# Download from Microsoft Open Tech Redis port
# Visit: https://github.com/microsoftarchive/redis/releases
# Download Redis-x64-*.zip

# Extract and run
.\redis-server.exe
```

## 📋 Verification Script

Create and run this verification script to check all services:

```powershell
# Save as: check_services.ps1

Write-Host "=== MIDAS RAG System Service Check ===" -ForegroundColor Green

# Check Python and virtual environment
Write-Host "`n1. Python Environment:" -ForegroundColor Yellow
python --version
if (Test-Path "rag_env") {
    Write-Host "✅ Virtual environment exists" -ForegroundColor Green
} else {
    Write-Host "❌ Virtual environment missing" -ForegroundColor Red
}

# Check Ollama
Write-Host "`n2. Ollama Service:" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 5
    Write-Host "✅ Ollama running - Version: $($response.version)" -ForegroundColor Green
} catch {
    Write-Host "❌ Ollama not accessible" -ForegroundColor Red
}

# Check Qdrant
Write-Host "`n3. Qdrant Service:" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:6333/collections" -TimeoutSec 5
    Write-Host "✅ Qdrant running" -ForegroundColor Green
} catch {
    Write-Host "❌ Qdrant not accessible" -ForegroundColor Red
}

# Check PostgreSQL
Write-Host "`n4. PostgreSQL:" -ForegroundColor Yellow
try {
    $env:PGPASSWORD = "your_password"
    $result = psql -h localhost -U rag_user -d rag_system -c "SELECT version();" 2>$null
    if ($result) {
        Write-Host "✅ PostgreSQL accessible" -ForegroundColor Green
    } else {
        Write-Host "❌ PostgreSQL connection failed" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ PostgreSQL not installed or configured" -ForegroundColor Red
}

# Check Redis
Write-Host "`n5. Redis:" -ForegroundColor Yellow
try {
    if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
        $result = redis-cli ping
        if ($result -eq "PONG") {
            Write-Host "✅ Redis running" -ForegroundColor Green
        } else {
            Write-Host "❌ Redis not responding" -ForegroundColor Red
        }
    } else {
        Write-Host "❌ Redis CLI not found" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Redis not accessible" -ForegroundColor Red
}

# Check Streamlit app
Write-Host "`n6. Streamlit Application:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8501" -TimeoutSec 5 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Streamlit app running" -ForegroundColor Green
    } else {
        Write-Host "❌ Streamlit app not responding" -ForegroundColor Red
    }
} catch {
    Write-Host "❌ Streamlit app not accessible" -ForegroundColor Red
}

Write-Host "`n=== Service Check Complete ===" -ForegroundColor Green
```

## 🔧 Configuration Files

### Environment Variables (.env)
Create `.env` file in project root:
```env
# Database
DATABASE_URL=postgresql://rag_user:your_secure_password@localhost:5432/rag_system

# Redis
REDIS_URL=redis://localhost:6379/0

# Ollama
OLLAMA_BASE_URL=http://localhost:11434

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Application
SECRET_KEY=your-super-secure-secret-key-here
LOG_LEVEL=INFO

# Directories
UPLOAD_DIR=./uploads
TEMP_DIR=./temp
LOG_DIR=./logs
```

### App Configuration (app_config.yml)
Create `config/app_config.yml`:
```yaml
ollama:
  base_url: "http://localhost:11434"
  models:
    - "llama3.2:3b"
    - "phi3:mini"
  default_model: "llama3.2:3b"
  timeout: 30

qdrant:
  host: "localhost"
  port: 6333
  collection_name: "documents"
  vector_size: 384
  distance: "Cosine"

database:
  host: "localhost"
  port: 5432
  database: "rag_system"
  username: "rag_user"
  # Password will be read from environment variable

redis:
  host: "localhost"
  port: 6379
  db: 0

embedding:
  model: "all-MiniLM-L6-v2"
  cache_dir: "./models"

upload:
  max_size_mb: 100
  allowed_extensions:
    - ".txt"
    - ".pdf" 
    - ".docx"
    - ".csv"
    - ".md"
    - ".json"
  upload_dir: "./uploads"
  temp_dir: "./temp"

security:
  session_timeout: 3600
  max_login_attempts: 5
  require_https: false  # Set to true in production
```

## 🚀 Launch Sequence

Once all services are installed and configured:

1. **Start External Services:**
   ```powershell
   # Start PostgreSQL (usually auto-starts)
   # Start Redis (or Docker container)
   # Start Ollama: ollama serve
   # Start Qdrant (or Docker container)
   ```

2. **Activate Environment and Launch App:**
   ```powershell
   # Activate virtual environment
   rag_env\Scripts\activate

   # Launch application
   python -m streamlit run Streamlit_RAG_System.py
   ```

3. **Verify Full Stack:**
   ```powershell
   # Run verification script
   .\check_services.ps1
   ```

## 📝 Next Steps After Setup

1. **Configure Vector Collections:**
   - Create Qdrant collections for documents
   - Set up proper indexing

2. **Download Embedding Models:**
   ```python
   from sentence_transformers import SentenceTransformer
   model = SentenceTransformer('all-MiniLM-L6-v2')
   ```

3. **Initialize Database Schema:**
   - Run database migrations
   - Create necessary tables

4. **Test Document Processing:**
   - Upload test documents
   - Verify RAG pipeline

## 🔒 Security Considerations

- Change all default passwords
- Configure firewall rules
- Use HTTPS in production
- Implement proper authentication
- Regular security updates

## 📞 Support

- Check logs in `./logs` directory
- Review APPLICATION_CONTEXT.md for current status
- Use STARTUP_INSTRUCTIONS.md for recovery procedures
- See EXTERNAL_SERVICES_REQUIREMENTS.md for deployment details