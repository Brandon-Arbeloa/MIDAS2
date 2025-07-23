import re
import html
import unicodedata
import json
import logging
from typing import Dict, List, Optional, Any, Union, Callable
from dataclasses import dataclass
from enum import Enum
import bleach
from urllib.parse import urlparse, parse_qs
import base64
import binascii
from datetime import datetime
import sqlparse
import win32api
import win32security

logger = logging.getLogger(__name__)

class ValidationLevel(Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    PERMISSIVE = "permissive"

@dataclass
class ValidationRule:
    name: str
    pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_chars: Optional[str] = None
    forbidden_patterns: Optional[List[str]] = None
    custom_validator: Optional[Callable] = None
    sanitizer: Optional[Callable] = None
    error_message: str = "Invalid input"

@dataclass 
class ValidationResult:
    is_valid: bool
    sanitized_value: Any = None
    errors: List[str] = None
    warnings: List[str] = None
    security_level: str = "unknown"

class WindowsInputValidator:
    """Comprehensive input validation and sanitization for Windows deployment"""
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.STRICT):
        self.validation_level = validation_level
        self.setup_rules()
        self.setup_security_patterns()
        
        # Windows security context
        self.windows_security = self._initialize_windows_security()
    
    def _initialize_windows_security(self):
        """Initialize Windows security context"""
        try:
            # Get current user security context
            token = win32security.OpenProcessToken(
                win32api.GetCurrentProcess(),
                win32security.TOKEN_QUERY
            )
            user_sid = win32security.GetTokenInformation(
                token,
                win32security.TokenUser
            )[0]
            
            return {
                'user_sid': win32security.ConvertSidToStringSid(user_sid),
                'token_handle': token
            }
        except Exception as e:
            logger.warning(f"Windows security context initialization failed: {e}")
            return None
    
    def setup_rules(self):
        """Setup validation rules based on security level"""
        if self.validation_level == ValidationLevel.STRICT:
            self.rules = self._get_strict_rules()
        elif self.validation_level == ValidationLevel.MODERATE:
            self.rules = self._get_moderate_rules()
        else:
            self.rules = self._get_permissive_rules()
    
    def setup_security_patterns(self):
        """Setup security-related patterns"""
        # SQL Injection patterns
        self.sql_injection_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
            r"(\b(OR|AND)\s+['\"].*['\"])",
            r"(--|#|/\*|\*/)",
            r"(\b(SCRIPT|JAVASCRIPT|VBSCRIPT|ONLOAD|ONERROR)\b)",
            r"(xp_|sp_|fn_)"
        ]
        
        # XSS patterns
        self.xss_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"onload\s*=",
            r"onerror\s*=",
            r"onclick\s*=",
            r"onmouseover\s*=",
            r"onfocus\s*=",
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>",
            r"<link[^>]*>",
            r"<meta[^>]*>",
            r"eval\s*\(",
            r"setTimeout\s*\(",
            r"setInterval\s*\("
        ]
        
        # Path traversal patterns
        self.path_traversal_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"%2e%2e%2f",
            r"%2e%2e%5c",
            r"\.\.%2f",
            r"\.\.%5c"
        ]
        
        # Command injection patterns
        self.command_injection_patterns = [
            r"[;&|`$\(\)]",
            r"\b(cmd|powershell|bash|sh|exec|system|eval)\b",
            r">\s*&",
            r"\|\s*nc\b",
            r"\|\s*netcat\b",
            r"\b(wget|curl|ping|nslookup|dig)\b"
        ]
        
        # Windows-specific dangerous patterns
        self.windows_dangerous_patterns = [
            r"\b(rundll32|regsvr32|mshta|cscript|wscript)\b",
            r"\\\\[^\\]+\\",  # UNC paths
            r"\$env:",  # PowerShell environment variables
            r"Get-Process|Stop-Process|Invoke-Expression",
            r"New-Object\s+System\.Net",
            r"DownloadString|DownloadFile",
            r"[A-Z]:\\\\",  # Absolute Windows paths
            r"HKEY_|HKLM|HKCU"  # Registry keys
        ]
    
    def _get_strict_rules(self) -> Dict[str, ValidationRule]:
        """Get strict validation rules"""
        return {
            'username': ValidationRule(
                name='username',
                pattern=r'^[a-zA-Z0-9_-]{3,50}$',
                min_length=3,
                max_length=50,
                forbidden_patterns=['admin', 'root', 'system'],
                error_message="Username must be 3-50 characters, alphanumeric plus underscore and dash only"
            ),
            'email': ValidationRule(
                name='email',
                pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
                max_length=254,
                error_message="Invalid email format"
            ),
            'password': ValidationRule(
                name='password',
                min_length=12,
                max_length=128,
                custom_validator=self._validate_strong_password,
                error_message="Password must be 12-128 characters with uppercase, lowercase, numbers, and symbols"
            ),
            'filename': ValidationRule(
                name='filename',
                pattern=r'^[a-zA-Z0-9._-]+$',
                max_length=255,
                forbidden_patterns=[r'\.exe$', r'\.bat$', r'\.cmd$', r'\.ps1$', r'\.scr$'],
                error_message="Invalid filename"
            ),
            'query': ValidationRule(
                name='query',
                max_length=1000,
                custom_validator=self._validate_search_query,
                sanitizer=self._sanitize_query,
                error_message="Invalid search query"
            ),
            'sql_query': ValidationRule(
                name='sql_query',
                max_length=2000,
                custom_validator=self._validate_sql_query,
                sanitizer=self._sanitize_sql,
                error_message="Invalid or dangerous SQL query"
            ),
            'url': ValidationRule(
                name='url',
                max_length=2048,
                custom_validator=self._validate_url,
                sanitizer=self._sanitize_url,
                error_message="Invalid URL"
            ),
            'json': ValidationRule(
                name='json',
                max_length=10000,
                custom_validator=self._validate_json,
                sanitizer=self._sanitize_json,
                error_message="Invalid JSON"
            ),
            'windows_path': ValidationRule(
                name='windows_path',
                pattern=r'^[a-zA-Z]:\\[^<>:"|?*]+$',
                max_length=260,  # Windows MAX_PATH
                custom_validator=self._validate_windows_path,
                error_message="Invalid Windows path"
            )
        }
    
    def _get_moderate_rules(self) -> Dict[str, ValidationRule]:
        """Get moderate validation rules"""
        rules = self._get_strict_rules()
        
        # Relax some rules for moderate level
        rules['username'].pattern = r'^[a-zA-Z0-9._-]{2,100}$'
        rules['filename'].forbidden_patterns = [r'\.exe$', r'\.bat$', r'\.cmd$']
        rules['query'].max_length = 2000
        
        return rules
    
    def _get_permissive_rules(self) -> Dict[str, ValidationRule]:
        """Get permissive validation rules"""
        rules = self._get_moderate_rules()
        
        # Further relax for permissive level
        rules['username'].pattern = r'^[a-zA-Z0-9._@-]{1,200}$'
        rules['filename'].forbidden_patterns = [r'\.exe$']
        rules['query'].max_length = 5000
        
        return rules
    
    def validate(self, field_name: str, value: Any, custom_rule: ValidationRule = None) -> ValidationResult:
        """Validate input field"""
        rule = custom_rule or self.rules.get(field_name)
        if not rule:
            return ValidationResult(
                is_valid=True,
                sanitized_value=value,
                warnings=["No validation rule found for field"]
            )
        
        errors = []
        warnings = []
        sanitized_value = value
        
        # Convert to string if not already
        if not isinstance(value, str):
            if value is None:
                value = ""
            else:
                value = str(value)
                warnings.append("Value converted to string")
        
        # Length validation
        if rule.min_length and len(value) < rule.min_length:
            errors.append(f"Value too short (minimum {rule.min_length} characters)")
        
        if rule.max_length and len(value) > rule.max_length:
            errors.append(f"Value too long (maximum {rule.max_length} characters)")
            # Truncate if too long
            if self.validation_level != ValidationLevel.STRICT:
                value = value[:rule.max_length]
                warnings.append("Value truncated to maximum length")
        
        # Pattern validation
        if rule.pattern and not re.match(rule.pattern, value, re.IGNORECASE):
            errors.append(f"Value doesn't match required pattern")
        
        # Forbidden patterns
        if rule.forbidden_patterns:
            for pattern in rule.forbidden_patterns:
                if re.search(pattern, value, re.IGNORECASE):
                    errors.append(f"Value contains forbidden pattern")
                    break
        
        # Security checks
        security_level = self._check_security_threats(value)
        if security_level == "high":
            errors.append("Input contains potentially dangerous content")
        elif security_level == "medium":
            warnings.append("Input contains suspicious patterns")
        
        # Custom validation
        if rule.custom_validator:
            try:
                custom_result = rule.custom_validator(value)
                if not custom_result:
                    errors.append("Custom validation failed")
            except Exception as e:
                errors.append(f"Custom validation error: {str(e)}")
        
        # Sanitization
        if rule.sanitizer:
            try:
                sanitized_value = rule.sanitizer(value)
            except Exception as e:
                warnings.append(f"Sanitization failed: {str(e)}")
                sanitized_value = self._basic_sanitize(value)
        else:
            sanitized_value = self._basic_sanitize(value)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=sanitized_value,
            errors=errors,
            warnings=warnings,
            security_level=security_level
        )
    
    def validate_batch(self, data: Dict[str, Any], rules: Dict[str, ValidationRule] = None) -> Dict[str, ValidationResult]:
        """Validate multiple fields at once"""
        results = {}
        validation_rules = rules or self.rules
        
        for field_name, value in data.items():
            if field_name in validation_rules:
                results[field_name] = self.validate(field_name, value, validation_rules[field_name])
            else:
                results[field_name] = self.validate(field_name, value)
        
        return results
    
    def _check_security_threats(self, value: str) -> str:
        """Check for security threats in input"""
        if not isinstance(value, str):
            return "low"
        
        threat_score = 0
        
        # Check SQL injection
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                threat_score += 3
                logger.warning(f"SQL injection pattern detected: {pattern}")
        
        # Check XSS
        for pattern in self.xss_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                threat_score += 3
                logger.warning(f"XSS pattern detected: {pattern}")
        
        # Check path traversal
        for pattern in self.path_traversal_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                threat_score += 2
                logger.warning(f"Path traversal pattern detected: {pattern}")
        
        # Check command injection
        for pattern in self.command_injection_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                threat_score += 3
                logger.warning(f"Command injection pattern detected: {pattern}")
        
        # Check Windows-specific threats
        for pattern in self.windows_dangerous_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                threat_score += 2
                logger.warning(f"Windows threat pattern detected: {pattern}")
        
        # Determine threat level
        if threat_score >= 5:
            return "high"
        elif threat_score >= 2:
            return "medium"
        else:
            return "low"
    
    def _basic_sanitize(self, value: str) -> str:
        """Basic sanitization"""
        if not isinstance(value, str):
            value = str(value)
        
        # HTML escape
        value = html.escape(value)
        
        # Remove control characters
        value = ''.join(char for char in value if unicodedata.category(char)[0] != 'C' or char in '\t\n\r')
        
        # Normalize unicode
        value = unicodedata.normalize('NFKC', value)
        
        return value.strip()
    
    def _validate_strong_password(self, password: str) -> bool:
        """Validate strong password requirements"""
        if len(password) < 12:
            return False
        
        checks = [
            r'[a-z]',  # lowercase
            r'[A-Z]',  # uppercase
            r'[0-9]',  # numbers
            r'[!@#$%^&*(),.?":{}|<>]',  # symbols
        ]
        
        return all(re.search(check, password) for check in checks)
    
    def _validate_search_query(self, query: str) -> bool:
        """Validate search query"""
        # Check for SQL injection attempts
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return False
        
        # Check for XSS attempts
        for pattern in self.xss_patterns[:5]:  # Check basic XSS patterns
            if re.search(pattern, query, re.IGNORECASE):
                return False
        
        return True
    
    def _validate_sql_query(self, query: str) -> bool:
        """Validate SQL query"""
        try:
            # Parse SQL to check validity
            parsed = sqlparse.parse(query)
            if not parsed:
                return False
            
            # Check for dangerous operations
            dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'EXEC', 'xp_', 'sp_']
            query_upper = query.upper()
            
            for keyword in dangerous_keywords:
                if keyword in query_upper:
                    logger.warning(f"Dangerous SQL keyword detected: {keyword}")
                    return False
            
            return True
            
        except Exception:
            return False
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL"""
        try:
            parsed = urlparse(url)
            
            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Only allow http/https
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Check for suspicious patterns
            suspicious_patterns = ['javascript:', 'data:', 'file:', 'ftp:']
            if any(pattern in url.lower() for pattern in suspicious_patterns):
                return False
            
            return True
            
        except Exception:
            return False
    
    def _validate_json(self, json_str: str) -> bool:
        """Validate JSON"""
        try:
            data = json.loads(json_str)
            
            # Check for suspicious content in JSON
            json_content = json.dumps(data).lower()
            
            for pattern in self.xss_patterns[:3]:  # Basic XSS check
                if re.search(pattern, json_content):
                    return False
            
            return True
            
        except (json.JSONDecodeError, TypeError):
            return False
    
    def _validate_windows_path(self, path: str) -> bool:
        """Validate Windows file path"""
        # Check for path traversal
        for pattern in self.path_traversal_patterns:
            if re.search(pattern, path):
                return False
        
        # Check for invalid Windows path characters
        invalid_chars = '<>:"|?*'
        if any(char in path for char in invalid_chars):
            return False
        
        # Check for reserved names
        reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
        path_parts = path.split('\\')
        
        for part in path_parts:
            if part.upper() in reserved_names:
                return False
        
        return True
    
    def _sanitize_query(self, query: str) -> str:
        """Sanitize search query"""
        # Remove dangerous characters
        dangerous_chars = ['<', '>', '"', "'", ';', '--', '/*', '*/']
        sanitized = query
        
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, '')
        
        return self._basic_sanitize(sanitized)
    
    def _sanitize_sql(self, sql: str) -> str:
        """Sanitize SQL query"""
        # This is a basic sanitization - in production, use parameterized queries
        return sqlparse.format(sql, strip_comments=True, keyword_case='upper')
    
    def _sanitize_url(self, url: str) -> str:
        """Sanitize URL"""
        parsed = urlparse(url)
        
        # Rebuild URL with only safe components
        safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Add query parameters if they exist and are safe
        if parsed.query:
            query_params = parse_qs(parsed.query)
            safe_params = {}
            
            for key, values in query_params.items():
                safe_key = self._basic_sanitize(key)
                safe_values = [self._basic_sanitize(v) for v in values]
                safe_params[safe_key] = safe_values
            
            if safe_params:
                from urllib.parse import urlencode
                safe_url += '?' + urlencode(safe_params, doseq=True)
        
        return safe_url
    
    def _sanitize_json(self, json_str: str) -> str:
        """Sanitize JSON"""
        try:
            data = json.loads(json_str)
            # Re-serialize to ensure clean JSON
            return json.dumps(data, ensure_ascii=True, separators=(',', ':'))
        except:
            return "{}"

class WindowsFileValidator:
    """Windows-specific file validation"""
    
    def __init__(self):
        self.dangerous_extensions = [
            '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js',
            '.jar', '.ps1', '.msi', '.dll', '.sys', '.drv', '.cpl'
        ]
        
        self.allowed_extensions = [
            '.txt', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.csv', '.json', '.xml', '.jpg', '.jpeg', '.png', '.gif', '.bmp',
            '.zip', '.rar', '.7z', '.mp3', '.mp4', '.avi', '.mov'
        ]
    
    def validate_file_upload(self, filename: str, content: bytes, max_size_mb: int = 10) -> ValidationResult:
        """Validate file upload"""
        errors = []
        warnings = []
        
        # Check filename
        if not filename or len(filename) > 255:
            errors.append("Invalid filename length")
        
        # Check extension
        file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
        
        if file_ext in self.dangerous_extensions:
            errors.append(f"Dangerous file type: {file_ext}")
        
        if file_ext not in self.allowed_extensions:
            warnings.append(f"Unusual file type: {file_ext}")
        
        # Check file size
        if len(content) > max_size_mb * 1024 * 1024:
            errors.append(f"File too large (max {max_size_mb}MB)")
        
        if len(content) == 0:
            errors.append("Empty file")
        
        # Check file signature (magic numbers)
        file_signature_valid = self._validate_file_signature(content, file_ext)
        if not file_signature_valid:
            warnings.append("File signature doesn't match extension")
        
        # Windows Defender integration would go here
        # defender_scan_result = self._scan_with_defender(content)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            sanitized_value=filename,
            errors=errors,
            warnings=warnings,
            security_level="medium" if warnings else "low"
        )
    
    def _validate_file_signature(self, content: bytes, expected_ext: str) -> bool:
        """Validate file signature matches extension"""
        if len(content) < 4:
            return False
        
        signatures = {
            '.pdf': [b'%PDF'],
            '.jpg': [b'\xFF\xD8\xFF'],
            '.jpeg': [b'\xFF\xD8\xFF'],
            '.png': [b'\x89PNG'],
            '.gif': [b'GIF8'],
            '.zip': [b'PK\x03\x04'],
            '.exe': [b'MZ'],
            '.doc': [b'\xD0\xCF\x11\xE0'],
            '.docx': [b'PK\x03\x04']
        }
        
        expected_signatures = signatures.get(expected_ext, [])
        if not expected_signatures:
            return True  # Unknown extension, assume valid
        
        return any(content.startswith(sig) for sig in expected_signatures)

# Global validator instance
validator_instance: Optional[WindowsInputValidator] = None

def initialize_validator(validation_level: ValidationLevel = ValidationLevel.STRICT) -> WindowsInputValidator:
    """Initialize global validator"""
    global validator_instance
    validator_instance = WindowsInputValidator(validation_level)
    return validator_instance

def get_validator() -> WindowsInputValidator:
    """Get global validator instance"""
    if validator_instance is None:
        initialize_validator()
    return validator_instance