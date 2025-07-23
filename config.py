"""
Configuration management for RAG System
Handles loading and validation of configuration files
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

@dataclass
class OllamaConfig:
    """Ollama LLM configuration"""
    base_url: str = "http://localhost:11434"
    models: list = field(default_factory=lambda: ["llama3.2:3b", "phi3:mini"])
    default_model: str = "llama3.2:3b"
    timeout: int = 30
    temperature: float = 0.7
    max_tokens: int = 2048

@dataclass
class QdrantConfig:
    """Qdrant vector database configuration"""
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "documents"
    vector_size: int = 384  # all-MiniLM-L6-v2 dimensions
    distance: str = "Cosine"
    timeout: int = 30

@dataclass
class RedisConfig:
    """Redis cache configuration"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    timeout: int = 30

@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration"""
    host: str = "localhost"
    port: int = 5432
    database: str = "rag_system"
    username: str = "rag_user"
    password: str = "rag_password"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10

@dataclass
class EmbeddingConfig:
    """Embedding model configuration"""
    model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 500
    chunk_overlap: int = 100
    batch_size: int = 32
    device: str = "cpu"  # Windows CPU optimization

@dataclass
class UploadConfig:
    """File upload configuration"""
    max_file_size: int = 100  # MB
    allowed_extensions: list = field(default_factory=lambda: [
        ".txt", ".pdf", ".docx", ".csv", ".json", ".md", ".markdown"
    ])
    upload_dir: str = "data/uploads"
    temp_dir: str = "data/temp"

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    file: str = "logs/app.log"
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

@dataclass
class SecurityConfig:
    """Security configuration"""
    secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration: int = 3600  # 1 hour
    bcrypt_rounds: int = 12
    max_login_attempts: int = 5

@dataclass
class AppConfig:
    """Main application configuration"""
    name: str = "RAG System"
    version: str = "1.0.0"
    debug: bool = True
    host: str = "localhost"
    port: int = 8501
    
    # Component configurations
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

class ConfigManager:
    """Configuration manager for loading and validating config files"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._config: Optional[AppConfig] = None
    
    def load_config(self, config_file: str = "app_config.yml") -> AppConfig:
        """Load configuration from YAML file with environment variable overrides"""
        
        # Load from file
        config_path = self.config_dir / config_file
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f) or {}
                logger.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config file {config_path}: {e}")
                config_data = {}
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")
            config_data = {}
        
        # Apply environment variable overrides
        config_data = self._apply_env_overrides(config_data)
        
        # Create configuration objects
        self._config = self._create_config_objects(config_data)
        
        # Validate configuration
        self._validate_config()
        
        return self._config
    
    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides"""
        
        # Ollama overrides
        if os.getenv("OLLAMA_BASE_URL"):
            config_data.setdefault("ollama", {})["base_url"] = os.getenv("OLLAMA_BASE_URL")
        
        # Qdrant overrides
        if os.getenv("QDRANT_HOST"):
            config_data.setdefault("qdrant", {})["host"] = os.getenv("QDRANT_HOST")
        if os.getenv("QDRANT_PORT"):
            config_data.setdefault("qdrant", {})["port"] = int(os.getenv("QDRANT_PORT"))
        
        # Redis overrides
        if os.getenv("REDIS_HOST"):
            config_data.setdefault("redis", {})["host"] = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            config_data.setdefault("redis", {})["port"] = int(os.getenv("REDIS_PORT"))
        if os.getenv("REDIS_PASSWORD"):
            config_data.setdefault("redis", {})["password"] = os.getenv("REDIS_PASSWORD")
        
        # Database overrides
        if os.getenv("POSTGRES_HOST"):
            config_data.setdefault("database", {})["host"] = os.getenv("POSTGRES_HOST")
        if os.getenv("POSTGRES_PORT"):
            config_data.setdefault("database", {})["port"] = int(os.getenv("POSTGRES_PORT"))
        if os.getenv("POSTGRES_DB"):
            config_data.setdefault("database", {})["database"] = os.getenv("POSTGRES_DB")
        if os.getenv("POSTGRES_USER"):
            config_data.setdefault("database", {})["username"] = os.getenv("POSTGRES_USER")
        if os.getenv("POSTGRES_PASSWORD"):
            config_data.setdefault("database", {})["password"] = os.getenv("POSTGRES_PASSWORD")
        
        # Security overrides
        if os.getenv("SECRET_KEY"):
            config_data.setdefault("security", {})["secret_key"] = os.getenv("SECRET_KEY")
        
        return config_data
    
    def _create_config_objects(self, config_data: Dict[str, Any]) -> AppConfig:
        """Create configuration objects from dictionary"""
        
        # Extract component configurations
        ollama_config = OllamaConfig(**config_data.get("ollama", {}))
        qdrant_config = QdrantConfig(**config_data.get("qdrant", {}))
        redis_config = RedisConfig(**config_data.get("redis", {}))
        database_config = DatabaseConfig(**config_data.get("database", {}))
        embedding_config = EmbeddingConfig(**config_data.get("embedding", {}))
        upload_config = UploadConfig(**config_data.get("upload", {}))
        logging_config = LoggingConfig(**config_data.get("logging", {}))
        security_config = SecurityConfig(**config_data.get("security", {}))
        
        # Extract app-level configuration
        app_data = config_data.get("app", {})
        
        return AppConfig(
            name=app_data.get("name", "RAG System"),
            version=app_data.get("version", "1.0.0"),
            debug=app_data.get("debug", True),
            host=app_data.get("host", "localhost"),
            port=app_data.get("port", 8501),
            ollama=ollama_config,
            qdrant=qdrant_config,
            redis=redis_config,
            database=database_config,
            embedding=embedding_config,
            upload=upload_config,
            logging=logging_config,
            security=security_config
        )
    
    def _validate_config(self):
        """Validate configuration values"""
        if not self._config:
            raise ValueError("Configuration not loaded")
        
        # Validate required directories
        upload_dir = Path(self._config.upload.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        temp_dir = Path(self._config.upload.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)