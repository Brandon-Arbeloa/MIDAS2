import os
import subprocess
import logging
import shutil
import json
import schedule
import time
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import tarfile
import psutil
import win32file
import win32api
import win32con
import win32security
import win32service
import win32serviceutil
import pywintypes

# Windows Volume Shadow Copy Service
try:
    import vss
    VSS_AVAILABLE = True
except ImportError:
    VSS_AVAILABLE = False
    logging.warning("VSS module not available. Shadow copy features will be limited.")

logger = logging.getLogger(__name__)

@dataclass
class BackupConfig:
    backup_dir: str = "C:\\MIDAS\\backups"
    retention_days: int = 7
    compression_enabled: bool = True
    compression_level: int = 6
    use_shadow_copy: bool = True
    backup_schedule: str = "02:00"  # Daily at 2 AM
    notification_enabled: bool = True
    encryption_enabled: bool = False
    max_backup_size_gb: int = 50

@dataclass
class BackupJob:
    name: str
    source_paths: List[str]
    backup_type: str  # full, incremental, differential
    enabled: bool = True
    last_backup: Optional[datetime] = None
    success_count: int = 0
    error_count: int = 0

class WindowsVSSManager:
    """Windows Volume Shadow Copy Service Manager"""
    
    def __init__(self):
        self.vss_available = VSS_AVAILABLE
        if not self.vss_available:
            logger.warning("VSS functionality limited without vss module")
    
    def create_shadow_copy(self, volume: str) -> Optional[str]:
        """Create a volume shadow copy and return the shadow copy path"""
        if not self.vss_available:
            logger.warning("VSS not available, using direct file access")
            return None
        
        try:
            # Use vssadmin command as fallback
            result = subprocess.run([
                'vssadmin', 'create', 'shadow', 
                f'/for={volume}',
                '/autoretry=3'
            ], capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                # Parse the output to get shadow copy ID
                lines = result.stdout.split('\n')
                shadow_copy_id = None
                
                for line in lines:
                    if 'Shadow Copy ID:' in line:
                        shadow_copy_id = line.split(':')[1].strip()
                        break
                
                if shadow_copy_id:
                    # Mount the shadow copy
                    shadow_path = f"\\\\?\\GLOBALROOT\\Device\\HarddiskVolumeShadowCopy{shadow_copy_id[-2:]}\\"
                    logger.info(f"Created shadow copy: {shadow_copy_id}")
                    return shadow_path
            
            logger.error(f"Failed to create shadow copy: {result.stderr}")
            return None
            
        except Exception as e:
            logger.error(f"Shadow copy creation failed: {e}")
            return None
    
    def delete_shadow_copy(self, shadow_copy_id: str) -> bool:
        """Delete a specific shadow copy"""
        try:
            result = subprocess.run([
                'vssadmin', 'delete', 'shadows',
                f'/shadow={shadow_copy_id}',
                '/quiet'
            ], capture_output=True, text=True, shell=True)
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Failed to delete shadow copy: {e}")
            return False

class WindowsBackupManager:
    def __init__(self, config: BackupConfig = None):
        self.config = config or BackupConfig()
        self.backup_jobs: Dict[str, BackupJob] = {}
        self.vss_manager = WindowsVSSManager()
        
        # Ensure backup directory exists
        Path(self.config.backup_dir).mkdir(parents=True, exist_ok=True)
        
        # Initialize default backup jobs for MIDAS
        self._initialize_default_jobs()
        
        # Scheduling
        self._scheduler_thread = None
        self._scheduler_running = False
        
        # Backup history
        self.backup_history: List[Dict] = []
        self._load_backup_history()
    
    def _initialize_default_jobs(self):
        """Initialize default backup jobs for MIDAS components"""
        default_jobs = {
            'postgresql_data': BackupJob(
                name='PostgreSQL Data',
                source_paths=['./volumes/postgres-data'],
                backup_type='full',
                enabled=True
            ),
            'qdrant_data': BackupJob(
                name='Qdrant Vector Data',
                source_paths=['./volumes/qdrant-storage'],
                backup_type='full',
                enabled=True
            ),
            'redis_data': BackupJob(
                name='Redis Cache Data',
                source_paths=['./volumes/redis-data'],
                backup_type='incremental',
                enabled=True
            ),
            'application_config': BackupJob(
                name='Application Configuration',
                source_paths=[
                    './backend/core/config.py',
                    './docker-compose.yml',
                    './docker-compose.fastapi.yml',
                    './.env',
                    './secrets',
                    './nginx/nginx.conf'
                ],
                backup_type='full',
                enabled=True
            ),
            'user_data': BackupJob(
                name='User Data and Uploads',
                source_paths=['./data', './logs'],
                backup_type='incremental',
                enabled=True
            ),
            'monitoring_data': BackupJob(
                name='Monitoring and Metrics',
                source_paths=[
                    './monitoring/grafana/dashboards',
                    './volumes/prometheus-data',
                    './volumes/grafana-data'
                ],
                backup_type='incremental',
                enabled=False  # Optional
            )
        }
        
        self.backup_jobs.update(default_jobs)
    
    def _load_backup_history(self):
        """Load backup history from file"""
        history_file = Path(self.config.backup_dir) / 'backup_history.json'
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    self.backup_history = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load backup history: {e}")
                self.backup_history = []
    
    def _save_backup_history(self):
        """Save backup history to file"""
        history_file = Path(self.config.backup_dir) / 'backup_history.json'
        try:
            with open(history_file, 'w') as f:
                json.dump(self.backup_history, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save backup history: {e}")
    
    def create_backup(
        self, 
        job_name: str, 
        force: bool = False,
        use_shadow_copy: bool = None
    ) -> Dict[str, Any]:
        """Create a backup for the specified job"""
        if job_name not in self.backup_jobs:
            return {'success': False, 'error': f'Job {job_name} not found'}
        
        job = self.backup_jobs[job_name]
        if not job.enabled and not force:
            return {'success': False, 'error': f'Job {job_name} is disabled'}
        
        use_shadow_copy = use_shadow_copy if use_shadow_copy is not None else self.config.use_shadow_copy
        
        backup_start_time = datetime.now()
        backup_filename = f"{job_name}_{backup_start_time.strftime('%Y%m%d_%H%M%S')}"
        
        if self.config.compression_enabled:
            backup_filename += '.zip'
            backup_path = Path(self.config.backup_dir) / backup_filename
        else:
            backup_path = Path(self.config.backup_dir) / backup_filename
            backup_path.mkdir(exist_ok=True)
        
        logger.info(f"Starting backup job: {job.name}")
        
        shadow_copy_path = None
        shadow_copy_id = None
        
        try:
            # Create shadow copy if requested
            if use_shadow_copy and self.vss_manager.vss_available:
                # Determine volume for shadow copy (assumes C: drive)
                shadow_copy_path = self.vss_manager.create_shadow_copy("C:")
                if shadow_copy_path:
                    logger.info("Using Volume Shadow Copy for backup")
            
            # Perform the backup
            total_size = 0
            files_backed_up = 0
            errors = []
            
            if self.config.compression_enabled:
                with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, 
                                   compresslevel=self.config.compression_level) as zipf:
                    for source_path in job.source_paths:
                        try:
                            size, count, path_errors = self._add_to_zip(
                                zipf, source_path, shadow_copy_path
                            )
                            total_size += size
                            files_backed_up += count
                            errors.extend(path_errors)
                        except Exception as e:
                            errors.append(f"Failed to backup {source_path}: {e}")
            else:
                for source_path in job.source_paths:
                    try:
                        size, count, path_errors = self._copy_to_directory(
                            source_path, backup_path, shadow_copy_path
                        )
                        total_size += size
                        files_backed_up += count
                        errors.extend(path_errors)
                    except Exception as e:
                        errors.append(f"Failed to backup {source_path}: {e}")
            
            backup_end_time = datetime.now()
            backup_duration = (backup_end_time - backup_start_time).total_seconds()
            
            # Check backup size limit
            backup_size_gb = total_size / (1024**3)
            if backup_size_gb > self.config.max_backup_size_gb:
                logger.warning(f"Backup size ({backup_size_gb:.2f} GB) exceeds limit")
            
            # Record backup result
            backup_result = {
                'job_name': job_name,
                'backup_path': str(backup_path),
                'start_time': backup_start_time.isoformat(),
                'end_time': backup_end_time.isoformat(),
                'duration_seconds': backup_duration,
                'total_size_bytes': total_size,
                'files_count': files_backed_up,
                'success': len(errors) == 0,
                'errors': errors,
                'used_shadow_copy': shadow_copy_path is not None
            }
            
            # Update job statistics
            if backup_result['success']:
                job.success_count += 1
                job.last_backup = backup_end_time
            else:
                job.error_count += 1
            
            # Add to history
            self.backup_history.append(backup_result)
            self._save_backup_history()
            
            # Cleanup shadow copy
            if shadow_copy_id:
                self.vss_manager.delete_shadow_copy(shadow_copy_id)
            
            # Send notification if enabled
            if self.config.notification_enabled:
                self._send_backup_notification(backup_result)
            
            logger.info(f"Backup completed: {job.name} - {backup_duration:.2f}s - {backup_size_gb:.2f} GB")
            return backup_result
            
        except Exception as e:
            logger.error(f"Backup job {job_name} failed: {e}")
            
            # Cleanup shadow copy on error
            if shadow_copy_id:
                self.vss_manager.delete_shadow_copy(shadow_copy_id)
            
            return {
                'job_name': job_name,
                'success': False,
                'error': str(e),
                'start_time': backup_start_time.isoformat(),
                'end_time': datetime.now().isoformat()
            }
    
    def _add_to_zip(
        self, 
        zipf: zipfile.ZipFile, 
        source_path: str, 
        shadow_copy_path: Optional[str]
    ) -> Tuple[int, int, List[str]]:
        """Add files/directories to zip archive"""
        total_size = 0
        files_count = 0
        errors = []
        
        source = Path(source_path)
        
        # Use shadow copy path if available
        if shadow_copy_path and source.is_absolute():
            source_str = str(source).replace('C:', shadow_copy_path.rstrip('\\'))
            source = Path(source_str)
        
        try:
            if source.is_file():
                zipf.write(source, source.name)
                total_size += source.stat().st_size
                files_count += 1
            elif source.is_dir():
                for root, dirs, files in os.walk(source):
                    for file in files:
                        try:
                            file_path = Path(root) / file
                            arc_path = file_path.relative_to(source.parent)
                            zipf.write(file_path, str(arc_path))
                            total_size += file_path.stat().st_size
                            files_count += 1
                        except Exception as e:
                            errors.append(f"Failed to add {file_path}: {e}")
            else:
                errors.append(f"Source path not found: {source}")
                
        except Exception as e:
            errors.append(f"Failed to process {source}: {e}")
        
        return total_size, files_count, errors
    
    def _copy_to_directory(
        self, 
        source_path: str, 
        backup_dir: Path, 
        shadow_copy_path: Optional[str]
    ) -> Tuple[int, int, List[str]]:
        """Copy files/directories to backup directory"""
        total_size = 0
        files_count = 0
        errors = []
        
        source = Path(source_path)
        
        # Use shadow copy path if available
        if shadow_copy_path and source.is_absolute():
            source_str = str(source).replace('C:', shadow_copy_path.rstrip('\\'))
            source = Path(source_str)
        
        try:
            if source.is_file():
                dest = backup_dir / source.name
                shutil.copy2(source, dest)
                total_size += source.stat().st_size
                files_count += 1
            elif source.is_dir():
                dest = backup_dir / source.name
                shutil.copytree(source, dest, dirs_exist_ok=True)
                
                # Calculate size
                for root, dirs, files in os.walk(dest):
                    for file in files:
                        file_path = Path(root) / file
                        total_size += file_path.stat().st_size
                        files_count += 1
            else:
                errors.append(f"Source path not found: {source}")
                
        except Exception as e:
            errors.append(f"Failed to copy {source}: {e}")
        
        return total_size, files_count, errors
    
    def restore_backup(
        self, 
        backup_path: str, 
        restore_path: str,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """Restore from a backup archive"""
        backup_file = Path(backup_path)
        restore_dir = Path(restore_path)
        
        if not backup_file.exists():
            return {'success': False, 'error': 'Backup file not found'}
        
        if restore_dir.exists() and not overwrite:
            return {'success': False, 'error': 'Restore path exists and overwrite not allowed'}
        
        logger.info(f"Restoring backup from {backup_path} to {restore_path}")
        
        try:
            restore_dir.mkdir(parents=True, exist_ok=True)
            
            if backup_file.suffix == '.zip':
                with zipfile.ZipFile(backup_file, 'r') as zipf:
                    zipf.extractall(restore_dir)
            else:
                # Assume directory backup
                if backup_file.is_dir():
                    shutil.copytree(backup_file, restore_dir, dirs_exist_ok=overwrite)
                else:
                    return {'success': False, 'error': 'Unknown backup format'}
            
            logger.info(f"Backup restored successfully to {restore_path}")
            return {
                'success': True,
                'backup_path': backup_path,
                'restore_path': restore_path,
                'restored_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def cleanup_old_backups(self) -> Dict[str, Any]:
        """Remove backups older than retention period"""
        cutoff_date = datetime.now() - timedelta(days=self.config.retention_days)
        backup_dir = Path(self.config.backup_dir)
        
        removed_count = 0
        removed_size = 0
        errors = []
        
        try:
            for backup_file in backup_dir.iterdir():
                if backup_file.is_file() and backup_file.suffix in ['.zip', '.tar.gz']:
                    # Parse date from filename
                    try:
                        # Expected format: jobname_YYYYMMDD_HHMMSS.zip
                        parts = backup_file.stem.split('_')
                        if len(parts) >= 3:
                            date_str = f"{parts[-2]}_{parts[-1]}"
                            backup_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                            
                            if backup_date < cutoff_date:
                                file_size = backup_file.stat().st_size
                                backup_file.unlink()
                                removed_count += 1
                                removed_size += file_size
                                logger.info(f"Removed old backup: {backup_file.name}")
                                
                    except ValueError:
                        # Skip files that don't match expected format
                        continue
                        
                elif backup_file.is_dir():
                    # Handle directory backups
                    try:
                        # Use directory modification time
                        dir_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                        if dir_time < cutoff_date:
                            shutil.rmtree(backup_file)
                            removed_count += 1
                            logger.info(f"Removed old backup directory: {backup_file.name}")
                    except Exception as e:
                        errors.append(f"Failed to remove {backup_file}: {e}")
            
            # Clean up backup history
            self.backup_history = [
                entry for entry in self.backup_history
                if datetime.fromisoformat(entry['start_time']) >= cutoff_date
            ]
            self._save_backup_history()
            
            logger.info(f"Cleanup completed: {removed_count} backups removed, {removed_size / (1024**2):.2f} MB freed")
            
            return {
                'success': True,
                'removed_count': removed_count,
                'removed_size_mb': removed_size / (1024**2),
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_backup_notification(self, backup_result: Dict[str, Any]):
        """Send backup completion notification"""
        try:
            # Write notification to Windows Event Log
            import win32evtlog
            import win32evtlogutil
            
            event_type = win32evtlog.EVENTLOG_INFORMATION_TYPE if backup_result['success'] else win32evtlog.EVENTLOG_ERROR_TYPE
            event_message = f"MIDAS Backup {backup_result['job_name']}: {'SUCCESS' if backup_result['success'] else 'FAILED'}"
            
            if backup_result['success']:
                event_message += f" - {backup_result['files_count']} files, {backup_result['total_size_bytes'] / (1024**2):.2f} MB"
            else:
                event_message += f" - Errors: {len(backup_result.get('errors', []))}"
            
            win32evtlogutil.ReportEvent(
                "MIDAS Backup",
                1,  # Event ID
                eventType=event_type,
                strings=[event_message]
            )
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
    
    def start_scheduler(self):
        """Start the backup scheduler"""
        if self._scheduler_running:
            logger.warning("Scheduler is already running")
            return
        
        schedule.clear()
        
        # Schedule daily backups
        schedule.every().day.at(self.config.backup_schedule).do(self._run_scheduled_backups)
        
        # Schedule weekly cleanup
        schedule.every().sunday.at("01:00").do(self.cleanup_old_backups)
        
        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info(f"Backup scheduler started - daily backups at {self.config.backup_schedule}")
    
    def stop_scheduler(self):
        """Stop the backup scheduler"""
        self._scheduler_running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        
        schedule.clear()
        logger.info("Backup scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._scheduler_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)
    
    def _run_scheduled_backups(self):
        """Run all enabled backup jobs"""
        logger.info("Running scheduled backups")
        
        for job_name, job in self.backup_jobs.items():
            if job.enabled:
                try:
                    result = self.create_backup(job_name)
                    if result['success']:
                        logger.info(f"Scheduled backup completed: {job_name}")
                    else:
                        logger.error(f"Scheduled backup failed: {job_name} - {result.get('error', 'Unknown error')}")
                except Exception as e:
                    logger.error(f"Scheduled backup error for {job_name}: {e}")
    
    def get_backup_status(self) -> Dict[str, Any]:
        """Get overall backup system status"""
        total_backups = len(self.backup_history)
        successful_backups = len([b for b in self.backup_history if b['success']])
        failed_backups = total_backups - successful_backups
        
        # Calculate total backup size
        backup_dir = Path(self.config.backup_dir)
        total_size = 0
        backup_count = 0
        
        if backup_dir.exists():
            for item in backup_dir.iterdir():
                if item.is_file():
                    total_size += item.stat().st_size
                    backup_count += 1
                elif item.is_dir():
                    for root, dirs, files in os.walk(item):
                        for file in files:
                            total_size += (Path(root) / file).stat().st_size
                    backup_count += 1
        
        # Get recent backup history
        recent_backups = sorted(
            self.backup_history,
            key=lambda x: x['start_time'],
            reverse=True
        )[:10]
        
        return {
            'status': 'active' if self._scheduler_running else 'stopped',
            'total_jobs': len(self.backup_jobs),
            'enabled_jobs': len([j for j in self.backup_jobs.values() if j.enabled]),
            'total_backups_created': total_backups,
            'successful_backups': successful_backups,
            'failed_backups': failed_backups,
            'total_backup_size_gb': total_size / (1024**3),
            'backup_count': backup_count,
            'retention_days': self.config.retention_days,
            'last_cleanup': None,  # TODO: Track last cleanup time
            'recent_backups': recent_backups,
            'vss_available': self.vss_manager.vss_available,
            'backup_directory': str(backup_dir),
            'scheduler_running': self._scheduler_running
        }
    
    def get_job_status(self, job_name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific backup job"""
        if job_name not in self.backup_jobs:
            return None
        
        job = self.backup_jobs[job_name]
        job_backups = [b for b in self.backup_history if b['job_name'] == job_name]
        
        return {
            'name': job.name,
            'enabled': job.enabled,
            'backup_type': job.backup_type,
            'source_paths': job.source_paths,
            'last_backup': job.last_backup.isoformat() if job.last_backup else None,
            'success_count': job.success_count,
            'error_count': job.error_count,
            'total_backups': len(job_backups),
            'recent_backups': job_backups[-5:] if job_backups else []
        }

# Global backup manager instance
backup_manager: Optional[WindowsBackupManager] = None

def initialize_backup_manager(config: BackupConfig = None) -> WindowsBackupManager:
    global backup_manager
    backup_manager = WindowsBackupManager(config)
    return backup_manager

def get_backup_manager() -> WindowsBackupManager:
    if backup_manager is None:
        raise RuntimeError("Backup manager not initialized")
    return backup_manager

# Command line interface
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='MIDAS Windows Backup Manager')
    parser.add_argument('--backup', help='Create backup for specific job')
    parser.add_argument('--restore', nargs=2, metavar=('BACKUP_PATH', 'RESTORE_PATH'), help='Restore from backup')
    parser.add_argument('--cleanup', action='store_true', help='Clean up old backups')
    parser.add_argument('--status', action='store_true', help='Show backup status')
    parser.add_argument('--start-scheduler', action='store_true', help='Start backup scheduler')
    parser.add_argument('--list-jobs', action='store_true', help='List all backup jobs')
    
    args = parser.parse_args()
    
    # Initialize backup manager
    manager = initialize_backup_manager()
    
    if args.backup:
        result = manager.create_backup(args.backup, force=True)
        print(json.dumps(result, indent=2))
    
    elif args.restore:
        result = manager.restore_backup(args.restore[0], args.restore[1])
        print(json.dumps(result, indent=2))
    
    elif args.cleanup:
        result = manager.cleanup_old_backups()
        print(json.dumps(result, indent=2))
    
    elif args.status:
        status = manager.get_backup_status()
        print(json.dumps(status, indent=2))
    
    elif args.start_scheduler:
        manager.start_scheduler()
        print("Backup scheduler started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            manager.stop_scheduler()
            print("\nScheduler stopped.")
    
    elif args.list_jobs:
        for job_name in manager.backup_jobs:
            status = manager.get_job_status(job_name)
            print(f"{job_name}: {status['name']} ({'enabled' if status['enabled'] else 'disabled'})")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    main()