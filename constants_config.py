"""
Configuration Constants for Production RAG System
Centralized configuration for all modules with security-focused defaults.
"""

from pathlib import Path
import os

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

DATABASE_SCHEMA_VERSION = 2
DATABASE_TIMEOUT_SECONDS = 30
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0

# ============================================================================
# FILE PROCESSING CONFIGURATION
# ============================================================================

# File size limits (in bytes)
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB default
MAX_CHUNK_SIZE = 2000  # Maximum words per chunk
DEFAULT_CHUNK_SIZE = 500  # Default words per chunk
DEFAULT_CHUNK_OVERLAP = 100  # Default word overlap between chunks

# Processing timeouts
PROCESSING_TIMEOUT_SECONDS = 300  # 5 minutes
FILE_OPERATION_TIMEOUT_SECONDS = 60  # 1 minute

# Supported file types and MIME types
FILE_EXTENSIONS = [
    '.txt', '.pdf', '.docx', '.doc', '.csv', 
    '.md', '.markdown', '.json', '.rtf'
]

SUPPORTED_MIME_TYPES = {
    'text/plain',
    'text/csv',
    'text/markdown',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/json',
    'application/rtf'
}

ALLOWED_FILE_EXTENSIONS = FILE_EXTENSIONS  # Alias for backward compatibility

# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# File permissions (Unix-style octal)
SECURE_FILE_PERMISSIONS = 0o644  # rw-r--r--
SECURE_DIR_PERMISSIONS = 0o750   # rwxr-x---
SECURE_TEMP_PERMISSIONS = 0o700  # rwx------

# Security features
MALWARE_SCAN_ENABLED = False  # Enable when malware scanner is configured
QUARANTINE_RETENTION_DAYS = 30
AUDIT_LOG_RETENTION_DAYS = 90
SECURE_DELETE_PASSES = 3

# Content validation
TAG_CONFIDENCE_THRESHOLD = 0.3
MAX_CONCURRENT_OPERATIONS = 4

# ============================================================================
# CHUNKING AND EMBEDDING CONFIGURATION
# ============================================================================

# Chunking strategies
CHUNKING_STRATEGIES = {
    'semantic': {
        'chunk_size': 500,
        'overlap': 100,
        'sentence_boundary': True
    },
    'fixed': {
        'chunk_size': 1000,
        'overlap': 200,
        'sentence_boundary': False
    },
    'adaptive': {
        'min_chunk_size': 200,
        'max_chunk_size': 800,
        'overlap': 150,
        'content_aware': True
    }
}

# Content analysis keywords for auto-tagging
CONTENT_KEYWORDS = {
    'financial': [
        'budget', 'cost', 'revenue', 'profit', 'financial', 'money', 
        'dollar', 'invoice', 'expense', 'income', 'accounting', 'fiscal',
        'investment', 'capital', 'balance', 'audit', 'tax'
    ],
    'technical': [
        'code', 'software', 'system', 'algorithm', 'database', 'api', 
        'technical', 'programming', 'development', 'architecture',
        'infrastructure', 'deployment', 'configuration', 'framework'
    ],
    'legal': [
        'contract', 'agreement', 'legal', 'terms', 'conditions', 
        'liability', 'regulation', 'compliance', 'policy', 'law',
        'statute', 'jurisdiction', 'litigation', 'settlement'
    ],
    'medical': [
        'patient', 'medical', 'diagnosis', 'treatment', 'healthcare', 
        'clinical', 'pharmaceutical', 'therapy', 'doctor', 'hospital',
        'medicine', 'symptoms', 'procedure', 'surgery'
    ],
    'research': [
        'research', 'study', 'analysis', 'methodology', 'results', 
        'hypothesis', 'experiment', 'data', 'findings', 'conclusion',
        'investigation', 'survey', 'statistics', 'correlation'
    ],
    'security': [
        'security', 'encryption', 'authentication', 'authorization',
        'vulnerability', 'threat', 'risk', 'breach', 'incident',
        'confidential', 'classified', 'restricted', 'access control'
    ],
    'hr': [
        'employee', 'staff', 'personnel', 'hiring', 'recruitment',
        'performance', 'review', 'salary', 'benefits', 'training',
        'development', 'policy', 'handbook', 'onboarding'
    ]
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_LEVELS = {
    'DEBUG': 10,
    'INFO': 20,
    'WARNING': 30,
    'ERROR': 40,
    'CRITICAL': 50
}

DEFAULT_LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Log rotation settings
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# ============================================================================
# PERFORMANCE CONFIGURATION
# ============================================================================

# Threading and concurrency
MAX_WORKER_THREADS = 4
MAX_PROCESSING_WORKERS = 2
THREAD_POOL_TIMEOUT = 30

# Caching
CACHE_SIZE_LIMIT = 1000  # Number of items
CACHE_TTL_SECONDS = 3600  # 1 hour

# Batch processing
BATCH_SIZE = 100
MAX_BATCH_WAIT_TIME = 5.0  # seconds

# ============================================================================
# STORAGE CONFIGURATION
# ============================================================================

# Directory structure
DEFAULT_DATA_DIR = Path("data")
DEFAULT_UPLOAD_DIR = DEFAULT_DATA_DIR / "uploads"
DEFAULT_TEMP_DIR = DEFAULT_DATA_DIR / "temp"
DEFAULT_LOG_DIR = DEFAULT_DATA_DIR / "logs"
DEFAULT_BACKUP_DIR = DEFAULT_DATA_DIR / "backup"
DEFAULT_QUARANTINE_DIR = DEFAULT_TEMP_DIR / "quarantine"

# Database settings
DEFAULT_DATABASE_PATH = DEFAULT_DATA_DIR / "database" / "rag_system.db"
DATABASE_POOL_SIZE = 5
DATABASE_POOL_TIMEOUT = 30

# ============================================================================
# MONITORING AND HEALTH CHECKS
# ============================================================================

# Health check intervals
HEALTH_CHECK_INTERVAL_SECONDS = 60
DISK_USAGE_WARNING_THRESHOLD = 80  # Percentage
DISK_USAGE_CRITICAL_THRESHOLD = 95  # Percentage

# Performance metrics
PERFORMANCE_WINDOW_SIZE = 1000  # Number of operations to track
SLOW_OPERATION_THRESHOLD = 10.0  # seconds

# ============================================================================
# ENVIRONMENT-SPECIFIC OVERRIDES
# ============================================================================

def get_env_config():
    """Get environment-specific configuration overrides."""
    env_config = {}
    
    # Environment detection
    environment = os.getenv('ENVIRONMENT', 'development').lower()
    
    if environment == 'production':
        env_config.update({
            'DEFAULT_LOG_LEVEL': 'WARNING',
            'MALWARE_SCAN_ENABLED': True,
            'SECURE_DELETE_PASSES': 5,
            'MAX_FILE_SIZE_BYTES': 50 * 1024 * 1024,  # 50MB in production
            'DATABASE_TIMEOUT_SECONDS': 60,
            'PROCESSING_TIMEOUT_SECONDS': 600,  # 10 minutes
            'MAX_RETRY_ATTEMPTS': 5
        })
    elif environment == 'development':
        env_config.update({
            'DEFAULT_LOG_LEVEL': 'DEBUG',
            'MALWARE_SCAN_ENABLED': False,
            'SECURE_DELETE_PASSES': 1,
            'MAX_FILE_SIZE_BYTES': 200 * 1024 * 1024,  # 200MB in dev
            'PROCESSING_TIMEOUT_SECONDS': 120
        })
    elif environment == 'testing':
        env_config.update({
            'DEFAULT_LOG_LEVEL': 'DEBUG',
            'MALWARE_SCAN_ENABLED': False,
            'SECURE_DELETE_PASSES': 1,
            'MAX_FILE_SIZE_BYTES': 10 * 1024 * 1024,  # 10MB in testing
            'PROCESSING_TIMEOUT_SECONDS': 30,
            'DATABASE_TIMEOUT_SECONDS': 10
        })
    
    # Override with environment variables
    env_overrides = {
        'MAX_FILE_SIZE_MB': ('MAX_FILE_SIZE_BYTES', lambda x: int(x) * 1024 * 1024),
        'CHUNK_SIZE': ('DEFAULT_CHUNK_SIZE', int),
        'CHUNK_OVERLAP': ('DEFAULT_CHUNK_OVERLAP', int),
        'LOG_LEVEL': ('DEFAULT_LOG_LEVEL', str),
        'MALWARE_SCAN': ('MALWARE_SCAN_ENABLED', lambda x: x.lower() in ['true', '1', 'yes']),
        'SECURE_DELETE_PASSES': ('SECURE_DELETE_PASSES', int),
        'MAX_WORKERS': ('MAX_WORKER_THREADS', int),
        'DATABASE_TIMEOUT': ('DATABASE_TIMEOUT_SECONDS', int),
        'PROCESSING_TIMEOUT': ('PROCESSING_TIMEOUT_SECONDS', int)
    }
    
    for env_var, (config_key, converter) in env_overrides.items():
        env_value = os.getenv(env_var)
        if env_value is not None:
            try:
                env_config[config_key] = converter(env_value)
            except (ValueError, TypeError) as e:
                print(f"Warning: Invalid environment variable {env_var}={env_value}: {e}")
    
    return env_config

# ============================================================================
# SECURITY CLASSIFICATIONS
# ============================================================================

SECURITY_CLASSIFICATIONS = [
    'unclassified',
    'restricted',
    'confidential',
    'secret',
    'top_secret'
]

CLASSIFICATION_COLORS = {
    'unclassified': '#28a745',  # Green
    'restricted': '#ffc107',    # Yellow
    'confidential': '#fd7e14',  # Orange
    'secret': '#dc3545',        # Red
    'top_secret': '#6f42c1'     # Purple
}

# ============================================================================
# ERROR CODES AND MESSAGES
# ============================================================================

ERROR_CODES = {
    'FILE_NOT_FOUND': 1001,
    'FILE_TOO_LARGE': 1002,
    'INVALID_FILE_TYPE': 1003,
    'SECURITY_VIOLATION': 1004,
    'PROCESSING_TIMEOUT': 1005,
    'STORAGE_FULL': 1006,
    'DATABASE_ERROR': 1007,
    'MALWARE_DETECTED': 1008,
    'PERMISSION_DENIED': 1009,
    'QUOTA_EXCEEDED': 1010
}

ERROR_MESSAGES = {
    ERROR_CODES['FILE_NOT_FOUND']: "The specified file was not found",
    ERROR_CODES['FILE_TOO_LARGE']: "File size exceeds maximum allowed limit",
    ERROR_CODES['INVALID_FILE_TYPE']: "File type is not supported",
    ERROR_CODES['SECURITY_VIOLATION']: "File failed security validation",
    ERROR_CODES['PROCESSING_TIMEOUT']: "File processing timed out",
    ERROR_CODES['STORAGE_FULL']: "Storage space is insufficient",
    ERROR_CODES['DATABASE_ERROR']: "Database operation failed",
    ERROR_CODES['MALWARE_DETECTED']: "Malware detected in file",
    ERROR_CODES['PERMISSION_DENIED']: "Insufficient permissions for operation",
    ERROR_CODES['QUOTA_EXCEEDED']: "User storage quota exceeded"
}

# ============================================================================
# FEATURE FLAGS
# ============================================================================

FEATURE_FLAGS = {
    'ENABLE_ADVANCED_CHUNKING': True,
    'ENABLE_AUTO_TAGGING': True,
    'ENABLE_CONTENT_ANALYSIS': True,
    'ENABLE_DUPLICATE_DETECTION': True,
    'ENABLE_FILE_VERSIONING': False,
    'ENABLE_COMPRESSION': False,
    'ENABLE_ENCRYPTION_AT_REST': False,
    'ENABLE_AUDIT_LOGGING': True,
    'ENABLE_PERFORMANCE_MONITORING': True,
    'ENABLE_HEALTH_CHECKS': True
}

# ============================================================================
# VALIDATION RULES
# ============================================================================

VALIDATION_RULES = {
    'filename': {
        'max_length': 255,
        'forbidden_chars': ['<', '>', ':', '"', '/', '\\', '|', '?', '*'],
        'forbidden_names': ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']
    },
    'content': {
        'min_chars': 10,
        'max_chars': 10_000_000,  # 10MB of text
        'forbidden_patterns': [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'vbscript:',
            r'data:text/html'
        ]
    },
    'metadata': {
        'max_key_length': 100,
        'max_value_length': 1000,
        'max_entries': 100
    }
}

# ============================================================================
# RATE LIMITING
# ============================================================================

RATE_LIMITS = {
    'file_upload': {
        'requests_per_minute': 60,
        'requests_per_hour': 1000,
        'bytes_per_minute': 100 * 1024 * 1024,  # 100MB
        'bytes_per_hour': 1024 * 1024 * 1024    # 1GB
    },
    'search': {
        'requests_per_minute': 300,
        'requests_per_hour': 5000
    },
    'metadata_extraction': {
        'requests_per_minute': 120,
        'requests_per_hour': 2000
    }
}

# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def validate_configuration():
    """Validate configuration values for consistency and security."""
    errors = []
    warnings = []
    
    # Validate chunk sizes
    if DEFAULT_CHUNK_OVERLAP >= DEFAULT_CHUNK_SIZE:
        errors.append("Chunk overlap cannot be greater than or equal to chunk size")
    
    if DEFAULT_CHUNK_SIZE > MAX_CHUNK_SIZE:
        errors.append("Default chunk size cannot exceed maximum chunk size")
    
    # Validate timeouts
    if PROCESSING_TIMEOUT_SECONDS < 30:
        warnings.append("Processing timeout is very low, may cause premature timeouts")
    
    if DATABASE_TIMEOUT_SECONDS < 5:
        warnings.append("Database timeout is very low, may cause connection issues")
    
    # Validate file size limits
    if MAX_FILE_SIZE_BYTES > 1024 * 1024 * 1024:  # 1GB
        warnings.append("Maximum file size is very large, may impact performance")
    
    # Validate security settings
    if not MALWARE_SCAN_ENABLED and os.getenv('ENVIRONMENT', '').lower() == 'production':
        warnings.append("Malware scanning is disabled in production environment")
    
    if SECURE_DELETE_PASSES < 1:
        errors.append("Secure delete passes must be at least 1")
    
    # Validate directory permissions
    if SECURE_DIR_PERMISSIONS & 0o077:  # World or group writable
        warnings.append("Directory permissions may be too permissive")
    
    if errors:
        raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
    
    if warnings:
        print(f"Configuration warnings: {'; '.join(warnings)}")
    
    return True

# ============================================================================
# EXPORT INTERFACE
# ============================================================================

def get_config():
    """Get complete configuration with environment overrides applied."""
    # Start with base configuration
    config = {
        name: value for name, value in globals().items()
        if not name.startswith('_') and name.isupper()
    }
    
    # Apply environment-specific overrides
    env_config = get_env_config()
    config.update(env_config)
    
    return type('Config', (), config)()

# Apply validation on import
validate_configuration()
