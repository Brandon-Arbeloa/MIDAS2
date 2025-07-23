# 🤖 MIDAS RAG System - Enterprise AI Document Assistant

**100% On-Premises | Government-Ready | Zero Cloud Dependencies | Windows 11 Optimized**

A complete Retrieval-Augmented Generation system with comprehensive security hardening, designed for secure enterprise environments with local LLM processing, document analysis, and data visualization.

## 📋 Current Status
**Last Updated:** 2025-07-22  
**Application Status:** ✅ **RUNNING**  
- **FastAPI Backend:** http://localhost:8001  
- **Streamlit Frontend:** http://localhost:8502  
**Development Phase:** Production-ready with comprehensive security hardening

### ✅ Recently Completed (Prompt 17 & 18)
- **Performance Optimization:** Redis caching, connection pooling, Qdrant optimization, batch processing
- **Security Hardening:** Rate limiting, input validation, secure file uploads, audit logging
- **Windows Integration:** Event Log, Windows Defender, EFS/BitLocker, Firewall configuration
- **Incident Response:** PowerShell automation, security monitoring, automated threat response

## 🚀 Quick Start

### Prerequisites
- Windows 11 (64-bit) 
- Python 3.11 or higher
- Docker Desktop (optional)
- Administrator privileges (for security features)

### Installation & Launch

```bash
# 1. Clone repository
git clone https://github.com/yourusername/MIDAS.git
cd MIDAS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up security (requires Administrator)
cd scripts/security
.\setup_security.bat

# 4. Launch FastAPI backend
python backend/main_simple.py

# 5. Launch Streamlit frontend (in new terminal)
streamlit run Streamlit_RAG_System.py
```

**Access at:**
- FastAPI: http://localhost:8001
- Streamlit: http://localhost:8502

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   MIDAS RAG System                          │
│  ┌─────────────────┐    ┌─────────────────────────────────┐│
│  │   React UI      │    │     FastAPI Backend            ││
│  │   (Port 3000)   │    │     (Port 8000/8001)          ││
│  └─────────────────┘    └─────────────────────────────────┘│
│           │                           │                      │
│  ┌─────────────────┐    ┌─────────────────────────────────┐│
│  │  Streamlit UI   │    │    Security Layer              ││
│  │  (Port 8502)    │    │  • Rate Limiting               ││
│  └─────────────────┘    │  • Input Validation            ││
│                         │  • File Security               ││
│  ┌─────────────────┐    │  • Audit Logging              ││
│  │     Ollama      │    └─────────────────────────────────┘│
│  │  (Local LLM)    │                                        │
│  │  (Port 11434)   │    ┌─────────────────────────────────┐│
│  └─────────────────┘    │        Qdrant                   ││
│           │             │   (Vector Database)             ││
│  ┌─────────────────┐    │   (Port 6333)                  ││
│  │   PostgreSQL    │    └─────────────────────────────────┘│
│  │   (Metadata)    │                                        │
│  │   (Port 5432)   │    ┌─────────────────────────────────┐│
│  └─────────────────┘    │      Redis Cache               ││
│                         │   (Performance)                 ││
│                         │   (Port 6379)                   ││
│                         └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 🛡️ Security Features (NEW)

### Comprehensive Security Hardening
- **Redis-based Rate Limiting**: Prevents abuse with progressive delays
- **Input Validation**: SQL injection, XSS, path traversal prevention
- **Secure File Uploads**: Windows Defender integration, file type validation
- **Audit Logging**: Windows Event Log, file-based, and database logging
- **API Security**: CORS, security headers, JWT authentication
- **Database Security**: Parameterized queries, connection encryption
- **Security Monitoring**: Real-time threat detection and alerting
- **Backup Encryption**: BitLocker/EFS integration
- **Windows Firewall**: Automated rule management
- **Incident Response**: PowerShell automation for threat mitigation

## 🛠️ Technology Stack

### Core Components
- **Frontend**: Streamlit + React (with Material-UI)
- **Backend**: FastAPI (Python 3.11)
- **LLM**: Ollama (Llama 3.2, Phi-3, Mistral)
- **Vector DB**: Qdrant (optimized for Windows)
- **Database**: PostgreSQL + SQLite
- **Cache**: Redis (Windows-optimized)
- **Embeddings**: sentence-transformers (local)
- **Monitoring**: Windows Performance Counters + Grafana
- **Security**: Custom middleware + Windows integration

### Windows-Specific Integrations
- Windows Event Log for audit trails
- Windows Defender for malware scanning
- Windows EFS/BitLocker for encryption
- Windows Firewall for network security
- Windows Performance Counters for monitoring
- PowerShell for automation and incident response

## 📋 Features

### Document Processing
- **File Types**: PDF, DOCX, TXT, CSV, XLSX, Markdown, JSON, XML
- **Smart Chunking**: Configurable chunking strategies
- **Metadata Extraction**: Comprehensive file analysis
- **Batch Processing**: Windows multiprocessing optimization
- **Secure Uploads**: Virus scanning, type validation, quarantine

### AI-Powered Search
- **Semantic Search**: Vector similarity search
- **Hybrid Search**: Combines semantic and keyword search
- **Context Windows**: Optimized context management
- **Source Attribution**: Detailed source tracking
- **Real-time Processing**: Streaming responses

### Performance Optimization
- **Redis Caching**: Query, embedding, and result caching
- **Connection Pooling**: Database and service connections
- **Batch Processing**: Optimized for Windows multiprocessing
- **Memory Management**: Automatic garbage collection
- **Qdrant Optimization**: HNSW parameters tuned for Windows

### Security & Compliance
- **Zero Trust Architecture**: Multiple security layers
- **FISMA/FedRAMP Compatible**: Government-ready security
- **Complete Audit Trail**: Comprehensive activity logging
- **Data Sovereignty**: All data stays on-premises
- **Air-Gap Ready**: Works without internet connectivity

## 🔧 Configuration

### Environment Variables (.env)
```bash
# Domain Configuration
DOMAIN_NAME=localhost

# Database Configuration
POSTGRES_DB=midas
POSTGRES_USER=midas_user
POSTGRES_PASSWORD=midas_password
DATABASE_URL=postgresql://midas_user:midas_password@localhost:5432/midas

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Security Configuration
SECRET_KEY=your-secret-key-here-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key-here-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Application Configuration
APP_NAME=MIDAS
APP_VERSION=1.0.0
DEBUG=False
ENVIRONMENT=production

# API Configuration
API_V1_STR=/api/v1
PROJECT_NAME=MIDAS RAG System
BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:8501"]

# File Upload Configuration
MAX_UPLOAD_SIZE=104857600
UPLOAD_FOLDER=uploads

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=midas_documents

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_NUM_PARALLEL=2
OLLAMA_MAX_LOADED_MODELS=2

# Monitoring Configuration
ENABLE_METRICS=true
METRICS_PORT=8090
```

### Security Configuration
```json
{
  "monitoring_interval": 60,
  "enable_email_alerts": false,
  "max_cpu_threshold": 90,
  "max_memory_threshold": 90,
  "max_failed_logins": 5,
  "quarantine_directory": "C:/MIDAS/quarantine",
  "backup_directory": "C:/MIDAS/security_backups",
  "log_directory": "C:/MIDAS/logs",
  "enable_auto_response": true
}
```

## 📁 Project Structure

```
MIDAS/
├── backend/
│   ├── api/              # API routes
│   ├── core/             # Core functionality
│   ├── models/           # Database models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   │   ├── caching/      # Redis cache management
│   │   ├── performance/  # Performance optimization
│   │   └── background/   # Background tasks
│   ├── security/         # Security modules
│   │   ├── windows_rate_limiter.py
│   │   ├── input_validator.py
│   │   ├── secure_file_upload.py
│   │   ├── windows_audit_logger.py
│   │   ├── api_security.py
│   │   ├── database_security.py
│   │   ├── windows_security_monitor.py
│   │   ├── windows_backup_encryption.py
│   │   └── windows_firewall.py
│   └── main.py           # FastAPI application
├── frontend/
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── pages/        # Page components
│   │   ├── services/     # API services
│   │   └── store/        # State management
│   ├── package.json      # Node dependencies
│   └── vite.config.ts    # Vite configuration
├── scripts/
│   ├── backup/           # Backup automation
│   ├── security/         # Security scripts
│   │   ├── incident_response.ps1
│   │   ├── security_automation.py
│   │   └── setup_security.bat
│   └── setup/            # Setup scripts
├── monitoring/
│   ├── grafana/          # Grafana dashboards
│   └── windows_performance_monitor.py
├── config/
│   ├── app_config.yml    # Application config
│   └── logging.yml       # Logging config
├── docker/
│   ├── docker-compose.yml
│   └── docker-compose.production.yml
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
└── docs/
    ├── SECURITY.md
    ├── DEPLOYMENT.md
    └── API.md
```

## 🚦 Development & Deployment

### Development Mode
```bash
# Backend
cd backend
uvicorn main:app --reload --port 8000

# Frontend (React)
cd frontend
npm install
npm run dev

# Frontend (Streamlit)
streamlit run Streamlit_RAG_System.py
```

### Production Deployment (Docker)
```bash
# Build and start all services
docker-compose -f docker-compose.production.yml up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

### Windows Service Installation
```powershell
# Install as Windows service (Administrator required)
.\scripts\setup\install_service.ps1

# Start services
net start "MIDAS Backend"
net start "MIDAS Frontend"
```

## 🔒 Security Operations

### Security Monitoring
```python
# Start security monitoring
python scripts/security/security_automation.py --start

# Run manual security scan
python scripts/security/security_automation.py --scan

# Check security status
python scripts/security/security_automation.py --status
```

### Incident Response
```powershell
# Import incident response module
Import-Module .\scripts\security\incident_response.ps1

# Start incident response
Start-IncidentResponse -IncidentType "SuspiciousActivity"

# Run security check
Start-SecurityCheck -Full

# Emergency lockdown
Invoke-EmergencyLockdown -Reason "Security breach detected"
```

## 📊 Monitoring & Metrics

### Grafana Dashboard
- Access: http://localhost:3000
- Default credentials: admin/admin
- Pre-configured dashboards for:
  - System performance
  - Application metrics
  - Security events
  - Cache performance

### Windows Performance Monitor
- Automatic metric collection
- Prometheus export on port 8090
- Integration with Windows Event Log

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test suites
pytest tests/unit/
pytest tests/integration/
pytest tests/security/

# Run with coverage
pytest --cov=backend tests/

# Run security tests
python -m pytest tests/security/ -v
```

## 🆘 Troubleshooting

### Common Issues

1. **Port Conflicts**
   ```bash
   netstat -an | findstr :8000
   # Kill process using the port
   taskkill /PID [process_id] /F
   ```

2. **Docker Issues**
   ```bash
   # Reset Docker
   docker-compose down -v
   docker system prune -a
   ```

3. **Permission Errors**
   - Run as Administrator for security features
   - Check Windows Defender exclusions

4. **Service Failures**
   - Check Windows Event Log
   - Review logs in C:\MIDAS\logs

### Support Resources
- **Logs**: C:\MIDAS\logs
- **Security Events**: Windows Event Viewer
- **Performance**: Windows Performance Monitor
- **Configuration**: Check .env file

## 📜 License

MIT License - See LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 🏆 Acknowledgments

- Built with security-first approach for enterprise deployment
- Optimized for Windows 11 and government environments
- Designed for air-gap deployment capabilities

---

**🏛️ Enterprise-Grade | 🔒 Security Hardened | 🚀 Performance Optimized | 🏢 Government Ready**