# MIDAS Background Processing System

## Overview

The MIDAS Background Processing System uses Celery with Redis as the message broker to handle asynchronous document processing, file monitoring, and system health checks on Windows 11.

## Components

### 1. **Celery Configuration** (`celery_config.py`)
- Windows-optimized Celery setup with Redis broker
- SQLite result backend (PostgreSQL ready)
- Task routing for different queues (documents, analysis, monitoring)
- Beat schedule for periodic tasks

### 2. **Document Processing Tasks** (`background_tasks/document_tasks.py`)
- `process_document_file`: Process individual documents
- `process_document_batch`: Batch document processing
- `extract_document_metadata`: Quick metadata extraction
- `cleanup_old_processed_files`: Maintenance task
- Windows-specific file locking checks
- Automatic retry on failures

### 3. **File Watcher** (`background_tasks/file_watcher.py`)
- Monitors specified directories for new documents
- Automatic processing of supported file types
- Batch processing option for efficiency
- Configurable watch directories
- History tracking to avoid reprocessing

### 4. **Monitoring Tasks** (`background_tasks/monitoring_tasks.py`)
- `system_health_check`: CPU, memory, disk, Redis, and Celery monitoring
- `check_task_queue`: Active task monitoring
- `generate_task_report`: Task execution statistics
- `cleanup_old_tasks`: Database maintenance

### 5. **Streamlit Monitoring Dashboard** (`Streamlit_Task_Monitoring.py`)
- Real-time task monitoring
- System health visualization
- Task execution history
- Live task updates
- Performance metrics

## Setup Instructions

### Prerequisites

1. **Redis for Windows**
   ```powershell
   # Run as Administrator
   .\Setup-Redis-Windows.ps1
   ```

2. **Python Dependencies**
   ```bash
   pip install celery[redis] watchdog psycopg2-binary sqlalchemy apscheduler
   ```

### Starting the Services

1. **Start all services at once:**
   ```powershell
   .\Start-Celery-Services.ps1
   ```
   
   This will start:
   - Celery Worker (processes tasks)
   - Celery Beat (schedules periodic tasks)
   - Flower (web-based monitoring at http://localhost:5555/flower)
   - File Watcher (monitors document directories)

2. **Start the Streamlit monitoring dashboard:**
   ```bash
   streamlit run Streamlit_Task_Monitoring.py
   ```

### Stopping Services

```powershell
.\Stop-Celery-Services.ps1
```

## Usage

### Processing Documents Programmatically

```python
from background_tasks.document_tasks import process_document_file

# Process a single document
result = process_document_file.delay("path/to/document.pdf")
print(f"Task ID: {result.id}")

# Get result
processing_result = result.get(timeout=60)
print(f"Status: {processing_result['status']}")
print(f"Chunks created: {processing_result['chunks_created']}")
```

### Batch Processing

```python
from background_tasks.document_tasks import process_document_batch

file_paths = ["doc1.pdf", "doc2.docx", "doc3.txt"]
result = process_document_batch.delay(file_paths)
batch_result = result.get(timeout=300)
```

### File Watcher

The file watcher automatically monitors these directories:
- `~/Documents/MIDAS_Uploads`
- `~/Downloads`
- `~/Desktop`

To add custom directories:
```bash
python -m background_tasks.file_watcher -d "C:/CustomPath" "D:/AnotherPath"
```

### Monitoring

1. **Web UI (Flower)**: http://localhost:5555/flower
2. **Streamlit Dashboard**: http://localhost:8501
3. **Logs**: Check the `logs/` directory

## Supported File Types

- Documents: `.pdf`, `.docx`, `.doc`, `.txt`, `.rtf`, `.odt`
- Data: `.csv`, `.xlsx`, `.xls`, `.json`, `.xml`
- Other: `.html`, `.md`, `.log`, `.msg`, `.eml`

## Configuration

### Environment Variables

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# PostgreSQL (optional)
POSTGRES_USER=midas_user
POSTGRES_PASSWORD=midas_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=midas_tasks
```

### Task Queues

- `default`: General tasks
- `documents`: Document processing tasks
- `analysis`: Data analysis tasks
- `monitoring`: System monitoring tasks

## Testing

Run the comprehensive test suite:
```bash
python test_background_processing.py
```

This tests:
- Redis connectivity
- Celery worker availability
- Document processing
- Batch processing
- Monitoring tasks
- Cleanup tasks

## Troubleshooting

### Redis Connection Issues
```powershell
# Check Redis service
Get-Service Redis

# Restart Redis
Restart-Service Redis

# Test connection
redis-cli ping
```

### No Workers Available
```powershell
# Check if Celery worker is running
Get-Process | Where-Object {$_.ProcessName -like "*celery*"}

# Start worker manually
python -m celery -A celery_config worker --loglevel=info --pool=solo
```

### Task Not Processing
1. Check worker logs in `logs/celery_worker.log`
2. Verify Redis is running
3. Check task queue in Flower UI
4. Run test script: `python test_background_processing.py`

### Windows-Specific Issues

**File Locking**: The system includes Windows file locking checks to prevent processing files that are still being written.

**Pool Type**: Uses `solo` pool for Windows compatibility. For production, consider using `eventlet`:
```bash
pip install eventlet
# Then update celery_config.py: worker_pool='eventlet'
```

## Performance Tuning

### Batch Processing
- Default batch size: 10 files
- Default batch timeout: 60 seconds
- Adjust in `file_watcher.py` constructor

### Worker Concurrency
- Default: 1 (solo pool)
- For multiple workers: Start multiple instances with different names

### Memory Management
- Task result expiration: 24 hours
- Max tasks per worker child: 50
- Automatic cleanup of old results

## Security Considerations

1. Redis is bound to localhost only
2. File processing uses temporary copies
3. Input validation on file sizes (100MB limit)
4. Sanitized file paths and names
5. User authentication integration ready

## Future Enhancements

1. **PostgreSQL Integration**: Switch from SQLite to PostgreSQL for better performance
2. **Windows Task Scheduler**: Auto-start services on boot
3. **Email Notifications**: Alert on task failures
4. **S3 Integration**: Process files from cloud storage
5. **OCR Support**: Extract text from images
6. **GPU Acceleration**: For ML-based document analysis