import os
import json
import logging
import threading
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import socket
import getpass
import win32api
import win32security
import win32evtlog
import win32evtlogutil
import win32con
import win32process
import win32file
import wmi
import psutil
from pathlib import Path

logger = logging.getLogger(__name__)

class SecurityEventType(Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"  
    FILE_ACCESS = "file_access"
    DATA_ACCESS = "data_access"
    SYSTEM_CHANGE = "system_change"
    SECURITY_VIOLATION = "security_violation"
    NETWORK_ACCESS = "network_access"
    API_ACCESS = "api_access"
    ERROR = "error"
    WARNING = "warning"

class SecurityEventSeverity(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

@dataclass
class SecurityEvent:
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    message: str
    timestamp: datetime = None
    user_id: str = None
    username: str = None
    ip_address: str = None
    user_agent: str = None
    resource: str = None
    action: str = None
    details: Dict[str, Any] = None
    session_id: str = None
    request_id: str = None
    success: bool = None
    error_code: str = None
    additional_data: Dict[str, Any] = None

class WindowsEventLogHandler:
    """Handler for Windows Event Log integration"""
    
    def __init__(self, source_name: str = "MIDAS_Security"):
        self.source_name = source_name
        self.event_log_available = self._setup_event_source()
    
    def _setup_event_source(self) -> bool:
        """Setup Windows Event Log source"""
        try:
            # Register event source if it doesn't exist
            win32evtlogutil.AddSourceToRegistry(
                self.source_name,
                "Application",
                "C:\\Windows\\System32\\EventLog.dll"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Windows Event Log source: {e}")
            return False
    
    def log_event(self, event: SecurityEvent):
        """Log security event to Windows Event Log"""
        if not self.event_log_available:
            return
        
        try:
            # Determine Windows event type
            if event.severity in [SecurityEventSeverity.CRITICAL, SecurityEventSeverity.HIGH]:
                event_type = win32evtlog.EVENTLOG_ERROR_TYPE
            elif event.severity == SecurityEventSeverity.MEDIUM:
                event_type = win32evtlog.EVENTLOG_WARNING_TYPE
            else:
                event_type = win32evtlog.EVENTLOG_INFORMATION_TYPE
            
            # Create event message
            message_parts = [
                f"Event Type: {event.event_type.value}",
                f"Severity: {event.severity.name}",
                f"Message: {event.message}",
                f"User: {event.username or 'Unknown'}",
                f"IP: {event.ip_address or 'Unknown'}",
                f"Resource: {event.resource or 'N/A'}",
                f"Action: {event.action or 'N/A'}",
                f"Success: {event.success}",
                f"Timestamp: {event.timestamp.isoformat()}"
            ]
            
            if event.details:
                message_parts.append(f"Details: {json.dumps(event.details, default=str)}")
            
            full_message = "\n".join(message_parts)
            
            # Calculate event ID based on event type
            event_id_map = {
                SecurityEventType.AUTHENTICATION: 1001,
                SecurityEventType.AUTHORIZATION: 1002,
                SecurityEventType.FILE_ACCESS: 1003,
                SecurityEventType.DATA_ACCESS: 1004,
                SecurityEventType.SYSTEM_CHANGE: 1005,
                SecurityEventType.SECURITY_VIOLATION: 1006,
                SecurityEventType.NETWORK_ACCESS: 1007,
                SecurityEventType.API_ACCESS: 1008,
                SecurityEventType.ERROR: 1009,
                SecurityEventType.WARNING: 1010
            }
            
            event_id = event_id_map.get(event.event_type, 1000)
            
            # Log to Windows Event Log
            win32evtlogutil.ReportEvent(
                self.source_name,
                event_id,
                eventType=event_type,
                strings=[full_message]
            )
            
        except Exception as e:
            logger.error(f"Failed to log to Windows Event Log: {e}")

class FileAuditLogger:
    """File-based audit logger with rotation"""
    
    def __init__(self, log_dir: str = "logs", max_file_size_mb: int = 100, max_files: int = 30):
        self.log_dir = Path(log_dir)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.max_files = max_files
        
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up secure permissions
        self._secure_log_directory()
        
        # Current log file
        self.current_log_file = None
        self._create_new_log_file()
        
        # Lock for thread safety
        self._lock = threading.Lock()
    
    def _secure_log_directory(self):
        """Set secure permissions on log directory"""
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
            
            # Create security descriptor
            sd = win32security.SECURITY_DESCRIPTOR()
            dacl = win32security.ACL()
            
            # Add ACE for current user (full control)
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                win32file.GENERIC_ALL,
                user_sid
            )
            
            # Add ACE for SYSTEM (full control)
            system_sid = win32security.LookupAccountName(None, "SYSTEM")[0]
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                win32file.GENERIC_ALL,
                system_sid
            )
            
            # Add ACE for Administrators (full control)
            admin_sid = win32security.LookupAccountName(None, "Administrators")[0]
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                win32file.GENERIC_ALL,
                admin_sid
            )
            
            sd.SetSecurityDescriptorDacl(1, dacl, 0)
            
            # Apply security descriptor
            win32security.SetFileSecurity(
                str(self.log_dir),
                win32security.DACL_SECURITY_INFORMATION,
                sd
            )
            
        except Exception as e:
            logger.warning(f"Could not set secure permissions on log directory: {e}")
    
    def _create_new_log_file(self):
        """Create new log file with timestamp"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"security_audit_{timestamp}.jsonl"
        self.current_log_file = self.log_dir / filename
        
        # Create file and set permissions
        self.current_log_file.touch()
        self._secure_log_file(self.current_log_file)
    
    def _secure_log_file(self, file_path: Path):
        """Set secure permissions on log file"""
        try:
            # Similar to directory permissions but for file
            token = win32security.OpenProcessToken(
                win32api.GetCurrentProcess(),
                win32security.TOKEN_QUERY
            )
            user_sid = win32security.GetTokenInformation(
                token,
                win32security.TokenUser
            )[0]
            
            sd = win32security.SECURITY_DESCRIPTOR()
            dacl = win32security.ACL()
            
            # Current user - read/write
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                user_sid
            )
            
            # SYSTEM - full control
            system_sid = win32security.LookupAccountName(None, "SYSTEM")[0]
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                win32file.GENERIC_ALL,
                system_sid
            )
            
            sd.SetSecurityDescriptorDacl(1, dacl, 0)
            
            win32security.SetFileSecurity(
                str(file_path),
                win32security.DACL_SECURITY_INFORMATION,
                sd
            )
            
        except Exception as e:
            logger.warning(f"Could not secure log file: {e}")
    
    def _check_rotation(self):
        """Check if log file needs rotation"""
        if self.current_log_file and self.current_log_file.exists():
            if self.current_log_file.stat().st_size >= self.max_file_size:
                self._create_new_log_file()
                self._cleanup_old_files()
    
    def _cleanup_old_files(self):
        """Remove old log files beyond retention limit"""
        try:
            log_files = sorted(
                self.log_dir.glob("security_audit_*.jsonl"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            # Keep only the most recent files
            for old_file in log_files[self.max_files:]:
                old_file.unlink()
                
        except Exception as e:
            logger.error(f"Error cleaning up old log files: {e}")
    
    def log_event(self, event: SecurityEvent):
        """Log security event to file"""
        with self._lock:
            try:
                self._check_rotation()
                
                # Convert event to JSON
                event_dict = asdict(event)
                event_dict['timestamp'] = event.timestamp.isoformat()
                
                # Add system context
                event_dict['system_info'] = {
                    'hostname': socket.gethostname(),
                    'process_id': os.getpid(),
                    'thread_id': threading.get_ident()
                }
                
                # Write to log file
                with open(self.current_log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(event_dict, default=str) + '\n')
                
            except Exception as e:
                logger.error(f"Failed to log to file: {e}")

class DatabaseAuditLogger:
    """Database audit logger for structured storage"""
    
    def __init__(self, db_connection=None):
        self.db_connection = db_connection
        self.table_created = False
        
        if db_connection:
            self._ensure_audit_table()
    
    def _ensure_audit_table(self):
        """Ensure audit table exists"""
        if self.table_created:
            return
        
        try:
            # SQL to create audit table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS security_audit_log (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                severity INTEGER NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                user_id VARCHAR(100),
                username VARCHAR(100),
                ip_address INET,
                user_agent TEXT,
                resource VARCHAR(500),
                action VARCHAR(100),
                success BOOLEAN,
                error_code VARCHAR(50),
                session_id VARCHAR(100),
                request_id VARCHAR(100),
                details JSONB,
                additional_data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
            
            # Create index for performance
            create_index_sql = """
            CREATE INDEX IF NOT EXISTS idx_security_audit_timestamp ON security_audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_security_audit_user ON security_audit_log(username);
            CREATE INDEX IF NOT EXISTS idx_security_audit_type ON security_audit_log(event_type);
            CREATE INDEX IF NOT EXISTS idx_security_audit_severity ON security_audit_log(severity);
            """
            
            cursor = self.db_connection.cursor()
            cursor.execute(create_table_sql)
            cursor.execute(create_index_sql)
            self.db_connection.commit()
            
            self.table_created = True
            
        except Exception as e:
            logger.error(f"Failed to create audit table: {e}")
    
    def log_event(self, event: SecurityEvent):
        """Log security event to database"""
        if not self.db_connection or not self.table_created:
            return
        
        try:
            insert_sql = """
            INSERT INTO security_audit_log (
                event_type, severity, message, timestamp, user_id, username,
                ip_address, user_agent, resource, action, success, error_code,
                session_id, request_id, details, additional_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            cursor = self.db_connection.cursor()
            cursor.execute(insert_sql, (
                event.event_type.value,
                event.severity.value,
                event.message,
                event.timestamp,
                event.user_id,
                event.username,
                event.ip_address,
                event.user_agent,
                event.resource,
                event.action,
                event.success,
                event.error_code,
                event.session_id,
                event.request_id,
                json.dumps(event.details) if event.details else None,
                json.dumps(event.additional_data) if event.additional_data else None
            ))
            
            self.db_connection.commit()
            
        except Exception as e:
            logger.error(f"Failed to log to database: {e}")
            # Rollback transaction on error
            self.db_connection.rollback()

class WindowsAuditLogger:
    """Comprehensive Windows audit logging system"""
    
    def __init__(
        self,
        enable_event_log: bool = True,
        enable_file_log: bool = True,
        enable_database_log: bool = True,
        log_dir: str = "logs",
        db_connection = None
    ):
        self.handlers = []
        
        # Initialize handlers based on configuration
        if enable_event_log:
            self.handlers.append(WindowsEventLogHandler())
        
        if enable_file_log:
            self.handlers.append(FileAuditLogger(log_dir))
        
        if enable_database_log and db_connection:
            self.handlers.append(DatabaseAuditLogger(db_connection))
        
        # System information cache
        self._system_info = self._gather_system_info()
        
        # Session tracking
        self._current_sessions = {}
        self._session_lock = threading.Lock()
    
    def _gather_system_info(self) -> Dict[str, str]:
        """Gather system information for audit context"""
        try:
            return {
                'hostname': socket.gethostname(),
                'username': getpass.getuser(),
                'os_version': f"{os.name} {psutil.version_info}",
                'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
                'process_id': str(os.getpid()),
                'executable_path': os.sys.executable
            }
        except Exception:
            return {}
    
    def create_session(self, user_id: str, username: str, ip_address: str) -> str:
        """Create audit session and return session ID"""
        session_id = hashlib.sha256(f"{user_id}_{username}_{ip_address}_{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        with self._session_lock:
            self._current_sessions[session_id] = {
                'user_id': user_id,
                'username': username,
                'ip_address': ip_address,
                'created_at': datetime.now(),
                'last_activity': datetime.now()
            }
        
        # Log session creation
        self.log_authentication(
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            action="session_created",
            success=True,
            session_id=session_id
        )
        
        return session_id
    
    def end_session(self, session_id: str):
        """End audit session"""
        with self._session_lock:
            session_info = self._current_sessions.pop(session_id, None)
        
        if session_info:
            # Log session end
            self.log_authentication(
                user_id=session_info['user_id'],
                username=session_info['username'],
                ip_address=session_info['ip_address'],
                action="session_ended",
                success=True,
                session_id=session_id,
                details={'session_duration': str(datetime.now() - session_info['created_at'])}
            )
    
    def _create_event(
        self,
        event_type: SecurityEventType,
        severity: SecurityEventSeverity,
        message: str,
        **kwargs
    ) -> SecurityEvent:
        """Create security event with common fields"""
        return SecurityEvent(
            event_type=event_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(),
            **kwargs
        )
    
    def log_event(self, event: SecurityEvent):
        """Log security event to all configured handlers"""
        # Update session activity if session_id provided
        if event.session_id:
            with self._session_lock:
                if event.session_id in self._current_sessions:
                    self._current_sessions[event.session_id]['last_activity'] = datetime.now()
        
        # Send to all handlers
        for handler in self.handlers:
            try:
                handler.log_event(event)
            except Exception as e:
                logger.error(f"Handler failed to log event: {e}")
    
    # Specific logging methods for different event types
    
    def log_authentication(
        self,
        user_id: str,
        username: str,
        ip_address: str,
        action: str,
        success: bool,
        session_id: str = None,
        user_agent: str = None,
        details: Dict = None,
        error_code: str = None
    ):
        """Log authentication event"""
        severity = SecurityEventSeverity.HIGH if not success else SecurityEventSeverity.LOW
        message = f"Authentication {action} for user {username} from {ip_address}: {'SUCCESS' if success else 'FAILED'}"
        
        event = self._create_event(
            SecurityEventType.AUTHENTICATION,
            severity,
            message,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            action=action,
            success=success,
            session_id=session_id,
            user_agent=user_agent,
            details=details,
            error_code=error_code
        )
        
        self.log_event(event)
    
    def log_authorization(
        self,
        user_id: str,
        username: str,
        resource: str,
        action: str,
        success: bool,
        ip_address: str = None,
        session_id: str = None,
        details: Dict = None
    ):
        """Log authorization event"""
        severity = SecurityEventSeverity.MEDIUM if not success else SecurityEventSeverity.LOW
        message = f"Authorization {action} on {resource} for user {username}: {'SUCCESS' if success else 'DENIED'}"
        
        event = self._create_event(
            SecurityEventType.AUTHORIZATION,
            severity,
            message,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource=resource,
            action=action,
            success=success,
            session_id=session_id,
            details=details
        )
        
        self.log_event(event)
    
    def log_file_access(
        self,
        user_id: str,
        username: str,
        file_path: str,
        action: str,
        success: bool,
        ip_address: str = None,
        session_id: str = None,
        details: Dict = None
    ):
        """Log file access event"""
        severity = SecurityEventSeverity.MEDIUM if action in ['delete', 'modify'] else SecurityEventSeverity.LOW
        message = f"File {action} on {file_path} by user {username}: {'SUCCESS' if success else 'FAILED'}"
        
        event = self._create_event(
            SecurityEventType.FILE_ACCESS,
            severity,
            message,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource=file_path,
            action=action,
            success=success,
            session_id=session_id,
            details=details
        )
        
        self.log_event(event)
    
    def log_data_access(
        self,
        user_id: str,
        username: str,
        data_type: str,
        action: str,
        success: bool,
        ip_address: str = None,
        session_id: str = None,
        request_id: str = None,
        details: Dict = None
    ):
        """Log data access event"""
        severity = SecurityEventSeverity.MEDIUM if action in ['delete', 'modify', 'export'] else SecurityEventSeverity.LOW
        message = f"Data {action} on {data_type} by user {username}: {'SUCCESS' if success else 'FAILED'}"
        
        event = self._create_event(
            SecurityEventType.DATA_ACCESS,
            severity,
            message,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource=data_type,
            action=action,
            success=success,
            session_id=session_id,
            request_id=request_id,
            details=details
        )
        
        self.log_event(event)
    
    def log_security_violation(
        self,
        violation_type: str,
        description: str,
        severity: SecurityEventSeverity,
        user_id: str = None,
        username: str = None,
        ip_address: str = None,
        resource: str = None,
        session_id: str = None,
        details: Dict = None
    ):
        """Log security violation"""
        message = f"Security violation: {violation_type} - {description}"
        
        event = self._create_event(
            SecurityEventType.SECURITY_VIOLATION,
            severity,
            message,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource=resource,
            session_id=session_id,
            details=details
        )
        
        self.log_event(event)
    
    def log_api_access(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        user_id: str = None,
        username: str = None,
        ip_address: str = None,
        user_agent: str = None,
        session_id: str = None,
        request_id: str = None,
        response_time_ms: float = None,
        details: Dict = None
    ):
        """Log API access"""
        success = 200 <= status_code < 400
        severity = SecurityEventSeverity.LOW
        
        if status_code >= 500:
            severity = SecurityEventSeverity.HIGH
        elif status_code >= 400:
            severity = SecurityEventSeverity.MEDIUM
        
        message = f"API {method} {endpoint} - Status: {status_code}"
        
        if response_time_ms:
            details = details or {}
            details['response_time_ms'] = response_time_ms
        
        event = self._create_event(
            SecurityEventType.API_ACCESS,
            severity,
            message,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            resource=endpoint,
            action=method,
            success=success,
            session_id=session_id,
            request_id=request_id,
            error_code=str(status_code) if not success else None,
            details=details
        )
        
        self.log_event(event)
    
    def get_audit_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get audit summary for the specified time period"""
        # This would typically query the database for statistics
        # For now, return basic info
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        return {
            'summary_period_hours': hours,
            'active_sessions': len(self._current_sessions),
            'system_info': self._system_info,
            'handlers_configured': len(self.handlers),
            'generated_at': datetime.now().isoformat()
        }

# Global audit logger instance
audit_logger: Optional[WindowsAuditLogger] = None

def initialize_audit_logger(
    enable_event_log: bool = True,
    enable_file_log: bool = True,
    enable_database_log: bool = True,
    log_dir: str = "logs",
    db_connection = None
) -> WindowsAuditLogger:
    """Initialize global audit logger"""
    global audit_logger
    audit_logger = WindowsAuditLogger(
        enable_event_log=enable_event_log,
        enable_file_log=enable_file_log,
        enable_database_log=enable_database_log,
        log_dir=log_dir,
        db_connection=db_connection
    )
    return audit_logger

def get_audit_logger() -> WindowsAuditLogger:
    """Get global audit logger instance"""
    if audit_logger is None:
        initialize_audit_logger()
    return audit_logger