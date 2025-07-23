"""
MIDAS Backend Configuration
Windows-specific settings and environment configuration
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator

class Settings(BaseSettings):
    """Application settings with Windows integration"""
    
    # Application
    APP_NAME: str = "MIDAS"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "midas"
    POSTGRES_USER: str = "midas_user"
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    
    # External Services
    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434
    OLLAMA_URL: str = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
    
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = f"http://{QDRANT_HOST}:{QDRANT_PORT}"
    
    # File Storage (Windows paths)
    DATA_DIR: Path = Path("data")
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    TEMP_DIR: Path = DATA_DIR / "temp"
    BACKUP_DIR: Path = Path("backups")
    LOG_DIR: Path = Path("logs")
    
    # Windows AppData integration
    @property
    def APPDATA_DIR(self) -> Path:
        """Get Windows AppData directory for user-specific data"""
        if os.name == 'nt':
            appdata = os.getenv('APPDATA')
            if appdata:
                return Path(appdata) / "MIDAS"
        return Path.home() / ".midas"
    
    @property
    def DASHBOARD_DIR(self) -> Path:
        """Dashboard storage directory"""
        return self.APPDATA_DIR / "dashboards"
    
    @property
    def CONFIG_DIR(self) -> Path:
        """Configuration directory"""
        return self.APPDATA_DIR / "config"
    
    # File upload settings
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: List[str] = [
        '.pdf', '.txt', '.docx', '.doc', '.xlsx', '.xls', 
        '.csv', '.json', '.md', '.py', '.sql'
    ]
    
    # Windows-specific settings
    WINDOWS_AUTH_ENABLED: bool = True
    WINDOWS_FILE_WATCHER: bool = True
    USE_WINDOWS_PATHS: bool = os.name == 'nt'
    
    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ]
    
    # WebSocket settings
    WS_PING_INTERVAL: int = 30
    WS_PING_TIMEOUT: int = 10
    WS_CLOSE_TIMEOUT: int = 30
    
    # Celery settings
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL
    CELERY_TIMEZONE: str = "UTC"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_MAX_SIZE: int = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT: int = 5
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        if v not in ["development", "staging", "production"]:
            raise ValueError("Environment must be development, staging, or production")
        return v
    
    def create_directories(self):
        """Create necessary directories on Windows"""
        directories = [
            self.DATA_DIR,
            self.UPLOAD_DIR,
            self.TEMP_DIR,
            self.BACKUP_DIR,
            self.LOG_DIR,
            self.APPDATA_DIR,
            self.DASHBOARD_DIR,
            self.CONFIG_DIR
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create global settings instance
settings = Settings()

# Create directories on import
settings.create_directories()