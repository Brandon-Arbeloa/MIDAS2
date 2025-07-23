"""
Storage Manager Service - Production Grade
Handles document storage, indexing, and deduplication with enterprise-grade security and reliability.
"""

import sqlite3
import json
import logging
import time
import platform
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import shutil

# Configuration constants
WINDOWS = platform.system() == 'Windows'
DATABASE_SCHEMA_VERSION = "1.0.0"
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1
SUPPORTED_MIME_TYPES = [
    "text/plain", "text/csv", "text/markdown", 
    "application/pdf", "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]
FILE_EXTENSIONS = ['.txt', '.pdf', '.docx', '.csv', '.json', '.md']
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
TAG_CONFIDENCE_THRESHOLD = 0.7
DATABASE_TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)

@dataclass
class DocumentRecord:
    """Document record for database storage with comprehensive metadata."""
    id: Optional[int]
    filename: str
    original_filename: str
    file_path: str
    content_hash: str
    file_size: int
    mime_type: str
    upload_timestamp: str
    processing_timestamp: str
    metadata: Dict[str, Any]
    status: str = "processed"
    error_message: Optional[str] = None
    schema_version: int = DATABASE_SCHEMA_VERSION
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

@dataclass
class ChunkRecord:
    """Chunk record for database storage with enhanced metadata."""
    id: Optional[int]
    document_id: int
    chunk_index: int
    text: str
    word_count: int
    char_count: int
    chunk_metadata: Dict[str, Any]
    created_timestamp: str
    text_hash: Optional[str] = None
    processing_version: str = "1.0"

    def __post_init__(self):
        """Calculate text hash for deduplication."""
        if not self.text_hash and self.text:
            self.text_hash = hashlib.sha256(self.text.encode('utf-8')).hexdigest()

class DatabaseConnectionManager:
    """Thread-safe database connection manager with retry logic."""
    
    def __init__(self, db_path: Path, timeout: int = DATABASE_TIMEOUT_SECONDS):
        self.db_path = db_path
        self.timeout = timeout
        self._lock = threading.RLock()
    
    @contextmanager
    def get_connection(self, retries: int = MAX_RETRY_ATTEMPTS):
        """Get database connection with retry logic and proper cleanup."""
        connection = None
        attempt = 0
        
        while attempt < retries:
            try:
                with self._lock:
                    connection = sqlite3.connect(
                        self.db_path,
                        timeout=self.timeout,
                        isolation_level=None  # Autocommit mode
                    )
                    connection.execute("PRAGMA foreign_keys = ON")
                    connection.execute("PRAGMA journal_mode = WAL")
                    connection.execute("PRAGMA synchronous = FULL")
                    connection.execute("PRAGMA cache_size = -64000")  # 64MB cache
                    
                    yield connection
                    return
                    
            except sqlite3.OperationalError as e:
                attempt += 1
                if attempt >= retries:
                    logger.error(f"Database connection failed after {retries} attempts: {e}")
                    raise
                
                logger.warning(f"Database connection attempt {attempt} failed: {e}, retrying...")
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                
            except Exception as e:
                logger.error(f"Unexpected database error: {e}")
                raise
                
            finally:
                if connection:
                    try:
                        connection.close()
                    except Exception as e:
                        logger.warning(f"Error closing database connection: {e}")

class StorageManager:
    """
    Enterprise-grade storage manager with enhanced security, reliability, and performance.
    
    Features:
    - Thread-safe operations with connection pooling
    - Retry logic for all database operations
    - Comprehensive error handling and logging
    - File locking for atomic operations
    - Security-focused file handling
    - Configurable storage paths and settings
    """
    
    def __init__(self, config: Any):
        """
        Initialize storage manager with configuration.
        
        Args:
            config: Configuration object with database and storage settings
        """
        self.config = config
        self.db_path = self._get_database_path()
        self.storage_root = self._get_storage_root()
        
        # Ensure directories exist with proper permissions
        self._setup_directories()
        
        # Initialize database connection manager
        self.db_manager = DatabaseConnectionManager(self.db_path)
        
        # Initialize database schema
        self._init_database()
        
        # Thread pool for concurrent operations
        self.executor = ThreadPoolExecutor(
            max_workers=getattr(config, 'max_workers', 4),
            thread_name_prefix='storage-worker'
        )
        
        logger.info(f"Storage manager initialized - Database: {self.db_path}, Storage: {self.storage_root}")
    
    def _get_database_path(self) -> Path:
        """Get database path from configuration with security validation."""
        if hasattr(self.config, 'database') and hasattr(self.config.database, 'path'):
            db_path = Path(self.config.database.path)
        else:
            # Secure default in application data directory
            db_path = Path.cwd() / "data" / "database" / "rag_system.db"
        
        # Validate path is within allowed directories (security measure)
        resolved_path = db_path.resolve()
        if not self._is_path_allowed(resolved_path):
            raise ValueError(f"Database path not allowed: {resolved_path}")
        
        return resolved_path
    
    def _get_storage_root(self) -> Path:
        """Get storage root path from configuration with security validation."""
        if hasattr(self.config, 'storage') and hasattr(self.config.storage, 'root_path'):
            storage_path = Path(self.config.storage.root_path)
        else:
            storage_path = Path.cwd() / "data" / "storage"
        
        resolved_path = storage_path.resolve()
        if not self._is_path_allowed(resolved_path):
            raise ValueError(f"Storage path not allowed: {resolved_path}")
        
        return resolved_path
    
    def _is_path_allowed(self, path: Path) -> bool:
        """
        Validate that path is within allowed directories (security measure).
        
        Args:
            path: Path to validate
            
        Returns:
            bool: True if path is allowed
        """
        try:
            # Check if path is within application directory or explicitly allowed paths
            app_root = Path.cwd().resolve()
            allowed_roots = [app_root]
            
            # Add configured allowed paths
            if hasattr(self.config, 'security') and hasattr(self.config.security, 'allowed_paths'):
                allowed_roots.extend([Path(p).resolve() for p in self.config.security.allowed_paths])
            
            for allowed_root in allowed_roots:
                try:
                    path.relative_to(allowed_root)
                    return True
                except ValueError:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Error validating path {path}: {e}")
            return False
    
    def _setup_directories(self) -> None:
        """Setup required directories with proper permissions."""
        directories = [
            self.db_path.parent,
            self.storage_root,
            self.storage_root / "documents",
            self.storage_root / "temp",
            self.storage_root / "backup"
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True, mode=0o750)  # Secure permissions
                logger.debug(f"Directory ensured: {directory}")
            except Exception as e:
                logger.error(f"Failed to create directory {directory}: {e}")
                raise
    
    def _init_database(self) -> None:
        """Initialize database schema with comprehensive tables and indexes."""
        schema_sql = [
            # Documents table with enhanced security and metadata
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                content_hash TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                upload_timestamp TEXT NOT NULL,
                processing_timestamp TEXT NOT NULL,
                metadata TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                schema_version INTEGER NOT NULL DEFAULT {schema_version},
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checksum TEXT,
                security_classification TEXT DEFAULT 'unclassified',
                retention_policy TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed TIMESTAMP,
                
                CONSTRAINT chk_status CHECK (status IN ('pending', 'processing', 'processed', 'failed', 'archived')),
                CONSTRAINT chk_file_size CHECK (file_size >= 0),
                CONSTRAINT chk_security_classification CHECK (
                    security_classification IN ('unclassified', 'restricted', 'confidential', 'secret')
                )
            )
            """.format(schema_version=DATABASE_SCHEMA_VERSION),
            
            # Chunks table with deduplication support
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                char_count INTEGER NOT NULL,
                text_hash TEXT,
                chunk_metadata TEXT NOT NULL,
                created_timestamp TEXT NOT NULL,
                processing_version TEXT DEFAULT '1.0',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                embedding_model TEXT,
                embedding_dimensions INTEGER,
                
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                CONSTRAINT chk_word_count CHECK (word_count >= 0),
                CONSTRAINT chk_char_count CHECK (char_count >= 0),
                UNIQUE(document_id, chunk_index)
            )
            """,
            
            # Document tags with confidence scoring
            """
            CREATE TABLE IF NOT EXISTS document_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                tag_type TEXT DEFAULT 'auto',
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0),
                CONSTRAINT chk_tag_type CHECK (tag_type IN ('auto', 'manual', 'ml')),
                UNIQUE(document_id, tag, tag_type)
            )
            """,
            
            # Processing history for audit trail
            """
            CREATE TABLE IF NOT EXISTS processing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                processing_stage TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                error_message TEXT,
                processing_details TEXT,
                
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
            )
            """,
            
            # File integrity checks
            """
            CREATE TABLE IF NOT EXISTS file_integrity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                check_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_hash TEXT NOT NULL,
                integrity_status TEXT NOT NULL,
                error_details TEXT,
                
                FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                CONSTRAINT chk_integrity_status CHECK (
                    integrity_status IN ('valid', 'corrupted', 'missing', 'modified')
                )
            )
            """
        ]
        
        # Performance indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)",
            "CREATE INDEX IF NOT EXISTS idx_documents_mime ON documents(mime_type)",
            "CREATE INDEX IF NOT EXISTS idx_documents_timestamp ON documents(upload_timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_documents_classification ON documents(security_classification)",
            
            "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash)",
            "CREATE INDEX IF NOT EXISTS idx_chunks_text_search ON chunks(text)",
            
            "CREATE INDEX IF NOT EXISTS idx_tags_document_id ON document_tags(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_tags_tag ON document_tags(tag)",
            "CREATE INDEX IF NOT EXISTS idx_tags_confidence ON document_tags(confidence)",
            
            "CREATE INDEX IF NOT EXISTS idx_history_document_id ON processing_history(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_history_status ON processing_history(status)",
            
            "CREATE INDEX IF NOT EXISTS idx_integrity_document_id ON file_integrity(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_integrity_status ON file_integrity(integrity_status)"
        ]
        
        # Database triggers for audit trail
        triggers = [
            """
            CREATE TRIGGER IF NOT EXISTS update_documents_timestamp 
            AFTER UPDATE ON documents
            BEGIN
                UPDATE documents SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END
            """,
            
            """
            CREATE TRIGGER IF NOT EXISTS log_document_access
            AFTER UPDATE OF access_count ON documents
            BEGIN
                UPDATE documents SET last_accessed = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END
            """
        ]
        
        try:
            with self.db_manager.get_connection() as conn:
                # Create tables
                for sql in schema_sql:
                    conn.execute(sql)
                
                # Create indexes
                for index_sql in indexes:
                    conn.execute(index_sql)
                
                # Create triggers
                for trigger_sql in triggers:
                    conn.execute(trigger_sql)
                
                conn.execute("PRAGMA optimize")
                
            logger.info("Database schema initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
            raise
    
    @contextmanager
    def _file_lock(self, file_path: Path, mode: str = 'r'):
        """
        Context manager for file locking to ensure atomic operations.
        
        Args:
            file_path: Path to file to lock
            mode: File open mode
        """
        lock_file = None
        try:
            # Create lock file
            lock_path = file_path.with_suffix(file_path.suffix + '.lock')
            lock_file = open(lock_path, 'w')
            
            # Acquire exclusive lock
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            yield lock_file
            
        except BlockingIOError:
            raise RuntimeError(f"Could not acquire lock for {file_path}")
        except Exception as e:
            logger.error(f"Error in file locking for {file_path}: {e}")
            raise
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                    lock_path = file_path.with_suffix(file_path.suffix + '.lock')
                    if lock_path.exists():
                        lock_path.unlink()
                except Exception as e:
                    logger.warning(f"Error releasing file lock: {e}")
    
    def store_document_atomic(self, processing_result: Dict[str, Any]) -> Optional[int]:
        """
        Store document and chunks atomically with comprehensive error handling.
        
        Args:
            processing_result: Result from document processing
            
        Returns:
            Optional[int]: Document ID if successful, None if failed
        """
        if not processing_result.get("success"):
            logger.error("Cannot store failed processing result")
            return None
        
        metadata = processing_result["metadata"]
        chunks = processing_result["chunks"]
        
        # Validate required fields
        required_fields = ["filename", "content_hash", "file_size", "mime_type"]
        for field in required_fields:
            if field not in metadata:
                logger.error(f"Missing required metadata field: {field}")
                return None
        
        document_id = None
        temp_file_path = None
        
        try:
            with self.db_manager.get_connection() as conn:
                # Begin transaction
                conn.execute("BEGIN IMMEDIATE")
                
                try:
                    # Check for duplicates
                    existing_id = self._get_document_by_hash(conn, metadata["content_hash"])
                    if existing_id:
                        logger.info(f"Document with hash {metadata['content_hash']} already exists (ID: {existing_id})")
                        conn.execute("ROLLBACK")
                        return existing_id
                    
                    # Create document record
                    doc_record = DocumentRecord(
                        id=None,
                        filename=self._sanitize_filename(metadata["filename"]),
                        original_filename=metadata["filename"],
                        file_path=metadata.get("file_path", ""),
                        content_hash=metadata["content_hash"],
                        file_size=metadata["file_size"],
                        mime_type=metadata["mime_type"],
                        upload_timestamp=metadata.get("upload_timestamp", datetime.now().isoformat()),
                        processing_timestamp=datetime.now().isoformat(),
                        metadata=metadata,
                        status="processing"
                    )
                    
                    # Insert document
                    document_id = self._insert_document(conn, doc_record)
                    
                    # Log processing start
                    self._log_processing_stage(conn, document_id, "document_insertion", "completed")
                    
                    # Insert chunks with deduplication
                    chunk_ids = []
                    for chunk in chunks:
                        chunk_record = ChunkRecord(
                            id=None,
                            document_id=document_id,
                            chunk_index=chunk["chunk_index"],
                            text=chunk["text"],
                            word_count=chunk["word_count"],
                            char_count=chunk["char_count"],
                            chunk_metadata=chunk["metadata"],
                            created_timestamp=chunk["metadata"].get("chunk_created", datetime.now().isoformat())
                        )
                        
                        chunk_id = self._insert_chunk(conn, chunk_record)
                        chunk_ids.append(chunk_id)
                    
                    # Log chunk processing
                    self._log_processing_stage(conn, document_id, "chunk_creation", "completed", 
                                             f"Created {len(chunk_ids)} chunks")
                    
                    # Generate and insert tags
                    tags = self._generate_enhanced_tags(metadata, chunks)
                    for tag, confidence in tags.items():
                        if confidence >= TAG_CONFIDENCE_THRESHOLD:
                            self._insert_tag(conn, document_id, tag, confidence, "auto")
                    
                    # Update document status
                    conn.execute(
                        "UPDATE documents SET status = 'processed' WHERE id = ?",
                        (document_id,)
                    )
                    
                    # Log final processing stage
                    self._log_processing_stage(conn, document_id, "document_processing", "completed")
                    
                    # Commit transaction
                    conn.execute("COMMIT")
                    
                    logger.info(f"Document stored successfully - ID: {document_id}, Chunks: {len(chunk_ids)}")
                    return document_id
                    
                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(f"Transaction failed, rolled back: {e}")
                    
                    if document_id:
                        self._log_processing_stage(conn, document_id, "document_processing", "failed", str(e))
                    
                    raise
                    
        except Exception as e:
            logger.error(f"Error storing document: {e}")
            
            # Cleanup on failure
            if temp_file_path and Path(temp_file_path).exists():
                try:
                    Path(temp_file_path).unlink()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
            
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for secure storage.
        
        Args:
            filename: Original filename
            
        Returns:
            str: Sanitized filename
        """
        import re
        
        # Remove path separators and other dangerous characters
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
        
        # Limit length
        if len(sanitized) > 200:
            name_part = Path(sanitized).stem[:190]
            ext_part = Path(sanitized).suffix
            sanitized = f"{name_part}{ext_part}"
        
        # Ensure not empty
        if not sanitized.strip():
            sanitized = f"unknown_file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return sanitized
    
    def _get_document_by_hash(self, conn: sqlite3.Connection, content_hash: str) -> Optional[int]:
        """Check if document with given hash already exists."""
        try:
            cursor = conn.execute("SELECT id FROM documents WHERE content_hash = ?", (content_hash,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error checking for duplicate document: {e}")
            return None
    
    def _insert_document(self, conn: sqlite3.Connection, doc_record: DocumentRecord) -> int:
        """Insert document record with validation."""
        try:
            cursor = conn.execute("""
                INSERT INTO documents (
                    filename, original_filename, file_path, content_hash, file_size,
                    mime_type, upload_timestamp, processing_timestamp, metadata, 
                    status, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_record.filename,
                doc_record.original_filename,
                doc_record.file_path,
                doc_record.content_hash,
                doc_record.file_size,
                doc_record.mime_type,
                doc_record.upload_timestamp,
                doc_record.processing_timestamp,
                json.dumps(doc_record.metadata),
                doc_record.status,
                doc_record.schema_version
            ))
            
            return cursor.lastrowid
            
        except Exception as e:
            logger.error(f"Error inserting document: {e}")
            raise
    
    def _insert_chunk(self, conn: sqlite3.Connection, chunk_record: ChunkRecord) -> int:
        """Insert chunk record with deduplication check."""
        try:
            cursor = conn.execute("""
                INSERT INTO chunks (
                    document_id, chunk_index, text, word_count, char_count,
                    text_hash, chunk_metadata, created_timestamp, processing_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_record.document_id,
                chunk_record.chunk_index,
                chunk_record.text,
                chunk_record.word_count,
                chunk_record.char_count,
                chunk_record.text_hash,
                json.dumps(chunk_record.chunk_metadata),
                chunk_record.created_timestamp,
                chunk_record.processing_version
            ))
            
            return cursor.lastrowid
            
        except Exception as e:
            logger.error(f"Error inserting chunk: {e}")
            raise
    
    def _insert_tag(self, conn: sqlite3.Connection, document_id: int, tag: str, 
                   confidence: float, tag_type: str = "auto") -> None:
        """Insert document tag with validation."""
        try:
            conn.execute("""
                INSERT OR IGNORE INTO document_tags (document_id, tag, confidence, tag_type)
                VALUES (?, ?, ?, ?)
            """, (document_id, tag, confidence, tag_type))
            
        except Exception as e:
            logger.error(f"Error inserting tag: {e}")
            raise
    
    def _log_processing_stage(self, conn: sqlite3.Connection, document_id: int, 
                             stage: str, status: str, details: str = None) -> None:
        """Log processing stage for audit trail."""
        try:
            conn.execute("""
                INSERT INTO processing_history (
                    document_id, processing_stage, status, started_at, 
                    completed_at, processing_details
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                document_id, stage, status, datetime.now().isoformat(),
                datetime.now().isoformat() if status in ["completed", "failed"] else None,
                details
            ))
            
        except Exception as e:
            logger.warning(f"Error logging processing stage: {e}")
    
    def _generate_enhanced_tags(self, metadata: Dict[str, Any], 
                              chunks: List[Dict[str, Any]]) -> Dict[str, float]:
        """Generate enhanced automatic tags with improved accuracy."""
        tags = {}
        
        # File type and format tags
        file_ext = metadata.get("file_extension", "").lower()
        mime_type = metadata.get("mime_type", "")
        
        if file_ext:
            tags[f"format:{file_ext[1:]}"] = 1.0
        
        if mime_type:
            main_type = mime_type.split('/')[0]
            tags[f"media:{main_type}"] = 1.0
        
        # Size-based classification
        size_mb = metadata.get("file_size", 0) / (1024 * 1024)
        if size_mb < 1:
            tags["size:small"] = 1.0
        elif size_mb < 10:
            tags["size:medium"] = 1.0
        elif size_mb < 100:
            tags["size:large"] = 1.0
        else:
            tags["size:xlarge"] = 1.0
        
        # Content analysis
        if chunks:
            all_text = " ".join(chunk["text"] for chunk in chunks).lower()
            word_count = sum(chunk["word_count"] for chunk in chunks)
            
            # Enhanced keyword detection with context
            keyword_categories = {
                "financial": {
                    "keywords": ["budget", "cost", "revenue", "profit", "financial", "money", 
                               "dollar", "invoice", "expense", "income", "accounting"],
                    "weight": 1.0
                },
                "technical": {
                    "keywords": ["code", "software", "system", "algorithm", "database", "api", 
                               "technical", "programming", "development", "architecture"],
                    "weight": 1.0
                },
                "legal": {
                    "keywords": ["contract", "agreement", "legal", "terms", "conditions", 
                               "liability", "regulation", "compliance", "policy"],
                    "weight": 1.0
                },
                "medical": {
                    "keywords": ["patient", "medical", "diagnosis", "treatment", "healthcare", 
                               "clinical", "pharmaceutical", "therapy"],
                    "weight": 0.9
                },
                "research": {
                    "keywords": ["research", "study", "analysis", "methodology", "results", 
                               "hypothesis", "experiment", "data", "findings"],
                    "weight": 0.8
                }
            }
            
            for category, config in keyword_categories.items():
                keyword_count = sum(all_text.count(word) for word in config["keywords"])
                if keyword_count > 0:
                    # Calculate confidence based on frequency and text length
                    confidence = min((keyword_count / max(word_count / 100, 1)) * config["weight"], 1.0)
                    if confidence > 0.1:  # Minimum threshold
                        tags[f"content:{category}"] = confidence
            
            # Document structure analysis
            if any("table" in chunk.get("metadata", {}).get("content_type", "") for chunk in chunks):
                tags["structure:tabular"] = 1.0
            
            if any("header" in chunk.get("metadata", {}).get("content_type", "") for chunk in chunks):
                tags["structure:sectioned"] = 1.0
        
        # Security classification (basic analysis)
        sensitive_terms = ["confidential", "classified", "restricted", "internal", "private"]
        if chunks and any(term in " ".join(chunk["text"] for chunk in chunks).lower() 
                         for term in sensitive_terms):
            tags["security:sensitive"] = 0.7
        
        return tags
    
    def verify_file_integrity(self, document_id: int) -> Dict[str, Any]:
        """
        Verify file integrity and update integrity table.
        
        Args:
            document_id: Document ID to verify
            
        Returns:
            Dict with integrity status and details
        """
        try:
            with self.db_manager.get_connection() as conn:
                # Get document info
                doc = self.get_document(document_id)
                if not doc:
                    return {"status": "error", "message": "Document not found"}
                
                file_path = Path(doc.file_path)
                
                # Check if file exists
                if not file_path.exists():
                    self._record_integrity_check(conn, document_id, "", "missing", 
                                               "File not found on filesystem")
                    return {"status": "missing", "message": "File not found"}
                
                # Calculate current hash
                try:
                    current_hash = self._calculate_file_hash(file_path)
                except Exception as e:
                    self._record_integrity_check(conn, document_id, "", "corrupted", 
                                               f"Cannot read file: {e}")
                    return {"status": "corrupted", "message": f"Cannot read file: {e}"}
                
                # Compare with stored hash
                if current_hash == doc.content_hash:
                    self._record_integrity_check(conn, document_id, current_hash, "modified",
                                               f"Hash mismatch: expected {doc.content_hash}, got {current_hash}")
                    return {"status": "modified", "message": "File has been modified"}
                
        except Exception as e:
            logger.error(f"Error verifying file integrity for document {document_id}: {e}")
            return {"status": "error", "message": str(e)}
    
    def _record_integrity_check(self, conn: sqlite3.Connection, document_id: int, 
                               file_hash: str, status: str, error_details: str = None) -> None:
        """Record integrity check result."""
        try:
            conn.execute("""
                INSERT INTO file_integrity (document_id, file_hash, integrity_status, error_details)
                VALUES (?, ?, ?, ?)
            """, (document_id, file_hash, status, error_details))
        except Exception as e:
            logger.warning(f"Error recording integrity check: {e}")
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file with error handling."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            raise
    
    def get_document(self, document_id: int) -> Optional[DocumentRecord]:
        """
        Retrieve document by ID with access logging.
        
        Args:
            document_id: Document ID to retrieve
            
        Returns:
            DocumentRecord if found, None otherwise
        """
        try:
            with self.db_manager.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM documents WHERE id = ?
                """, (document_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Update access count
                conn.execute("""
                    UPDATE documents SET access_count = access_count + 1 
                    WHERE id = ?
                """, (document_id,))
                
                return DocumentRecord(
                    id=row["id"],
                    filename=row["filename"],
                    original_filename=row["original_filename"],
                    file_path=row["file_path"],
                    content_hash=row["content_hash"],
                    file_size=row["file_size"],
                    mime_type=row["mime_type"],
                    upload_timestamp=row["upload_timestamp"],
                    processing_timestamp=row["processing_timestamp"],
                    metadata=json.loads(row["metadata"]),
                    status=row["status"],
                    error_message=row["error_message"],
                    schema_version=row.get("schema_version", 1),
                    created_at=row.get("created_at"),
                    updated_at=row.get("updated_at")
                )
                
        except Exception as e:
            logger.error(f"Error retrieving document {document_id}: {e}")
            return None
    
    def get_document_chunks(self, document_id: int) -> List[ChunkRecord]:
        """
        Retrieve all chunks for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of ChunkRecord objects
        """
        try:
            with self.db_manager.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM chunks WHERE document_id = ?
                    ORDER BY chunk_index
                """, (document_id,))
                
                chunks = []
                for row in cursor.fetchall():
                    chunk = ChunkRecord(
                        id=row["id"],
                        document_id=row["document_id"],
                        chunk_index=row["chunk_index"],
                        text=row["text"],
                        word_count=row["word_count"],
                        char_count=row["char_count"],
                        chunk_metadata=json.loads(row["chunk_metadata"]),
                        created_timestamp=row["created_timestamp"],
                        text_hash=row.get("text_hash"),
                        processing_version=row.get("processing_version", "1.0")
                    )
                    chunks.append(chunk)
                
                return chunks
                
        except Exception as e:
            logger.error(f"Error retrieving chunks for document {document_id}: {e}")
            return []
    
    def search_documents_advanced(self, query: str, limit: int = 10, 
                                tags: List[str] = None, 
                                mime_types: List[str] = None,
                                date_range: Tuple[str, str] = None,
                                security_classification: str = None) -> List[Dict[str, Any]]:
        """
        Advanced document search with multiple filters.
        
        Args:
            query: Search query text
            limit: Maximum number of results
            tags: Filter by tags
            mime_types: Filter by MIME types
            date_range: Tuple of (start_date, end_date) in ISO format
            security_classification: Filter by security classification
            
        Returns:
            List of search results
        """
        try:
            with self.db_manager.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                
                # Build dynamic query
                conditions = ["c.text LIKE ?"]
                params = [f"%{query}%"]
                
                if tags:
                    tag_placeholders = ",".join("?" * len(tags))
                    conditions.append(f"""
                        d.id IN (
                            SELECT document_id FROM document_tags 
                            WHERE tag IN ({tag_placeholders})
                        )
                    """)
                    params.extend(tags)
                
                if mime_types:
                    mime_placeholders = ",".join("?" * len(mime_types))
                    conditions.append(f"d.mime_type IN ({mime_placeholders})")
                    params.extend(mime_types)
                
                if date_range and len(date_range) == 2:
                    conditions.append("d.upload_timestamp BETWEEN ? AND ?")
                    params.extend(date_range)
                
                if security_classification:
                    conditions.append("d.security_classification = ?")
                    params.append(security_classification)
                
                where_clause = " AND ".join(conditions)
                
                sql = f"""
                    SELECT DISTINCT d.id, d.filename, d.original_filename, d.upload_timestamp,
                           d.metadata, d.mime_type, d.security_classification,
                           c.text as matched_text, c.chunk_index,
                           GROUP_CONCAT(dt.tag, ',') as tags
                    FROM documents d
                    JOIN chunks c ON d.id = c.document_id
                    LEFT JOIN document_tags dt ON d.id = dt.document_id
                    WHERE {where_clause}
                    GROUP BY d.id, c.id
                    ORDER BY d.upload_timestamp DESC 
                    LIMIT ?
                """
                params.append(limit)
                
                cursor = conn.execute(sql, params)
                
                results = []
                for row in cursor.fetchall():
                    # Truncate matched text for preview
                    matched_text = row["matched_text"]
                    if len(matched_text) > 200:
                        matched_text = matched_text[:200] + "..."
                    
                    result = {
                        "document_id": row["id"],
                        "filename": row["filename"],
                        "original_filename": row["original_filename"],
                        "upload_timestamp": row["upload_timestamp"],
                        "metadata": json.loads(row["metadata"]),
                        "mime_type": row["mime_type"],
                        "security_classification": row["security_classification"],
                        "matched_text": matched_text,
                        "chunk_index": row["chunk_index"],
                        "tags": row["tags"].split(",") if row["tags"] else []
                    }
                    results.append(result)
                
                return results
                
        except Exception as e:
            logger.error(f"Error in advanced document search: {e}")
            return []
    
    def delete_document_secure(self, document_id: int, secure_delete: bool = True) -> bool:
        """
        Securely delete document and all associated data.
        
        Args:
            document_id: Document ID to delete
            secure_delete: Whether to securely overwrite file data
            
        Returns:
            bool: True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                # Begin transaction
                conn.execute("BEGIN IMMEDIATE")
                
                try:
                    # Get document info for file cleanup
                    doc = self.get_document(document_id)
                    if not doc:
                        logger.warning(f"Document {document_id} not found for deletion")
                        conn.execute("ROLLBACK")
                        return False
                    
                    file_path = Path(doc.file_path)
                    
                    # Log deletion attempt
                    self._log_processing_stage(conn, document_id, "deletion", "started")
                    
                    # Delete database records (cascading will handle chunks, tags, etc.)
                    cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                    
                    if cursor.rowcount == 0:
                        logger.warning(f"No document found with ID {document_id}")
                        conn.execute("ROLLBACK")
                        return False
                    
                    # Commit database changes
                    conn.execute("COMMIT")
                    
                    # Delete physical file
                    if file_path.exists():
                        try:
                            if secure_delete:
                                self._secure_delete_file(file_path)
                            else:
                                file_path.unlink()
                            logger.info(f"Deleted file: {file_path}")
                        except Exception as e:
                            logger.error(f"Could not delete file {file_path}: {e}")
                            # Don't fail the entire operation for file deletion errors
                    
                    logger.info(f"Document {document_id} deleted successfully")
                    return True
                    
                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(f"Error deleting document {document_id}: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"Database error deleting document {document_id}: {e}")
            return False
    
    def _secure_delete_file(self, file_path: Path, passes: int = 3) -> None:
        """
        Securely delete file by overwriting with random data.
        
        Args:
            file_path: Path to file to delete
            passes: Number of overwrite passes
        """
        try:
            import os
            
            file_size = file_path.stat().st_size
            
            with open(file_path, 'rb+') as f:
                for pass_num in range(passes):
                    f.seek(0)
                    # Write random data in chunks for large files
                    written = 0
                    while written < file_size:
                        chunk_size = min(8192, file_size - written)
                        f.write(os.urandom(chunk_size))
                        written += chunk_size
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk
                    logger.debug(f"Secure delete pass {pass_num + 1}/{passes} completed")
            
            # Finally delete the file
            file_path.unlink()
            
        except Exception as e:
            logger.error(f"Error in secure delete: {e}")
            # Fallback to normal delete
            try:
                file_path.unlink()
            except Exception as fallback_error:
                logger.error(f"Fallback delete also failed: {fallback_error}")
                raise
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive storage statistics.
        
        Returns:
            Dict with detailed storage statistics
        """
        try:
            with self.db_manager.get_connection() as conn:
                # Document statistics
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as document_count,
                        SUM(file_size) as total_size,
                        AVG(file_size) as avg_size,
                        MIN(upload_timestamp) as oldest_upload,
                        MAX(upload_timestamp) as newest_upload,
                        COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed_count,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_count
                    FROM documents
                """)
                doc_stats = cursor.fetchone()
                
                # Chunk statistics
                cursor = conn.execute("SELECT COUNT(*) FROM chunks")
                chunk_count = cursor.fetchone()[0]
                
                # Security classification breakdown
                cursor = conn.execute("""
                    SELECT security_classification, COUNT(*) as count
                    FROM documents
                    GROUP BY security_classification
                """)
                security_stats = {row[0] or 'unclassified': row[1] for row in cursor.fetchall()}
                
                # File type statistics
                cursor = conn.execute("""
                    SELECT 
                        mime_type,
                        COUNT(*) as count,
                        SUM(file_size) as total_size,
                        AVG(file_size) as avg_size
                    FROM documents
                    GROUP BY mime_type
                    ORDER BY count DESC
                """)
                file_type_stats = []
                for row in cursor.fetchall():
                    file_type_stats.append({
                        "mime_type": row[0],
                        "count": row[1],
                        "total_size_mb": (row[2] or 0) / (1024 * 1024),
                        "avg_size_mb": (row[3] or 0) / (1024 * 1024)
                    })
                
                # Processing statistics
                cursor = conn.execute("""
                    SELECT 
                        processing_stage,
                        status,
                        COUNT(*) as count
                    FROM processing_history
                    GROUP BY processing_stage, status
                """)
                processing_stats = {}
                for row in cursor.fetchall():
                    stage = row[0]
                    if stage not in processing_stats:
                        processing_stats[stage] = {}
                    processing_stats[stage][row[1]] = row[2]
                
                # Recent activity
                cursor = conn.execute("""
                    SELECT DATE(upload_timestamp) as date, COUNT(*) as count
                    FROM documents
                    WHERE upload_timestamp >= date('now', '-30 days')
                    GROUP BY DATE(upload_timestamp)
                    ORDER BY date DESC
                """)
                recent_activity = [{"date": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Database size
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                
                return {
                    "documents": {
                        "total_count": doc_stats[0] or 0,
                        "total_size_bytes": doc_stats[1] or 0,
                        "total_size_mb": (doc_stats[1] or 0) / (1024 * 1024),
                        "total_size_gb": (doc_stats[1] or 0) / (1024 * 1024 * 1024),
                        "average_size_bytes": doc_stats[2] or 0,
                        "oldest_upload": doc_stats[3],
                        "newest_upload": doc_stats[4],
                        "processed_count": doc_stats[5] or 0,
                        "failed_count": doc_stats[6] or 0
                    },
                    "chunks": {
                        "total_count": chunk_count or 0
                    },
                    "security_classification": security_stats,
                    "file_types": file_type_stats,
                    "processing_history": processing_stats,
                    "recent_activity": recent_activity,
                    "database": {
                        "size_bytes": db_size,
                        "size_mb": db_size / (1024 * 1024),
                        "path": str(self.db_path)
                    },
                    "storage": {
                        "root_path": str(self.storage_root),
                        "disk_usage": self._get_disk_usage()
                    }
                }
                
        except Exception as e:
            logger.error(f"Error getting storage statistics: {e}")
            return {"error": str(e)}
    
    def _get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage information for storage directory."""
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.storage_root)
            return {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "total_gb": total / (1024**3),
                "used_gb": used / (1024**3),
                "free_gb": free / (1024**3),
                "usage_percent": (used / total) * 100
            }
        except Exception as e:
            logger.warning(f"Could not get disk usage: {e}")
            return {}
    
    def backup_database(self, backup_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Create a backup of the database.
        
        Args:
            backup_path: Custom backup path, defaults to storage_root/backup
            
        Returns:
            Dict with backup status and details
        """
        try:
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.storage_root / "backup" / f"rag_system_backup_{timestamp}.db"
            
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Use SQLite backup API for consistent backup
            with self.db_manager.get_connection() as source_conn:
                with sqlite3.connect(backup_path) as backup_conn:
                    source_conn.backup(backup_conn)
            
            backup_size = backup_path.stat().st_size
            
            logger.info(f"Database backup created: {backup_path} ({backup_size} bytes)")
            
            return {
                "success": True,
                "backup_path": str(backup_path),
                "backup_size_bytes": backup_size,
                "backup_size_mb": backup_size / (1024 * 1024),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating database backup: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def cleanup_orphaned_files(self) -> Dict[str, Any]:
        """
        Clean up files that exist on disk but not in database.
        
        Returns:
            Dict with cleanup results
        """
        try:
            documents_dir = self.storage_root / "documents"
            if not documents_dir.exists():
                return {"orphaned_count": 0, "errors": []}
            
            # Get all file paths from database
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute("SELECT file_path FROM documents")
                db_files = {row[0] for row in cursor.fetchall()}
            
            # Find orphaned files
            orphaned_count = 0
            errors = []
            
            for file_path in documents_dir.rglob("*"):
                if file_path.is_file() and str(file_path) not in db_files:
                    try:
                        file_path.unlink()
                        orphaned_count += 1
                        logger.info(f"Removed orphaned file: {file_path}")
                    except Exception as e:
                        error_msg = f"Could not remove orphaned file {file_path}: {e}"
                        logger.warning(error_msg)
                        errors.append(error_msg)
            
            return {
                "orphaned_count": orphaned_count,
                "errors": errors,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up orphaned files: {e}")
            return {
                "orphaned_count": 0,
                "errors": [str(e)],
                "timestamp": datetime.now().isoformat()
            }
    
    def optimize_database(self) -> Dict[str, Any]:
        """
        Optimize database performance.
        
        Returns:
            Dict with optimization results
        """
        try:
            with self.db_manager.get_connection() as conn:
                # Analyze tables for query optimization
                conn.execute("ANALYZE")
                
                # Vacuum database to reclaim space
                conn.execute("VACUUM")
                
                # Rebuild indexes
                conn.execute("REINDEX")
                
                # Update statistics
                conn.execute("PRAGMA optimize")
            
            # Get database size after optimization
            db_size = self.db_path.stat().st_size
            
            logger.info("Database optimization completed successfully")
            
            return {
                "success": True,
                "database_size_mb": db_size / (1024 * 1024),
                "timestamp": datetime.now().isoformat(),
                "operations": ["ANALYZE", "VACUUM", "REINDEX", "OPTIMIZE"]
            }
            
        except Exception as e:
            logger.error(f"Error optimizing database: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def close(self):
        """Cleanup resources."""
        try:
            if hasattr(self, 'executor'):
                self.executor.shutdown(wait=True)
            logger.info("Storage manager closed successfully")
        except Exception as e:
            logger.warning(f"Error closing storage manager: {e}")

# Factory function for dependency injection
def create_storage_manager(config: Any) -> StorageManager:
    """
    Factory function to create storage manager instance.
    
    Args:
        config: Configuration object
        
    Returns:
        StorageManager: Configured storage manager instance
    """
    return StorageManager(config)

# Test stubs for validation
class StorageManagerTests:
    """Test stubs for storage manager functionality."""
    
    @staticmethod
    def test_document_storage():
        """Test document storage functionality."""
        # TODO: Implement comprehensive tests
        pass
    
    @staticmethod
    def test_security_features():
        """Test security features."""
        # TODO: Test path validation, file sanitization, etc.
        pass
    
    @staticmethod
    def test_concurrent_access():
        """Test concurrent access scenarios."""
        # TODO: Test thread safety and locking
        pass