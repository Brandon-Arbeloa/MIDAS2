"""
System Monitoring and Health Check Tasks
Monitors Celery tasks, system resources, and processing status
"""

import os
import sys
import psutil
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

from celery import Task
from celery.result import AsyncResult
from celery_config import app
from celery.utils.log import get_task_logger

# Windows-specific imports
if sys.platform == 'win32':
    import win32api
    import win32con
    import win32process
    import win32pdh

logger = get_task_logger(__name__)

class MonitoringTask(Task):
    """Base class for monitoring tasks"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log monitoring task failures"""
        logger.error(f"Monitoring task {task_id} failed: {exc}")

@app.task(base=MonitoringTask, name='tasks.monitoring.system_health_check')
def system_health_check() -> Dict[str, Any]:
    """
    Perform comprehensive system health check
    """
    health_status = {
        'timestamp': datetime.now().isoformat(),
        'status': 'healthy',
        'checks': {},
        'warnings': [],
        'errors': []
    }
    
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        health_status['checks']['cpu'] = {
            'usage_percent': cpu_percent,
            'core_count': psutil.cpu_count(),
            'status': 'ok' if cpu_percent < 80 else 'warning'
        }
        if cpu_percent > 80:
            health_status['warnings'].append(f"High CPU usage: {cpu_percent}%")
        
        # Memory usage
        memory = psutil.virtual_memory()
        health_status['checks']['memory'] = {
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'used_percent': memory.percent,
            'status': 'ok' if memory.percent < 85 else 'warning'
        }
        if memory.percent > 85:
            health_status['warnings'].append(f"High memory usage: {memory.percent}%")
        
        # Disk usage
        disk_checks = {}
        for partition in psutil.disk_partitions():
            if partition.fstype:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_checks[partition.mountpoint] = {
                        'total_gb': round(usage.total / (1024**3), 2),
                        'free_gb': round(usage.free / (1024**3), 2),
                        'used_percent': usage.percent,
                        'status': 'ok' if usage.percent < 90 else 'warning'
                    }
                    if usage.percent > 90:
                        health_status['warnings'].append(
                            f"Low disk space on {partition.mountpoint}: {usage.percent}% used"
                        )
                except PermissionError:
                    continue
        health_status['checks']['disk'] = disk_checks
        
        # Redis connectivity
        try:
            from redis import Redis
            redis_client = Redis.from_url(app.conf.broker_url)
            redis_ping = redis_client.ping()
            redis_info = redis_client.info()
            health_status['checks']['redis'] = {
                'connected': redis_ping,
                'version': redis_info.get('redis_version', 'unknown'),
                'used_memory_mb': round(redis_info.get('used_memory', 0) / (1024**2), 2),
                'connected_clients': redis_info.get('connected_clients', 0),
                'status': 'ok'
            }
        except Exception as e:
            health_status['checks']['redis'] = {
                'connected': False,
                'error': str(e),
                'status': 'error'
            }
            health_status['errors'].append(f"Redis connection failed: {e}")
            health_status['status'] = 'degraded'
        
        # Celery workers
        try:
            inspector = app.control.inspect()
            active_workers = inspector.active()
            if active_workers:
                worker_count = len(active_workers)
                total_tasks = sum(len(tasks) for tasks in active_workers.values())
                health_status['checks']['celery'] = {
                    'worker_count': worker_count,
                    'active_tasks': total_tasks,
                    'workers': list(active_workers.keys()),
                    'status': 'ok'
                }
            else:
                health_status['checks']['celery'] = {
                    'worker_count': 0,
                    'status': 'warning'
                }
                health_status['warnings'].append("No Celery workers detected")
        except Exception as e:
            health_status['checks']['celery'] = {
                'error': str(e),
                'status': 'error'
            }
            health_status['errors'].append(f"Celery inspection failed: {e}")
        
        # Windows-specific checks
        if sys.platform == 'win32':
            health_status['checks']['windows'] = get_windows_metrics()
        
        # Overall status determination
        if health_status['errors']:
            health_status['status'] = 'unhealthy'
        elif health_status['warnings']:
            health_status['status'] = 'degraded'
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status['status'] = 'error'
        health_status['errors'].append(f"Health check error: {str(e)}")
    
    # Save health status
    save_health_status(health_status)
    
    return health_status

@app.task(base=MonitoringTask, name='tasks.monitoring.check_task_queue')
def check_task_queue() -> Dict[str, Any]:
    """
    Monitor Celery task queue status
    """
    queue_status = {
        'timestamp': datetime.now().isoformat(),
        'queues': {},
        'failed_tasks': [],
        'slow_tasks': []
    }
    
    try:
        inspector = app.control.inspect()
        
        # Active tasks
        active = inspector.active()
        if active:
            for worker, tasks in active.items():
                queue_status['queues'][worker] = {
                    'active_count': len(tasks),
                    'tasks': []
                }
                for task in tasks:
                    task_info = {
                        'id': task['id'],
                        'name': task['name'],
                        'args': str(task['args'])[:100],  # Truncate long args
                        'time_start': task.get('time_start', 0)
                    }
                    
                    # Check for slow tasks (running > 5 minutes)
                    if task.get('time_start'):
                        runtime = time.time() - task['time_start']
                        if runtime > 300:  # 5 minutes
                            queue_status['slow_tasks'].append({
                                'task_id': task['id'],
                                'name': task['name'],
                                'runtime_seconds': runtime
                            })
                    
                    queue_status['queues'][worker]['tasks'].append(task_info)
        
        # Reserved tasks
        reserved = inspector.reserved()
        if reserved:
            for worker, tasks in reserved.items():
                if worker not in queue_status['queues']:
                    queue_status['queues'][worker] = {}
                queue_status['queues'][worker]['reserved_count'] = len(tasks)
        
        # Check for failed tasks in result backend
        # (This is a simplified check - in production would query result backend)
        
    except Exception as e:
        logger.error(f"Queue check failed: {e}")
        queue_status['error'] = str(e)
    
    return queue_status

@app.task(base=MonitoringTask, name='tasks.monitoring.cleanup_old_tasks')
def cleanup_old_tasks(days: int = 7) -> Dict[str, int]:
    """
    Clean up old task results and temporary files
    """
    cleanup_results = {
        'deleted_results': 0,
        'deleted_files': 0,
        'freed_space_mb': 0,
        'errors': []
    }
    
    try:
        # Clean up old task results from SQLite
        from sqlalchemy import create_engine, text
        from celery_config import SQLITE_DB
        
        engine = create_engine(f'sqlite:///{SQLITE_DB}')
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with engine.connect() as conn:
            result = conn.execute(
                text("DELETE FROM celery_taskmeta WHERE date_done < :cutoff"),
                {"cutoff": cutoff_date}
            )
            cleanup_results['deleted_results'] = result.rowcount
            conn.commit()
        
        # Clean up temporary files
        temp_dirs = [
            Path(os.environ.get('TEMP', '/tmp')) / 'midas_processing',
            Path(__file__).parent.parent / 'temp',
            Path(__file__).parent.parent / 'data' / 'temp'
        ]
        
        for temp_dir in temp_dirs:
            if temp_dir.exists():
                for file_path in temp_dir.rglob('*'):
                    if file_path.is_file():
                        file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_age.days > days:
                            try:
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                cleanup_results['deleted_files'] += 1
                                cleanup_results['freed_space_mb'] += file_size / (1024**2)
                            except Exception as e:
                                cleanup_results['errors'].append(f"Failed to delete {file_path}: {e}")
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        cleanup_results['errors'].append(str(e))
    
    logger.info(f"Cleanup complete: {cleanup_results}")
    return cleanup_results

@app.task(base=MonitoringTask, name='tasks.monitoring.generate_task_report')
def generate_task_report(period_hours: int = 24) -> Dict[str, Any]:
    """
    Generate comprehensive task execution report
    """
    report = {
        'period': f'Last {period_hours} hours',
        'generated_at': datetime.now().isoformat(),
        'summary': {},
        'task_stats': {},
        'performance_metrics': {}
    }
    
    try:
        # Query task results from SQLite
        from sqlalchemy import create_engine, text
        from celery_config import SQLITE_DB
        
        engine = create_engine(f'sqlite:///{SQLITE_DB}')
        cutoff_date = datetime.now() - timedelta(hours=period_hours)
        
        with engine.connect() as conn:
            # Task counts by status
            result = conn.execute(
                text("""
                    SELECT status, COUNT(*) as count 
                    FROM celery_taskmeta 
                    WHERE date_done > :cutoff 
                    GROUP BY status
                """),
                {"cutoff": cutoff_date}
            )
            
            status_counts = {row[0]: row[1] for row in result}
            report['summary']['total_tasks'] = sum(status_counts.values())
            report['summary']['successful'] = status_counts.get('SUCCESS', 0)
            report['summary']['failed'] = status_counts.get('FAILURE', 0)
            report['summary']['pending'] = status_counts.get('PENDING', 0)
            
            # Task counts by name
            result = conn.execute(
                text("""
                    SELECT task_id, COUNT(*) as count, 
                           AVG(JULIANDAY(date_done) - JULIANDAY(date_done)) * 86400 as avg_duration
                    FROM celery_taskmeta 
                    WHERE date_done > :cutoff 
                    GROUP BY task_id
                    ORDER BY count DESC
                """),
                {"cutoff": cutoff_date}
            )
            
            for row in result:
                task_name = row[0] if row[0] else 'unknown'
                report['task_stats'][task_name] = {
                    'count': row[1],
                    'avg_duration_seconds': row[2] if row[2] else 0
                }
        
        # Calculate performance metrics
        if report['summary']['total_tasks'] > 0:
            report['performance_metrics']['success_rate'] = round(
                (report['summary']['successful'] / report['summary']['total_tasks']) * 100, 2
            )
            report['performance_metrics']['failure_rate'] = round(
                (report['summary']['failed'] / report['summary']['total_tasks']) * 100, 2
            )
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        report['error'] = str(e)
    
    # Save report
    save_task_report(report)
    
    return report

# Utility functions

def get_windows_metrics() -> Dict[str, Any]:
    """Get Windows-specific performance metrics"""
    metrics = {}
    
    if sys.platform != 'win32':
        return metrics
    
    try:
        # Get handle count
        process = psutil.Process()
        metrics['handle_count'] = process.num_handles()
        
        # Get thread count
        metrics['thread_count'] = process.num_threads()
        
        # Get Windows version
        metrics['windows_version'] = sys.getwindowsversion().major
        
    except Exception as e:
        logger.warning(f"Failed to get Windows metrics: {e}")
    
    return metrics

def save_health_status(status: Dict[str, Any]):
    """Save health status to file"""
    status_file = Path(__file__).parent / 'data' / 'health_status.json'
    status_file.parent.mkdir(exist_ok=True)
    
    try:
        # Keep history of last 100 checks
        history = []
        if status_file.exists():
            with open(status_file, 'r') as f:
                data = json.load(f)
                history = data.get('history', [])
        
        history.append(status)
        history = history[-100:]  # Keep last 100
        
        with open(status_file, 'w') as f:
            json.dump({
                'latest': status,
                'history': history
            }, f, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to save health status: {e}")

def save_task_report(report: Dict[str, Any]):
    """Save task report to file"""
    report_file = Path(__file__).parent / 'data' / f"task_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.parent.mkdir(exist_ok=True)
    
    try:
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Also save as latest report
        latest_file = report_file.parent / 'latest_task_report.json'
        with open(latest_file, 'w') as f:
            json.dump(report, f, indent=2)
    
    except Exception as e:
        logger.error(f"Failed to save task report: {e}")

# Export tasks
__all__ = [
    'system_health_check',
    'check_task_queue',
    'cleanup_old_tasks',
    'generate_task_report'
]