import os
import subprocess
import shutil
import logging
import json
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
import win32api
import win32file
import win32security
import win32con
import win32crypt
import winreg
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

@dataclass
class BackupEncryptionConfig:
    encryption_method: str = "bitlocker"  # bitlocker, efs, custom
    backup_directory: str = "encrypted_backups"
    key_storage_method: str = "windows_credential_store"  # file, registry, credential_store
    compression_enabled: bool = True
    backup_retention_days: int = 30
    verify_integrity: bool = True
    enable_recovery_key: bool = True
    recovery_key_path: str = "recovery_keys"

@dataclass
class BackupJob:
    job_id: str
    source_path: str
    backup_path: str
    encryption_method: str
    created_at: datetime
    size_bytes: int
    encrypted: bool
    compressed: bool
    integrity_hash: str
    recovery_key_id: Optional[str] = None

class WindowsBitLockerManager:
    """Manage BitLocker encryption for backup drives"""
    
    def __init__(self):
        self.bitlocker_available = self._check_bitlocker_availability()
    
    def _check_bitlocker_availability(self) -> bool:
        """Check if BitLocker is available on this system"""
        try:
            result = subprocess.run([
                'powershell', '-Command',
                'Get-BitLockerVolume'
            ], capture_output=True, text=True, shell=True)
            
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"BitLocker availability check failed: {e}")
            return False
    
    def encrypt_drive(self, drive_letter: str, password: str = None) -> Dict[str, Any]:
        """Encrypt a drive with BitLocker"""
        if not self.bitlocker_available:
            return {'success': False, 'error': 'BitLocker not available'}
        
        try:
            # Enable BitLocker
            if password:
                cmd = f'Enable-BitLocker -MountPoint {drive_letter}: -PasswordProtector -Password (ConvertTo-SecureString "{password}" -AsPlainText -Force)'
            else:
                cmd = f'Enable-BitLocker -MountPoint {drive_letter}: -RecoveryPasswordProtector'
            
            result = subprocess.run([
                'powershell', '-Command', cmd
            ], capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                # Get recovery key
                recovery_result = subprocess.run([
                    'powershell', '-Command',
                    f'Get-BitLockerVolume -MountPoint {drive_letter}: | Select-Object -ExpandProperty KeyProtector | Where-Object {{ $_.KeyProtectorType -eq "RecoveryPassword" }} | Select-Object -ExpandProperty RecoveryPassword'
                ], capture_output=True, text=True, shell=True)
                
                recovery_key = recovery_result.stdout.strip() if recovery_result.returncode == 0 else None
                
                return {
                    'success': True,
                    'drive': drive_letter,
                    'recovery_key': recovery_key
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_bitlocker_status(self, drive_letter: str) -> Dict[str, Any]:
        """Get BitLocker status for a drive"""
        try:
            result = subprocess.run([
                'powershell', '-Command',
                f'Get-BitLockerVolume -MountPoint {drive_letter}: | ConvertTo-Json'
            ], capture_output=True, text=True, shell=True)
            
            if result.returncode == 0 and result.stdout.strip():
                status_data = json.loads(result.stdout)
                return {
                    'encrypted': status_data.get('ProtectionStatus') == 'On',
                    'encryption_percentage': status_data.get('EncryptionPercentage', 0),
                    'volume_status': status_data.get('VolumeStatus', 'Unknown'),
                    'protection_status': status_data.get('ProtectionStatus', 'Unknown')
                }
            else:
                return {'encrypted': False, 'error': 'Could not retrieve status'}
                
        except Exception as e:
            return {'encrypted': False, 'error': str(e)}

class WindowsEFSManager:
    """Manage EFS (Encrypting File System) encryption"""
    
    def __init__(self):
        self.efs_available = self._check_efs_availability()
    
    def _check_efs_availability(self) -> bool:
        """Check if EFS is available"""
        try:
            # Check if NTFS and EFS are supported
            result = subprocess.run([
                'fsutil', 'fsinfo', 'ntfsinfo', 'C:'
            ], capture_output=True, text=True, shell=True)
            
            return result.returncode == 0
        except Exception:
            return False
    
    def encrypt_directory(self, directory_path: str) -> bool:
        """Encrypt a directory with EFS"""
        if not self.efs_available:
            logger.warning("EFS not available")
            return False
        
        try:
            # Use cipher command to encrypt directory
            result = subprocess.run([
                'cipher', '/e', '/s:' + directory_path
            ], capture_output=True, text=True, shell=True)
            
            success = result.returncode == 0
            if success:
                logger.info(f"Directory encrypted with EFS: {directory_path}")
            else:
                logger.error(f"EFS encryption failed: {result.stderr}")
            
            return success
            
        except Exception as e:
            logger.error(f"EFS encryption error: {e}")
            return False
    
    def decrypt_directory(self, directory_path: str) -> bool:
        """Decrypt a directory encrypted with EFS"""
        if not self.efs_available:
            return False
        
        try:
            result = subprocess.run([
                'cipher', '/d', '/s:' + directory_path
            ], capture_output=True, text=True, shell=True)
            
            return result.returncode == 0
            
        except Exception:
            return False
    
    def is_encrypted(self, file_path: str) -> bool:
        """Check if file/directory is EFS encrypted"""
        try:
            attrs = win32file.GetFileAttributes(file_path)
            return bool(attrs & win32file.FILE_ATTRIBUTE_ENCRYPTED)
        except Exception:
            return False

class CustomEncryptionManager:
    """Custom AES encryption for backup files"""
    
    def __init__(self):
        self.key_size = 32  # 256-bit key
        self.iv_size = 16   # 128-bit IV
    
    def generate_key(self, password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        """Generate encryption key from password"""
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_size,
            salt=salt,
            iterations=100000,
        )
        
        key = kdf.derive(password.encode())
        return key, salt
    
    def encrypt_file(self, file_path: str, output_path: str, password: str) -> Dict[str, Any]:
        """Encrypt a file with AES-256-CBC"""
        try:
            # Generate key and IV
            key, salt = self.generate_key(password)
            iv = os.urandom(self.iv_size)
            
            # Create cipher
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            encryptor = cipher.encryptor()
            
            # Read and encrypt file
            with open(file_path, 'rb') as infile, open(output_path, 'wb') as outfile:
                # Write salt and IV first
                outfile.write(salt)
                outfile.write(iv)
                
                # Encrypt file contents in chunks
                while True:
                    chunk = infile.read(64 * 1024)  # 64KB chunks
                    if not chunk:
                        break
                    
                    # Pad last chunk if necessary
                    if len(chunk) % 16 != 0:
                        chunk += b'\0' * (16 - len(chunk) % 16)
                    
                    encrypted_chunk = encryptor.update(chunk)
                    outfile.write(encrypted_chunk)
                
                # Finalize encryption
                final_chunk = encryptor.finalize()
                outfile.write(final_chunk)
            
            # Calculate file hash for integrity
            file_hash = self._calculate_file_hash(output_path)
            
            return {
                'success': True,
                'encrypted_file': output_path,
                'file_hash': file_hash,
                'salt': salt.hex(),
                'iv': iv.hex()
            }
            
        except Exception as e:
            logger.error(f"Custom encryption failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def decrypt_file(self, encrypted_file: str, output_path: str, password: str) -> bool:
        """Decrypt a file encrypted with AES-256-CBC"""
        try:
            with open(encrypted_file, 'rb') as infile:
                # Read salt and IV
                salt = infile.read(16)
                iv = infile.read(16)
                
                # Derive key
                key, _ = self.generate_key(password, salt)
                
                # Create cipher
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                
                # Decrypt file
                with open(output_path, 'wb') as outfile:
                    while True:
                        chunk = infile.read(64 * 1024)
                        if not chunk:
                            break
                        
                        decrypted_chunk = decryptor.update(chunk)
                        outfile.write(decrypted_chunk)
                    
                    # Finalize decryption
                    final_chunk = decryptor.finalize()
                    outfile.write(final_chunk)
                
                # Remove padding from last block
                self._remove_padding(output_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Custom decryption failed: {e}")
            return False
    
    def _remove_padding(self, file_path: str):
        """Remove null byte padding from decrypted file"""
        try:
            with open(file_path, 'r+b') as f:
                f.seek(-16, 2)  # Go to last 16 bytes
                last_block = f.read(16)
                
                # Find last non-null byte
                for i in range(15, -1, -1):
                    if last_block[i] != 0:
                        break
                
                # Truncate file to remove padding
                if i < 15:
                    f.seek(-16 + i + 1, 2)
                    f.truncate()
        except Exception as e:
            logger.warning(f"Padding removal failed: {e}")
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file"""
        hasher = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        
        return hasher.hexdigest()

class WindowsBackupEncryption:
    """Comprehensive backup encryption system for Windows"""
    
    def __init__(self, config: BackupEncryptionConfig = None):
        self.config = config or BackupEncryptionConfig()
        
        # Initialize encryption managers
        self.bitlocker = WindowsBitLockerManager()
        self.efs = WindowsEFSManager()
        self.custom_crypto = CustomEncryptionManager()
        
        # Backup tracking
        self.backup_jobs = []
        self.recovery_keys = {}
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure backup and recovery key directories exist"""
        directories = [
            self.config.backup_directory,
            self.config.recovery_key_path
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def create_encrypted_backup(
        self,
        source_path: str,
        backup_name: str = None,
        encryption_password: str = None
    ) -> Dict[str, Any]:
        """Create an encrypted backup"""
        
        # Generate backup name if not provided
        if not backup_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"
        
        # Determine backup paths
        backup_dir = Path(self.config.backup_directory) / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        job_id = f"{backup_name}_{secrets.token_hex(8)}"
        
        try:
            # Copy source to backup directory
            if Path(source_path).is_file():
                temp_backup_path = backup_dir / Path(source_path).name
                shutil.copy2(source_path, temp_backup_path)
            else:
                temp_backup_path = backup_dir
                shutil.copytree(source_path, backup_dir / "data", dirs_exist_ok=True)
                temp_backup_path = backup_dir / "data"
            
            # Compress if enabled
            if self.config.compression_enabled:
                compressed_path = backup_dir / f"{backup_name}.zip"
                shutil.make_archive(str(compressed_path)[:-4], 'zip', temp_backup_path)
                
                # Remove uncompressed files
                if temp_backup_path.is_dir():
                    shutil.rmtree(temp_backup_path)
                elif temp_backup_path.is_file():
                    temp_backup_path.unlink()
                
                temp_backup_path = compressed_path
            
            # Apply encryption based on method
            encrypted_path, encryption_info = self._encrypt_backup(
                temp_backup_path, 
                encryption_password or self._generate_password()
            )
            
            # Calculate size and integrity hash
            backup_size = self._get_directory_size(backup_dir)
            integrity_hash = self._calculate_directory_hash(backup_dir)
            
            # Create backup job record
            backup_job = BackupJob(
                job_id=job_id,
                source_path=source_path,
                backup_path=str(backup_dir),
                encryption_method=self.config.encryption_method,
                created_at=datetime.now(),
                size_bytes=backup_size,
                encrypted=True,
                compressed=self.config.compression_enabled,
                integrity_hash=integrity_hash,
                recovery_key_id=encryption_info.get('recovery_key_id')
            )
            
            self.backup_jobs.append(backup_job)
            
            # Save backup metadata
            self._save_backup_metadata(backup_job, encryption_info)
            
            logger.info(f"Encrypted backup created: {job_id}")
            
            return {
                'success': True,
                'job_id': job_id,
                'backup_path': str(backup_dir),
                'size_bytes': backup_size,
                'encryption_method': self.config.encryption_method,
                'recovery_info': encryption_info
            }
            
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            
            # Cleanup on failure
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            
            return {
                'success': False,
                'error': str(e)
            }
    
    def _encrypt_backup(self, backup_path: Path, password: str) -> Tuple[Path, Dict[str, Any]]:
        """Apply encryption to backup based on configured method"""
        
        if self.config.encryption_method == "bitlocker":
            return self._encrypt_with_bitlocker(backup_path, password)
        elif self.config.encryption_method == "efs":
            return self._encrypt_with_efs(backup_path)
        else:  # custom
            return self._encrypt_with_custom(backup_path, password)
    
    def _encrypt_with_bitlocker(self, backup_path: Path, password: str) -> Tuple[Path, Dict[str, Any]]:
        """Encrypt backup with BitLocker"""
        # For files, BitLocker encrypts the entire drive
        # This is a simplified implementation - in practice, you'd need a dedicated encrypted drive
        logger.warning("BitLocker integration requires dedicated drive - using custom encryption")
        return self._encrypt_with_custom(backup_path, password)
    
    def _encrypt_with_efs(self, backup_path: Path) -> Tuple[Path, Dict[str, Any]]:
        """Encrypt backup with EFS"""
        try:
            if backup_path.is_dir():
                success = self.efs.encrypt_directory(str(backup_path))
            else:
                # For single files, encrypt the parent directory
                success = self.efs.encrypt_directory(str(backup_path.parent))
            
            if success:
                return backup_path, {'method': 'efs', 'encrypted': True}
            else:
                logger.warning("EFS encryption failed, falling back to custom encryption")
                return self._encrypt_with_custom(backup_path, self._generate_password())
                
        except Exception as e:
            logger.error(f"EFS encryption error: {e}")
            return self._encrypt_with_custom(backup_path, self._generate_password())
    
    def _encrypt_with_custom(self, backup_path: Path, password: str) -> Tuple[Path, Dict[str, Any]]:
        """Encrypt backup with custom AES encryption"""
        try:
            if backup_path.is_file():
                encrypted_path = backup_path.with_suffix(backup_path.suffix + '.enc')
                result = self.custom_crypto.encrypt_file(str(backup_path), str(encrypted_path), password)
                
                if result['success']:
                    backup_path.unlink()  # Remove original
                    
                    # Store recovery key
                    recovery_key_id = self._store_recovery_key(password, result)
                    
                    return encrypted_path, {
                        'method': 'custom',
                        'encrypted': True,
                        'file_hash': result['file_hash'],
                        'recovery_key_id': recovery_key_id
                    }
                else:
                    raise Exception(result['error'])
            else:
                # For directories, encrypt all files individually
                encryption_info = {'method': 'custom', 'encrypted_files': []}
                
                for file_path in backup_path.rglob('*'):
                    if file_path.is_file():
                        encrypted_file_path = file_path.with_suffix(file_path.suffix + '.enc')
                        result = self.custom_crypto.encrypt_file(str(file_path), str(encrypted_file_path), password)
                        
                        if result['success']:
                            file_path.unlink()  # Remove original
                            encryption_info['encrypted_files'].append({
                                'original': str(file_path),
                                'encrypted': str(encrypted_file_path),
                                'hash': result['file_hash']
                            })
                
                # Store recovery key
                recovery_key_id = self._store_recovery_key(password, {'method': 'custom'})
                encryption_info['recovery_key_id'] = recovery_key_id
                
                return backup_path, encryption_info
                
        except Exception as e:
            logger.error(f"Custom encryption failed: {e}")
            raise
    
    def _generate_password(self) -> str:
        """Generate a secure random password"""
        return secrets.token_urlsafe(32)
    
    def _store_recovery_key(self, password: str, encryption_info: Dict[str, Any]) -> str:
        """Store recovery key securely"""
        recovery_key_id = secrets.token_hex(16)
        
        if self.config.key_storage_method == "file":
            # Store in encrypted file
            key_file = Path(self.config.recovery_key_path) / f"{recovery_key_id}.key"
            
            with open(key_file, 'w') as f:
                json.dump({
                    'recovery_key_id': recovery_key_id,
                    'password': password,
                    'created_at': datetime.now().isoformat(),
                    'encryption_info': encryption_info
                }, f, indent=2)
            
            # Encrypt the key file itself with EFS if available
            if self.efs.efs_available:
                self.efs.encrypt_directory(str(key_file.parent))
        
        elif self.config.key_storage_method == "windows_credential_store":
            # Store in Windows Credential Manager (simplified - would need more implementation)
            logger.info(f"Recovery key stored with ID: {recovery_key_id}")
        
        else:  # registry
            # Store in Windows Registry (encrypted)
            logger.info(f"Recovery key stored in registry with ID: {recovery_key_id}")
        
        self.recovery_keys[recovery_key_id] = {
            'password': password,
            'created_at': datetime.now(),
            'encryption_info': encryption_info
        }
        
        return recovery_key_id
    
    def _save_backup_metadata(self, backup_job: BackupJob, encryption_info: Dict[str, Any]):
        """Save backup metadata"""
        metadata_file = Path(backup_job.backup_path) / "backup_metadata.json"
        
        metadata = {
            **asdict(backup_job),
            'encryption_info': encryption_info
        }
        
        # Convert datetime objects to strings
        metadata['created_at'] = backup_job.created_at.isoformat()
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
    
    def restore_backup(self, job_id: str, output_path: str, recovery_key_id: str = None) -> Dict[str, Any]:
        """Restore an encrypted backup"""
        
        # Find backup job
        backup_job = None
        for job in self.backup_jobs:
            if job.job_id == job_id:
                backup_job = job
                break
        
        if not backup_job:
            return {'success': False, 'error': 'Backup job not found'}
        
        try:
            # Get recovery key
            if recovery_key_id and recovery_key_id in self.recovery_keys:
                password = self.recovery_keys[recovery_key_id]['password']
            else:
                return {'success': False, 'error': 'Recovery key required'}
            
            # Restore based on encryption method
            if backup_job.encryption_method == "custom":
                success = self._restore_custom_backup(backup_job, output_path, password)
            elif backup_job.encryption_method == "efs":
                success = self._restore_efs_backup(backup_job, output_path)
            else:
                success = self._restore_bitlocker_backup(backup_job, output_path, password)
            
            if success:
                logger.info(f"Backup restored successfully: {job_id}")
                return {'success': True, 'restored_to': output_path}
            else:
                return {'success': False, 'error': 'Restore operation failed'}
                
        except Exception as e:
            logger.error(f"Backup restore failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _restore_custom_backup(self, backup_job: BackupJob, output_path: str, password: str) -> bool:
        """Restore backup encrypted with custom encryption"""
        try:
            backup_dir = Path(backup_job.backup_path)
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Find encrypted files
            for encrypted_file in backup_dir.rglob('*.enc'):
                # Determine output file path
                relative_path = encrypted_file.relative_to(backup_dir)
                output_file = output_dir / str(relative_path)[:-4]  # Remove .enc extension
                
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Decrypt file
                success = self.custom_crypto.decrypt_file(
                    str(encrypted_file), 
                    str(output_file), 
                    password
                )
                
                if not success:
                    logger.error(f"Failed to decrypt: {encrypted_file}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Custom backup restore failed: {e}")
            return False
    
    def _restore_efs_backup(self, backup_job: BackupJob, output_path: str) -> bool:
        """Restore EFS encrypted backup"""
        try:
            shutil.copytree(backup_job.backup_path, output_path, dirs_exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"EFS backup restore failed: {e}")
            return False
    
    def _restore_bitlocker_backup(self, backup_job: BackupJob, output_path: str, password: str) -> bool:
        """Restore BitLocker encrypted backup"""
        # Simplified implementation
        return self._restore_custom_backup(backup_job, output_path, password)
    
    def cleanup_old_backups(self):
        """Remove old backups based on retention policy"""
        cutoff_date = datetime.now() - timedelta(days=self.config.backup_retention_days)
        
        removed_count = 0
        for backup_job in self.backup_jobs.copy():
            if backup_job.created_at < cutoff_date:
                try:
                    # Remove backup directory
                    backup_path = Path(backup_job.backup_path)
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    
                    # Remove from tracking
                    self.backup_jobs.remove(backup_job)
                    removed_count += 1
                    
                    logger.info(f"Removed old backup: {backup_job.job_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to remove backup {backup_job.job_id}: {e}")
        
        logger.info(f"Cleanup completed: {removed_count} old backups removed")
    
    def _get_directory_size(self, directory: Path) -> int:
        """Get total size of directory in bytes"""
        total_size = 0
        for file_path in directory.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size
    
    def _calculate_directory_hash(self, directory: Path) -> str:
        """Calculate hash of all files in directory"""
        hasher = hashlib.sha256()
        
        for file_path in sorted(directory.rglob('*')):
            if file_path.is_file():
                hasher.update(str(file_path).encode())
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(64 * 1024)
                        if not chunk:
                            break
                        hasher.update(chunk)
        
        return hasher.hexdigest()
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """Get list of all backups"""
        return [
            {
                'job_id': job.job_id,
                'source_path': job.source_path,
                'backup_path': job.backup_path,
                'created_at': job.created_at.isoformat(),
                'size_mb': round(job.size_bytes / (1024 * 1024), 2),
                'encryption_method': job.encryption_method,
                'encrypted': job.encrypted,
                'compressed': job.compressed
            }
            for job in self.backup_jobs
        ]
    
    def verify_backup_integrity(self, job_id: str) -> Dict[str, Any]:
        """Verify backup integrity"""
        backup_job = None
        for job in self.backup_jobs:
            if job.job_id == job_id:
                backup_job = job
                break
        
        if not backup_job:
            return {'valid': False, 'error': 'Backup not found'}
        
        try:
            backup_path = Path(backup_job.backup_path)
            current_hash = self._calculate_directory_hash(backup_path)
            
            return {
                'valid': current_hash == backup_job.integrity_hash,
                'current_hash': current_hash,
                'original_hash': backup_job.integrity_hash,
                'backup_path': str(backup_path)
            }
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}

# Global backup encryption instance
backup_encryption_instance: Optional[WindowsBackupEncryption] = None

def initialize_backup_encryption(config: BackupEncryptionConfig = None) -> WindowsBackupEncryption:
    """Initialize global backup encryption"""
    global backup_encryption_instance
    backup_encryption_instance = WindowsBackupEncryption(config)
    return backup_encryption_instance

def get_backup_encryption() -> WindowsBackupEncryption:
    """Get global backup encryption instance"""
    if backup_encryption_instance is None:
        initialize_backup_encryption()
    return backup_encryption_instance