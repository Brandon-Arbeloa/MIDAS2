"""
File Utilities Module - Production Grade
Secure and robust file operations with atomic transactions and comprehensive error handling.
"""

import os
import shutil
import hashlib
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Generator, Union, Callable, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager
from dataclasses import dataclass
import mimetypes
import logging
import json
import platform

logger = logging.getLogger(__name__)

# Constants
WINDOWS = platform.system() == 'Windows'
MAX_PATH_LENGTH = 260 if WINDOWS else 4096
TEMP_DIR_PREFIX = "rag_temp_"
UPLOAD_DIR_NAME = "uploads"
LOGS_DIR_NAME = "logs"

@dataclass
class FileOperationResult:
    """Result of a file operation."""
    success: bool
    message: str = ""
    path: Optional[Path] = None
    error_message: Optional[str] = None
    operation_time: float = 0.0
    data: Optional[Any] = None


class FileUtils:
    """
    Enterprise-grade file utilities with security and reliability features.
    
    Features:
    - Atomic file operations with rollback
    - Cross-platform compatibility
    - Secure file handling
    - Comprehensive error handling
    - File integrity verification
    """
    
    def __init__(self, base_dir: Optional[Path] = None, enable_audit: bool = True):
        """
        Initialize FileUtils.
        
        Args:
            base_dir: Base directory for file operations
            enable_audit: Whether to enable audit logging
        """
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.enable_audit = enable_audit
        self._lock = threading.Lock()
        
        # Create necessary directories
        self._init_directories()
        
        # Audit log
        if self.enable_audit:
            self.audit_log_path = self.base_dir / LOGS_DIR_NAME / "file_operations.log"
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _init_directories(self):
        """Initialize required directories."""
        dirs = [
            self.base_dir / UPLOAD_DIR_NAME,
            self.base_dir / LOGS_DIR_NAME,
            self.base_dir / "temp"
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def file_lock(self, file_path: Path, exclusive: bool = True, timeout: float = 10.0):
        """
        Context manager for file locking.
        
        Args:
            file_path: Path to lock
            exclusive: Whether to use exclusive lock
            timeout: Lock timeout in seconds
        """
        lock_path = file_path.with_suffix(file_path.suffix + '.lock')
        lock_file = None
        
        try:
            if WINDOWS:
                # Windows file locking using msvcrt
                import msvcrt
                
                # Create lock file
                lock_file = open(lock_path, 'w')
                
                # Try to acquire lock with timeout
                start_time = time.time()
                while True:
                    try:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except IOError:
                        if time.time() - start_time > timeout:
                            raise TimeoutError(f"Could not acquire lock on {file_path}")
                        time.sleep(0.1)
                
                yield
                
            else:
                # Unix file locking using fcntl
                import fcntl
                
                # Create lock file
                lock_file = open(lock_path, 'w')
                
                # Try to acquire lock with timeout
                start_time = time.time()
                while True:
                    try:
                        if exclusive:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        else:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                        break
                    except IOError:
                        if time.time() - start_time > timeout:
                            raise TimeoutError(f"Could not acquire lock on {file_path}")
                        time.sleep(0.1)
                
                yield
                
        finally:
            if lock_file:
                try:
                    if WINDOWS:
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    
                    lock_file.close()
                    if lock_path.exists():
                        lock_path.unlink()
                except:
                    pass
    
    def move_file_atomic(self, source: Path, destination: Path, 
                        overwrite: bool = False) -> FileOperationResult:
        """
        Atomically move file with rollback capability.
        
        Args:
            source: Source file path
            destination: Destination file path
            overwrite: Whether to overwrite existing file
            
        Returns:
            FileOperationResult: Operation result
        """
        start_time = time.time()
        
        try:
            source = Path(source).resolve()
            destination = Path(destination).resolve()
            
            # Validate paths
            if not source.exists():
                return FileOperationResult(
                    success=False,
                    error_message=f"Source file not found: {source}",
                    operation_time=time.time() - start_time
                )
            
            if not source.is_file():
                return FileOperationResult(
                    success=False,
                    error_message=f"Source is not a file: {source}",
                    operation_time=time.time() - start_time
                )
            
            # Create destination directory if needed
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if destination exists
            if destination.exists() and not overwrite:
                return FileOperationResult(
                    success=False,
                    error_message=f"Destination exists and overwrite=False: {destination}",
                    operation_time=time.time() - start_time
                )
            
            # Perform atomic move
            backup_path = None
            if destination.exists():
                backup_path = destination.with_suffix(destination.suffix + '.backup')
                shutil.copy2(destination, backup_path)
            
            try:
                shutil.move(str(source), str(destination))
                
                # Remove backup on success
                if backup_path and backup_path.exists():
                    backup_path.unlink()
                
                # Log operation
                if self.enable_audit:
                    self._log_operation("move", source, destination, True)
                
                return FileOperationResult(
                    success=True,
                    message=f"File moved successfully from {source} to {destination}",
                    path=destination,
                    operation_time=time.time() - start_time
                )
                
            except Exception as e:
                # Rollback on error
                if backup_path and backup_path.exists():
                    shutil.copy2(backup_path, destination)
                    backup_path.unlink()
                raise e
                
        except Exception as e:
            logger.error(f"Error moving file: {e}")
            
            if self.enable_audit:
                self._log_operation("move", source, destination, False, str(e))
            
            return FileOperationResult(
                success=False,
                error_message=f"Failed to move file: {str(e)}",
                operation_time=time.time() - start_time
            )
    
    def copy_file_atomic(self, source: Path, destination: Path,
                        overwrite: bool = False, verify_checksum: bool = True) -> FileOperationResult:
        """
        Atomically copy file with integrity verification.
        
        Args:
            source: Source file path
            destination: Destination file path
            overwrite: Whether to overwrite existing file
            verify_checksum: Whether to verify file integrity after copy
            
        Returns:
            FileOperationResult: Operation result
        """
        start_time = time.time()
        
        try:
            source = Path(source).resolve()
            destination = Path(destination).resolve()
            
            # Validate source
            if not source.exists():
                return FileOperationResult(
                    success=False,
                    error_message=f"Source file not found: {source}",
                    operation_time=time.time() - start_time
                )
            
            # Create destination directory
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Check destination
            if destination.exists() and not overwrite:
                return FileOperationResult(
                    success=False,
                    error_message=f"Destination exists and overwrite=False: {destination}",
                    operation_time=time.time() - start_time
                )
            
            # Calculate source checksum if verification needed
            source_checksum = None
            if verify_checksum:
                source_checksum = self._calculate_checksum(source)
            
            # Copy with temporary file
            temp_destination = destination.with_suffix(destination.suffix + '.tmp')
            
            try:
                shutil.copy2(str(source), str(temp_destination))
                
                # Verify checksum
                if verify_checksum:
                    dest_checksum = self._calculate_checksum(temp_destination)
                    if source_checksum != dest_checksum:
                        temp_destination.unlink()
                        return FileOperationResult(
                            success=False,
                            error_message="Checksum verification failed",
                            operation_time=time.time() - start_time
                        )
                
                # Atomic rename
                if destination.exists():
                    backup = destination.with_suffix(destination.suffix + '.backup')
                    destination.rename(backup)
                    try:
                        temp_destination.rename(destination)
                        backup.unlink()
                    except:
                        backup.rename(destination)
                        raise
                else:
                    temp_destination.rename(destination)
                
                # Log operation
                if self.enable_audit:
                    self._log_operation("copy", source, destination, True)
                
                return FileOperationResult(
                    success=True,
                    message=f"File copied successfully from {source} to {destination}",
                    path=destination,
                    operation_time=time.time() - start_time
                )
                
            except Exception as e:
                if temp_destination.exists():
                    temp_destination.unlink()
                raise e
                
        except Exception as e:
            logger.error(f"Error copying file: {e}")
            
            if self.enable_audit:
                self._log_operation("copy", source, destination, False, str(e))
            
            return FileOperationResult(
                success=False,
                error_message=f"Failed to copy file: {str(e)}",
                operation_time=time.time() - start_time
            )
    
    def delete_file_secure(self, file_path: Path, secure_delete: bool = False) -> FileOperationResult:
        """
        Securely delete a file.
        
        Args:
            file_path: Path to file to delete
            secure_delete: Whether to overwrite file before deletion
            
        Returns:
            FileOperationResult: Operation result
        """
        start_time = time.time()
        
        try:
            file_path = Path(file_path).resolve()
            
            if not file_path.exists():
                return FileOperationResult(
                    success=True,
                    message="File already does not exist",
                    operation_time=time.time() - start_time
                )
            
            if not file_path.is_file():
                return FileOperationResult(
                    success=False,
                    error_message=f"Path is not a file: {file_path}",
                    operation_time=time.time() - start_time
                )
            
            # Secure delete if requested
            if secure_delete:
                self._secure_overwrite(file_path)
            
            # Delete file
            file_path.unlink()
            
            # Log operation
            if self.enable_audit:
                self._log_operation("delete", file_path, None, True)
            
            return FileOperationResult(
                success=True,
                message=f"File deleted successfully: {file_path}",
                operation_time=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            
            if self.enable_audit:
                self._log_operation("delete", file_path, None, False, str(e))
            
            return FileOperationResult(
                success=False,
                error_message=f"Failed to delete file: {str(e)}",
                operation_time=time.time() - start_time
            )
    
    def _calculate_checksum(self, file_path: Path, algorithm: str = 'sha256') -> str:
        """Calculate file checksum."""
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _secure_overwrite(self, file_path: Path, passes: int = 3):
        """Securely overwrite file before deletion."""
        file_size = file_path.stat().st_size
        
        with open(file_path, 'rb+') as f:
            for _ in range(passes):
                f.seek(0)
                f.write(os.urandom(file_size))
                f.flush()
                os.fsync(f.fileno())
    
    def _log_operation(self, operation: str, source: Path, destination: Optional[Path],
                      success: bool, error: Optional[str] = None):
        """Log file operation for audit trail."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'source': str(source),
            'destination': str(destination) if destination else None,
            'success': success,
            'error': error
        }
        
        try:
            with self._lock:
                with open(self.audit_log_path, 'a') as f:
                    f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get comprehensive file information."""
        try:
            file_path = Path(file_path).resolve()
            
            if not file_path.exists():
                return {'error': 'File not found'}
            
            stat = file_path.stat()
            
            info = {
                'path': str(file_path),
                'name': file_path.name,
                'size': stat.st_size,
                'size_human': self._format_size(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'accessed': datetime.fromtimestamp(stat.st_atime).isoformat(),
                'is_file': file_path.is_file(),
                'is_dir': file_path.is_dir(),
                'exists': True,
                'extension': file_path.suffix,
                'mime_type': mimetypes.guess_type(str(file_path))[0] or 'unknown'
            }
            
            # Add permissions on Unix-like systems
            if not WINDOWS:
                import stat as stat_module
                mode = stat.st_mode
                info['permissions'] = {
                    'owner_read': bool(mode & stat_module.S_IRUSR),
                    'owner_write': bool(mode & stat_module.S_IWUSR),
                    'owner_execute': bool(mode & stat_module.S_IXUSR),
                    'group_read': bool(mode & stat_module.S_IRGRP),
                    'group_write': bool(mode & stat_module.S_IWGRP),
                    'group_execute': bool(mode & stat_module.S_IXGRP),
                    'other_read': bool(mode & stat_module.S_IROTH),
                    'other_write': bool(mode & stat_module.S_IWOTH),
                    'other_execute': bool(mode & stat_module.S_IXOTH),
                }
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return {'error': str(e)}
    
    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Clean up old temporary files.
        
        Args:
            max_age_hours: Maximum age of temp files in hours
            
        Returns:
            Cleanup statistics
        """
        temp_dir = self.base_dir / "temp"
        deleted_count = 0
        deleted_size = 0
        errors = []
        
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            for file_path in temp_dir.rglob('*'):
                if file_path.is_file():
                    try:
                        if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_time:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                    except Exception as e:
                        errors.append(f"Failed to delete {file_path}: {e}")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'deleted_size': deleted_size,
                'deleted_size_human': self._format_size(deleted_size),
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Error during temp file cleanup: {e}")
            return {
                'success': False,
                'error': str(e),
                'deleted_count': deleted_count,
                'deleted_size': deleted_size
            }


# Utility functions
def get_uploaded_files_dir() -> Path:
    """Get the uploaded files directory."""
    upload_dir = Path.cwd() / UPLOAD_DIR_NAME
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_temp_files_dir() -> Path:
    """Get the temporary files directory."""
    temp_dir = Path.cwd() / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def get_logs_dir() -> Path:
    """Get the logs directory."""
    logs_dir = Path.cwd() / LOGS_DIR_NAME
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def validate_file_path(file_path: Union[str, Path]) -> bool:
    """
    Validate file path for security.
    
    Args:
        file_path: Path to validate
        
    Returns:
        Whether path is valid and safe
    """
    try:
        path = Path(file_path).resolve()
        
        # Check for path traversal attempts
        if '..' in str(file_path):
            return False
        
        # Check path length
        if len(str(path)) > MAX_PATH_LENGTH:
            return False
        
        # Check for null bytes
        if '\x00' in str(file_path):
            return False
        
        return True
        
    except Exception:
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Replace problematic characters
    invalid_chars = '<>:"|?*\\/'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Limit length
    name, ext = os.path.splitext(filename)
    if len(filename) > 255:
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext
    
    # Ensure not empty
    if not filename:
        filename = 'unnamed_file'
    
    return filename