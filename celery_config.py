"""
MIDAS Celery Configuration for Windows 11
Background task processing with Redis broker and PostgreSQL backend
"""

import os
import sys
from pathlib import Path
from kombu import Queue
from celery import Celery
from datetime import timedelta

# Windows-specific configurations
if sys.platform == 'win32':
    # Required for Windows subprocess handling
    os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')

# Base directory
BASE_DIR = Path(__file__).parent

# Redis configuration (local Windows installation)
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_DB', 0))
REDIS_URL = f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'

# PostgreSQL configuration (for result backend)
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'midas_user')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'midas_password')
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', 5432))
POSTGRES_DB = os.environ.get('POSTGRES_DB', 'midas_tasks')

# SQLite fallback for development
SQLITE_DB = BASE_DIR / 'data' / 'celery_results.db'
SQLITE_DB.parent.mkdir(exist_ok=True)

# Create Celery app
app = Celery('midas')

# Celery configuration
app.conf.update(
    # Broker settings (Redis)
    broker_url=REDIS_URL,
    
    # Result backend (SQLite for now, PostgreSQL when available)
    result_backend=f'db+sqlite:///{SQLITE_DB}',
    # result_backend=f'db+postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}',
    
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Windows-specific: Use solo pool for development
    # Change to 'threads' or 'eventlet' for production
    worker_pool='solo',
    
    # Task result expiration (24 hours)
    result_expires=86400,
    
    # Task execution time limits
    task_soft_time_limit=300,  # 5 minutes soft limit
    task_time_limit=600,  # 10 minutes hard limit
    
    # Task routing
    task_routes={
        'tasks.document.*': {'queue': 'documents'},
        'tasks.analysis.*': {'queue': 'analysis'},
        'tasks.monitoring.*': {'queue': 'monitoring'},
    },
    
    # Queue configuration
    task_queues=(
        Queue('default', routing_key='default'),
        Queue('documents', routing_key='documents'),
        Queue('analysis', routing_key='analysis'),
        Queue('monitoring', routing_key='monitoring'),
    ),
    
    # Retry configuration
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        'cleanup-old-tasks': {
            'task': 'tasks.maintenance.cleanup_old_tasks',
            'schedule': timedelta(hours=24),
            'options': {'queue': 'monitoring'}
        },
        'monitor-document-folder': {
            'task': 'tasks.monitoring.check_document_folder',
            'schedule': timedelta(minutes=5),
            'options': {'queue': 'monitoring'}
        },
        'system-health-check': {
            'task': 'tasks.monitoring.system_health_check',
            'schedule': timedelta(minutes=10),
            'options': {'queue': 'monitoring'}
        },
    },
    
    # Windows-specific worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    worker_disable_rate_limits=False,
    
    # Error handling
    task_track_started=True,
    task_send_sent_event=True,
    
    # Windows file locking
    worker_hijack_root_logger=False,
    worker_log_color=False,
)

# Import task modules
app.autodiscover_tasks(['background_tasks'])

# Windows-specific initialization
if sys.platform == 'win32':
    # Ensure proper signal handling on Windows
    from celery.platforms import IS_WINDOWS
    if IS_WINDOWS:
        os.environ.setdefault('CELERY_ALWAYS_EAGER', 'false')

def get_celery_app():
    """Get configured Celery application"""
    return app

# Create worker command for Windows
WINDOWS_WORKER_CMD = [
    sys.executable,
    '-m', 'celery',
    '-A', 'celery_config',
    'worker',
    '--loglevel=info',
    '--pool=solo',  # Required for Windows
    '--concurrency=1',
    '-Q', 'default,documents,analysis,monitoring',
    '-n', 'midas-worker@%h'
]

# Create beat command for Windows
WINDOWS_BEAT_CMD = [
    sys.executable,
    '-m', 'celery',
    '-A', 'celery_config',
    'beat',
    '--loglevel=info'
]

# Create flower command for monitoring
WINDOWS_FLOWER_CMD = [
    sys.executable,
    '-m', 'flower',
    '-A', 'celery_config',
    '--port=5555',
    '--url_prefix=flower'
]

def test_celery_connection():
    """Test Celery and Redis connection"""
    try:
        # Test Redis connection
        from redis import Redis
        redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        redis_client.ping()
        print(f"✅ Redis connection successful: {REDIS_URL}")
        
        # Test Celery connection
        i = app.control.inspect()
        stats = i.stats()
        if stats:
            print("✅ Celery workers detected")
            for worker, info in stats.items():
                print(f"  - Worker: {worker}")
        else:
            print("⚠️ No Celery workers running")
            print(f"  Start worker with: {' '.join(WINDOWS_WORKER_CMD)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

if __name__ == '__main__':
    print("MIDAS Celery Configuration for Windows")
    print("=" * 50)
    print(f"Redis URL: {REDIS_URL}")
    print(f"Result Backend: SQLite ({SQLITE_DB})")
    print(f"Worker Pool: solo (Windows compatible)")
    print("=" * 50)
    test_celery_connection()