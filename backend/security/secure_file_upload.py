import os
import io
import hashlib
import mimetypes
import tempfile
import subprocess
import logging
import shutil
import json
import uuid
from typing import Dict, List, Optional, Tuple, Any, BinaryIO
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import magic
import zipfile
import py7zr
import rarfile
from PIL import Image
import win32api
import win32security
import win32file
import win32con
import win32process
import pythoncom
import wmi

logger = logging.getLogger(__name__)

@dataclass
class FileUploadConfig:
    max_file_size_mb: int = 100
    allowed_extensions: List[str] = None
    forbidden_extensions: List[str] = None
    max_files_per_request: int = 10
    quarantine_suspicious: bool = True
    scan_with_defender: bool = True
    enable_efs_encryption: bool = True
    upload_dir: str = "uploads"
    quarantine_dir: str = "quarantine"
    temp_dir: str = "temp"

@dataclass
class FileUploadResult:
    success: bool
    file_id: str = None
    filename: str = None
    file_path: str = None
    file_size: int = 0
    content_type: str = None
    security_scan_result: Dict = None
    errors: List[str] = None
    warnings: List[str] = None
    encrypted: bool = False

class WindowsDefenderIntegration:
    """Integration with Windows Defender for file scanning"""
    
    def __init__(self):
        self.wmi_connection = None
        self.defender_available = self._check_defender_availability()
    
    def _check_defender_availability(self) -> bool:
        """Check if Windows Defender is available and running"""
        try:
            pythoncom.CoInitialize()
            self.wmi_connection = wmi.WMI(namespace="root\\Microsoft\\Windows\\Defender")
            
            # Check if Windows Defender service is running
            result = subprocess.run([
                'powershell', '-Command',
                'Get-Service -Name "WinDefend" | Select-Object Status'
            ], capture_output=True, text=True, shell=True)
            
            return "Running" in result.stdout
            
        except Exception as e:
            logger.warning(f"Windows Defender availability check failed: {e}")
            return False
    
    def scan_file(self, file_path: str) -> Dict[str, Any]:
        """Scan file with Windows Defender"""
        if not self.defender_available:
            return {
                'scanned': False,
                'error': 'Windows Defender not available'
            }
        
        try:
            # Use Windows Defender command line scanner
            result = subprocess.run([
                'powershell', '-Command',
                f'Start-MpScan -ScanPath "{file_path}" -ScanType CustomScan'
            ], capture_output=True, text=True, shell=True, timeout=60)
            
            # Check scan results
            if result.returncode == 0:
                # Get threat detection results
                threat_result = subprocess.run([
                    'powershell', '-Command',
                    'Get-MpThreatDetection | Select-Object -Last 1 | ConvertTo-Json'
                ], capture_output=True, text=True, shell=True)
                
                threats = []
                if threat_result.stdout.strip():
                    try:
                        threat_data = json.loads(threat_result.stdout)
                        if threat_data:
                            threats.append(threat_data)
                    except json.JSONDecodeError:
                        pass
                
                return {
                    'scanned': True,
                    'clean': len(threats) == 0,
                    'threats': threats,
                    'scan_time': datetime.now().isoformat()
                }
            else:
                return {
                    'scanned': False,
                    'error': f'Scan failed: {result.stderr}'
                }
                
        except subprocess.TimeoutExpired:
            return {
                'scanned': False,
                'error': 'Scan timeout'
            }
        except Exception as e:
            return {
                'scanned': False,
                'error': f'Scan error: {str(e)}'
            }
    
    def get_defender_status(self) -> Dict[str, Any]:
        """Get Windows Defender status"""
        try:
            result = subprocess.run([
                'powershell', '-Command',
                'Get-MpComputerStatus | ConvertTo-Json'
            ], capture_output=True, text=True, shell=True)
            
            if result.returncode == 0 and result.stdout.strip():
                status_data = json.loads(result.stdout)
                return {
                    'available': True,
                    'real_time_protection': status_data.get('RealTimeProtectionEnabled', False),
                    'antivirus_enabled': status_data.get('AntivirusEnabled', False),
                    'definitions_updated': status_data.get('AntivirusSignatureLastUpdated', 'Unknown'),
                    'full_status': status_data
                }
            else:
                return {'available': False, 'error': 'Could not retrieve status'}
                
        except Exception as e:
            return {'available': False, 'error': str(e)}

class WindowsFileEncryption:
    """Windows EFS encryption for uploaded files"""
    
    def __init__(self):
        self.efs_available = self._check_efs_availability()
    
    def _check_efs_availability(self) -> bool:
        """Check if EFS is available on this system"""
        try:
            # Check if NTFS and EFS are supported
            result = subprocess.run([
                'fsutil', 'fsinfo', 'ntfsinfo', 'C:'
            ], capture_output=True, text=True, shell=True)
            
            return result.returncode == 0
            
        except Exception:
            return False
    
    def encrypt_file(self, file_path: str) -> bool:
        """Encrypt file using Windows EFS"""
        if not self.efs_available:
            logger.warning("EFS not available")
            return False
        
        try:
            # Use cipher command to encrypt
            result = subprocess.run([
                'cipher', '/e', file_path
            ], capture_output=True, text=True, shell=True)
            
            success = result.returncode == 0
            if success:
                logger.info(f"File encrypted: {file_path}")
            else:
                logger.error(f"Encryption failed: {result.stderr}")
            
            return success
            
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return False
    
    def decrypt_file(self, file_path: str) -> bool:
        """Decrypt file using Windows EFS"""
        if not self.efs_available:
            return False
        
        try:
            result = subprocess.run([
                'cipher', '/d', file_path
            ], capture_output=True, text=True, shell=True)
            
            return result.returncode == 0
            
        except Exception:
            return False
    
    def is_encrypted(self, file_path: str) -> bool:
        """Check if file is encrypted"""
        try:
            # Get file attributes
            attrs = win32file.GetFileAttributes(file_path)
            return bool(attrs & win32file.FILE_ATTRIBUTE_ENCRYPTED)
            
        except Exception:
            return False

class SecureFileUploadHandler:
    """Secure file upload handler with Windows-specific security features"""
    
    def __init__(self, config: FileUploadConfig = None):
        self.config = config or FileUploadConfig()
        self.defender = WindowsDefenderIntegration()
        self.encryption = WindowsFileEncryption()
        
        # Set default extensions if not provided
        if self.config.allowed_extensions is None:
            self.config.allowed_extensions = [
                '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                '.csv', '.json', '.xml', '.jpg', '.jpeg', '.png', '.gif', '.bmp',
                '.zip', '.rar', '.7z', '.mp3', '.mp4', '.avi', '.mov', '.md'
            ]
        
        if self.config.forbidden_extensions is None:
            self.config.forbidden_extensions = [
                '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js',
                '.jar', '.ps1', '.msi', '.dll', '.sys', '.drv', '.cpl', '.lnk',
                '.reg', '.inf', '.msp', '.mst', '.application', '.gadget',
                '.hta', '.cpl', '.msc', '.wsf', '.ws', '.vbe', '.jse'
            ]
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Initialize file type detector
        try:
            self.file_magic = magic.Magic(mime=True)
        except Exception:
            self.file_magic = None
            logger.warning("python-magic not available, using basic MIME detection")
    
    def _ensure_directories(self):
        """Ensure upload directories exist with proper permissions"""
        directories = [
            self.config.upload_dir,
            self.config.quarantine_dir,
            self.config.temp_dir
        ]
        
        for directory in directories:
            dir_path = Path(directory)
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Set restrictive permissions on Windows
            try:
                # Get current user SID
                token = win32security.OpenProcessToken(
                    win32api.GetCurrentProcess(),
                    win32security.TOKEN_QUERY
                )
                user_sid = win32security.GetTokenInformation(
                    token, 
                    win32security.TokenUser
                )[0]
                
                # Create security descriptor allowing only current user
                sd = win32security.SECURITY_DESCRIPTOR()
                dacl = win32security.ACL()
                
                # Add ACE for current user (full control)
                dacl.AddAccessAllowedAce(
                    win32security.ACL_REVISION,
                    win32file.GENERIC_ALL,
                    user_sid
                )
                
                sd.SetSecurityDescriptorDacl(1, dacl, 0)
                
                # Apply security descriptor
                win32security.SetFileSecurity(
                    str(dir_path),
                    win32security.DACL_SECURITY_INFORMATION,
                    sd
                )
                
            except Exception as e:
                logger.warning(f"Could not set directory permissions: {e}")
    
    def validate_file_type(self, filename: str, content: bytes) -> Tuple[bool, List[str]]:
        """Validate file type based on extension and content"""
        errors = []
        
        # Check file extension
        file_ext = Path(filename).suffix.lower()
        
        if file_ext in self.config.forbidden_extensions:
            errors.append(f"Forbidden file extension: {file_ext}")
            return False, errors
        
        if file_ext not in self.config.allowed_extensions:
            errors.append(f"File extension not in allowed list: {file_ext}")
            return False, errors
        
        # Validate MIME type
        detected_mime = None
        if self.file_magic:
            try:
                detected_mime = self.file_magic.from_buffer(content)
            except Exception:
                pass
        
        if not detected_mime:
            detected_mime, _ = mimetypes.guess_type(filename)
        
        # Check if MIME type matches extension
        expected_mimes = {
            '.txt': ['text/plain'],
            '.pdf': ['application/pdf'],
            '.jpg': ['image/jpeg'],
            '.jpeg': ['image/jpeg'],
            '.png': ['image/png'],
            '.gif': ['image/gif'],
            '.zip': ['application/zip'],
            '.json': ['application/json', 'text/plain'],
            '.xml': ['application/xml', 'text/xml'],
            '.csv': ['text/csv', 'text/plain']
        }
        
        if file_ext in expected_mimes and detected_mime:
            if detected_mime not in expected_mimes[file_ext]:
                errors.append(f"MIME type {detected_mime} doesn't match extension {file_ext}")
        
        return len(errors) == 0, errors
    
    def scan_archive_contents(self, file_path: str, file_ext: str) -> Tuple[bool, List[str]]:
        """Scan contents of archive files"""
        errors = []
        
        try:
            if file_ext == '.zip':
                with zipfile.ZipFile(file_path, 'r') as zip_file:
                    for file_info in zip_file.filelist:
                        inner_ext = Path(file_info.filename).suffix.lower()
                        if inner_ext in self.config.forbidden_extensions:
                            errors.append(f"Archive contains forbidden file: {file_info.filename}")
                        
                        # Check for zip bombs
                        if file_info.file_size > 100 * 1024 * 1024:  # 100MB
                            errors.append("Archive contains suspiciously large file")
                        
                        if file_info.compress_size > 0:
                            ratio = file_info.file_size / file_info.compress_size
                            if ratio > 100:  # Compression ratio > 100:1
                                errors.append("Suspicious compression ratio detected")
            
            elif file_ext == '.7z':
                with py7zr.SevenZipFile(file_path, 'r') as seven_file:
                    for file_info in seven_file.list():
                        inner_ext = Path(file_info.filename).suffix.lower()
                        if inner_ext in self.config.forbidden_extensions:
                            errors.append(f"Archive contains forbidden file: {file_info.filename}")
            
            elif file_ext == '.rar':
                with rarfile.RarFile(file_path, 'r') as rar_file:
                    for file_info in rar_file.infolist():
                        inner_ext = Path(file_info.filename).suffix.lower()
                        if inner_ext in self.config.forbidden_extensions:
                            errors.append(f"Archive contains forbidden file: {file_info.filename}")
        
        except Exception as e:
            errors.append(f"Error scanning archive: {str(e)}")
        
        return len(errors) == 0, errors
    
    def scan_image_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """Scan image file for embedded threats"""
        errors = []
        
        try:
            with Image.open(file_path) as img:
                # Check image properties
                if img.size[0] * img.size[1] > 100000000:  # Very large image
                    errors.append("Image resolution too high")
                
                # Check for EXIF data that might contain malicious content
                if hasattr(img, '_getexif') and img._getexif():
                    exif_data = img._getexif()
                    for tag_id, value in exif_data.items():
                        if isinstance(value, str) and len(value) > 1000:
                            errors.append("Suspicious EXIF data detected")
                            break
        
        except Exception as e:
            errors.append(f"Error scanning image: {str(e)}")
        
        return len(errors) == 0, errors
    
    def upload_file(self, file_content: BinaryIO, filename: str, user_id: str = None) -> FileUploadResult:
        """Upload and process file securely"""
        errors = []
        warnings = []
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        
        # Read file content
        content = file_content.read()
        file_size = len(content)
        
        # Basic validation
        if file_size == 0:
            errors.append("File is empty")
        
        if file_size > self.config.max_file_size_mb * 1024 * 1024:
            errors.append(f"File too large (max {self.config.max_file_size_mb}MB)")
        
        if not filename or len(filename) > 255:
            errors.append("Invalid filename")
        
        # Sanitize filename
        safe_filename = self._sanitize_filename(filename)
        file_ext = Path(safe_filename).suffix.lower()
        
        # Validate file type
        type_valid, type_errors = self.validate_file_type(safe_filename, content)
        errors.extend(type_errors)
        
        if errors:
            return FileUploadResult(
                success=False,
                errors=errors,
                warnings=warnings
            )
        
        # Create temporary file for scanning
        temp_file_path = None
        final_file_path = None
        
        try:
            # Write to temporary file
            with tempfile.NamedTemporaryFile(
                dir=self.config.temp_dir,
                suffix=file_ext,
                delete=False
            ) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # Additional file type specific scanning
            if file_ext in ['.zip', '.rar', '.7z']:
                archive_valid, archive_errors = self.scan_archive_contents(temp_file_path, file_ext)
                if not archive_valid:
                    errors.extend(archive_errors)
            
            elif file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                image_valid, image_errors = self.scan_image_file(temp_file_path)
                if not image_valid:
                    warnings.extend(image_errors)
            
            # Scan with Windows Defender
            scan_result = None
            if self.config.scan_with_defender:
                scan_result = self.defender.scan_file(temp_file_path)
                
                if scan_result.get('scanned', False) and not scan_result.get('clean', True):
                    if self.config.quarantine_suspicious:
                        # Move to quarantine
                        quarantine_path = Path(self.config.quarantine_dir) / f"{file_id}_{safe_filename}"
                        shutil.move(temp_file_path, quarantine_path)
                        
                        return FileUploadResult(
                            success=False,
                            file_id=file_id,
                            filename=safe_filename,
                            file_path=str(quarantine_path),
                            file_size=file_size,
                            security_scan_result=scan_result,
                            errors=["File quarantined due to security threats"],
                            warnings=warnings
                        )
                    else:
                        errors.append("File contains security threats")
            
            if errors:
                return FileUploadResult(
                    success=False,
                    errors=errors,
                    warnings=warnings,
                    security_scan_result=scan_result
                )
            
            # Move to final location
            final_filename = f"{file_id}_{safe_filename}"
            final_file_path = Path(self.config.upload_dir) / final_filename
            shutil.move(temp_file_path, final_file_path)
            
            # Encrypt file if enabled
            encrypted = False
            if self.config.enable_efs_encryption:
                encrypted = self.encryption.encrypt_file(str(final_file_path))
                if not encrypted:
                    warnings.append("File encryption failed")
            
            # Determine content type
            content_type = None
            if self.file_magic:
                try:
                    content_type = self.file_magic.from_file(str(final_file_path))
                except Exception:
                    pass
            
            if not content_type:
                content_type, _ = mimetypes.guess_type(safe_filename)
            
            return FileUploadResult(
                success=True,
                file_id=file_id,
                filename=safe_filename,
                file_path=str(final_file_path),
                file_size=file_size,
                content_type=content_type,
                security_scan_result=scan_result,
                errors=errors,
                warnings=warnings,
                encrypted=encrypted
            )
        
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return FileUploadResult(
                success=False,
                errors=[f"Upload failed: {str(e)}"],
                warnings=warnings
            )
        
        finally:
            # Cleanup temporary file if it still exists
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for Windows"""
        # Remove path separators
        filename = filename.replace('\\', '').replace('/', '')
        
        # Remove invalid characters for Windows
        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove control characters
        filename = ''.join(char for char in filename if ord(char) >= 32)
        
        # Handle reserved names
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
        name_part = Path(filename).stem
        
        if name_part.upper() in reserved_names:
            filename = f"file_{filename}"
        
        # Ensure filename isn't too long
        if len(filename) > 200:  # Leave room for file ID prefix
            name_part = Path(filename).stem[:150]
            ext_part = Path(filename).suffix
            filename = name_part + ext_part
        
        return filename
    
    def delete_file(self, file_id: str) -> bool:
        """Securely delete uploaded file"""
        try:
            # Find file with this ID
            for directory in [self.config.upload_dir, self.config.quarantine_dir]:
                dir_path = Path(directory)
                for file_path in dir_path.glob(f"{file_id}_*"):
                    # Decrypt if encrypted
                    if self.encryption.is_encrypted(str(file_path)):
                        self.encryption.decrypt_file(str(file_path))
                    
                    # Secure deletion (overwrite before delete)
                    self._secure_delete(file_path)
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"File deletion error: {e}")
            return False
    
    def _secure_delete(self, file_path: Path):
        """Securely delete file by overwriting"""
        try:
            file_size = file_path.stat().st_size
            
            # Overwrite file multiple times
            with open(file_path, 'r+b') as file:
                for _ in range(3):  # 3 passes
                    file.seek(0)
                    file.write(os.urandom(file_size))
                    file.flush()
                    os.fsync(file.fileno())
            
            # Delete file
            file_path.unlink()
            
        except Exception as e:
            logger.error(f"Secure deletion failed: {e}")
            # Fallback to normal deletion
            try:
                file_path.unlink()
            except Exception:
                pass
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get information about uploaded file"""
        try:
            for directory in [self.config.upload_dir, self.config.quarantine_dir]:
                dir_path = Path(directory)
                for file_path in dir_path.glob(f"{file_id}_*"):
                    stat = file_path.stat()
                    
                    return {
                        'file_id': file_id,
                        'filename': file_path.name[37:],  # Remove UUID prefix
                        'file_path': str(file_path),
                        'file_size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime),
                        'modified': datetime.fromtimestamp(stat.st_mtime),
                        'encrypted': self.encryption.is_encrypted(str(file_path)),
                        'quarantined': 'quarantine' in str(file_path)
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return None

# Global file upload handler
upload_handler: Optional[SecureFileUploadHandler] = None

def initialize_file_upload_handler(config: FileUploadConfig = None) -> SecureFileUploadHandler:
    """Initialize global file upload handler"""
    global upload_handler
    upload_handler = SecureFileUploadHandler(config)
    return upload_handler

def get_file_upload_handler() -> SecureFileUploadHandler:
    """Get global file upload handler"""
    if upload_handler is None:
        initialize_file_upload_handler()
    return upload_handler