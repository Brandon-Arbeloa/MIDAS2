# MIDAS Docker Deployment Guide for Windows 11

This guide provides complete instructions for deploying MIDAS using Docker Desktop on Windows 11.

## Prerequisites

1. **Windows 11** with WSL2 enabled
2. **Docker Desktop** for Windows (latest version)
3. **PowerShell 7+** (recommended)
4. **Git** for Windows
5. At least **16GB RAM** and **50GB free disk space**
6. **NVIDIA GPU** (optional, for Ollama acceleration)

## Quick Start

1. **Clone the repository:**
   ```powershell
   git clone https://github.com/yourusername/MIDAS.git
   cd MIDAS
   ```

2. **Create secrets:**
   ```powershell
   # Generate secure passwords
   -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | % {[char]$_}) | Out-File -NoNewline secrets/postgres_password.txt
   -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | % {[char]$_}) | Out-File -NoNewline secrets/app_secret_key.txt
   ```

3. **Configure environment:**
   ```powershell
   Copy-Item .env.example .env
   # Edit .env with your configuration
   ```

4. **Start services:**
   ```powershell
   .\start-docker.ps1
   ```

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nginx     │────▶│  Streamlit  │────▶│   Ollama    │
│  (Reverse   │     │    (Web     │     │    (LLM)    │
│   Proxy)    │     │    App)     │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
                            │                    │
                    ┌───────┴────────┐          │
                    │                │          │
              ┌─────▼─────┐   ┌─────▼─────┐   │
              │PostgreSQL │   │  Qdrant   │   │
              │(Database) │   │ (Vector   │   │
              │           │   │   DB)     │   │
              └───────────┘   └───────────┘   │
                    │                          │
              ┌─────▼─────┐                   │
              │   Redis   │                   │
              │ (Cache/   │                   │
              │  Queue)   │                   │
              └─────┬─────┘                   │
                    │                         │
         ┌──────────┴──────────┐             │
         │                     │             │
   ┌─────▼─────┐        ┌─────▼─────┐      │
   │  Celery   │        │  Celery   │      │
   │  Worker   │        │   Beat    │      │
   │  (Docs)   │        │(Scheduler)│      │
   └───────────┘        └───────────┘      │
         │                                  │
   ┌─────▼─────┐        ┌─────────────┐   │
   │  Celery   │        │   Flower    │   │
   │  Worker   │        │ (Monitoring)│   │
   │(Analysis) │        └─────────────┘   │
   └───────────┘                          │
                                         │
                    ┌─────────────┐      │
                    │   Backup    │──────┘
                    │   Service   │
                    └─────────────┘
```

## Service Details

### Core Services

1. **Streamlit** (Port 8501)
   - Main web application interface
   - Document upload and search
   - Dashboard creation and visualization

2. **Ollama** (Port 11434)
   - Local LLM inference
   - GPU acceleration support
   - Model management

3. **Qdrant** (Port 6333)
   - Vector database for embeddings
   - Semantic search capabilities
   - High-performance similarity search

4. **PostgreSQL** (Port 5432)
   - Primary data storage
   - User sessions and metadata
   - Dashboard configurations

5. **Redis** (Port 6379)
   - Celery message broker
   - Query result caching
   - Session storage

### Processing Services

6. **Celery Workers**
   - Document processing queue
   - Analysis tasks queue
   - Auto-scaling support

7. **Celery Beat**
   - Scheduled task execution
   - Periodic cleanup jobs
   - System maintenance

8. **Flower** (Port 5555)
   - Celery monitoring dashboard
   - Task history and statistics
   - Worker management

### Infrastructure Services

9. **Nginx** (Port 80/443)
   - Reverse proxy
   - SSL termination
   - Load balancing
   - Static file serving

10. **Backup Service**
    - Automated daily backups
    - Volume snapshots
    - Configurable retention

## Management Scripts

### Starting Services

```powershell
# Start all services
.\start-docker.ps1

# Start specific services
docker-compose up -d postgres redis qdrant
```

### Stopping Services

```powershell
# Stop all services gracefully
.\stop-docker.ps1

# Stop and remove containers
docker-compose down

# Stop and remove everything including volumes
docker-compose down -v
```

### Health Checks

```powershell
# Check service health
.\health-check.ps1

# View service logs
docker-compose logs -f streamlit
docker-compose logs -f celery-worker-docs

# View all logs
docker-compose logs -f
```

### Backup and Restore

```powershell
# Create backup
.\backup-docker.ps1

# Create backup with Ollama models
.\backup-docker.ps1 -IncludeModels

# Restore from backup
.\restore-docker.ps1 -BackupFile "backups/midas-backup-2024-01-01_12-00-00.zip"
```

## Configuration

### Environment Variables (.env)

```env
# Domain Configuration
DOMAIN_NAME=localhost

# Database Configuration
POSTGRES_DB=midas
POSTGRES_USER=midas_user

# Flower Authentication
FLOWER_USER=admin
FLOWER_PASSWORD=admin

# Resource Limits
OLLAMA_NUM_PARALLEL=2
OLLAMA_MAX_LOADED_MODELS=2
```

### Volume Mappings

| Service | Container Path | Host Path | Purpose |
|---------|---------------|-----------|---------|
| Ollama | /root/.ollama | ./volumes/ollama-models | Model storage |
| Qdrant | /qdrant/storage | ./volumes/qdrant-storage | Vector data |
| PostgreSQL | /var/lib/postgresql/data | ./volumes/postgres-data | Database files |
| Redis | /data | ./volumes/redis-data | Cache persistence |
| Streamlit | /app/appdata | ./volumes/streamlit-appdata | Dashboard configs |

### Port Mappings

| Service | Container Port | Host Port | Purpose |
|---------|----------------|-----------|---------|
| Nginx | 80 | 80 | HTTP traffic |
| Nginx | 443 | 443 | HTTPS traffic |
| Streamlit | 8501 | 8501 | Web interface |
| Ollama | 11434 | 11434 | API endpoint |
| Qdrant | 6333 | 6333 | HTTP API |
| Qdrant | 6334 | 6334 | gRPC API |
| PostgreSQL | 5432 | 5432 | Database |
| Redis | 6379 | 6379 | Cache/Queue |
| Flower | 5555 | 5555 | Monitoring |

## Security Considerations

1. **Secrets Management**
   - Store passwords in `secrets/` directory
   - Never commit secrets to version control
   - Use Docker secrets in production

2. **Network Security**
   - All services communicate on internal Docker network
   - Only necessary ports exposed to host
   - Nginx handles external traffic

3. **SSL/TLS**
   - Configure SSL certificates in `nginx/ssl/`
   - Update nginx configuration for HTTPS
   - Use Let's Encrypt for production

4. **Access Control**
   - Flower protected with basic auth
   - PostgreSQL requires authentication
   - Consider adding OAuth2 proxy

## Troubleshooting

### Common Issues

1. **Docker Desktop not running**
   ```powershell
   # Start Docker Desktop
   Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
   ```

2. **Port conflicts**
   ```powershell
   # Find process using port
   netstat -ano | findstr :8501
   
   # Kill process
   taskkill /PID <process_id> /F
   ```

3. **Volume permission issues**
   ```powershell
   # Reset volume permissions
   docker-compose down -v
   Remove-Item -Path volumes/* -Recurse -Force
   .\start-docker.ps1
   ```

4. **Out of memory**
   - Increase Docker Desktop memory limit
   - Reduce worker concurrency
   - Enable swap in WSL2

### Viewing Logs

```powershell
# View specific service logs
docker-compose logs -f streamlit

# View logs with timestamps
docker-compose logs -t -f celery-worker-docs

# View last 100 lines
docker-compose logs --tail=100 postgres
```

### Debugging

```powershell
# Enter container shell
docker-compose exec streamlit /bin/bash

# Run commands in container
docker-compose exec postgres psql -U midas_user -d midas

# Check container resources
docker stats
```

## Performance Tuning

### Ollama Optimization

```yaml
environment:
  - OLLAMA_NUM_PARALLEL=4  # Increase for more concurrent requests
  - OLLAMA_MAX_LOADED_MODELS=3  # Increase if RAM allows
  - OLLAMA_KEEP_ALIVE=10m  # Increase to keep models in memory
```

### PostgreSQL Tuning

Edit `postgres/postgresql.conf`:
```conf
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
work_mem = 16MB
```

### Redis Optimization

Edit `redis/redis.conf`:
```conf
maxmemory 4gb
maxmemory-policy allkeys-lru
```

## Monitoring

### Grafana Integration (Optional)

Add to docker-compose.yml:
```yaml
grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  volumes:
    - grafana-data:/var/lib/grafana
```

### Prometheus Integration (Optional)

Add to docker-compose.yml:
```yaml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus-data:/prometheus
```

## Maintenance

### Daily Tasks
- Check health status: `.\health-check.ps1`
- Review error logs
- Monitor disk usage

### Weekly Tasks
- Review and clean old backups
- Update Docker images
- Check for security updates

### Monthly Tasks
- Test backup restoration
- Review resource usage
- Optimize database

## Support

For issues and questions:
1. Check service logs
2. Run health check script
3. Review troubleshooting section
4. Submit GitHub issue with logs

## License

See LICENSE file in repository root.