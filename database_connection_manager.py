"""
MIDAS Database Connection Manager
Handles multiple database connections with Windows-specific authentication
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus
import pyodbc
from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
from contextlib import contextmanager
import win32api
import win32security
import win32con

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    name: str
    db_type: str  # postgresql, mysql, sqlite, mssql
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    use_windows_auth: bool = False
    connection_string: Optional[str] = None
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    echo: bool = False
    options: Dict[str, Any] = None

    def __post_init__(self):
        if self.options is None:
            self.options = {}

class DatabaseConnectionManager:
    """Manages database connections with Windows support"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(__file__).parent / 'config' / 'databases.json'
        self.connections: Dict[str, Engine] = {}
        self.configs: Dict[str, DatabaseConfig] = {}
        self._load_configs()
        self._init_odbc_drivers()
    
    def _init_odbc_drivers(self):
        """Initialize and list available ODBC drivers on Windows"""
        try:
            self.available_drivers = pyodbc.drivers()
            logger.info(f"Available ODBC drivers: {self.available_drivers}")
        except Exception as e:
            logger.warning(f"Failed to list ODBC drivers: {e}")
            self.available_drivers = []
    
    def _load_configs(self):
        """Load database configurations from file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    configs = json.load(f)
                    for name, config in configs.items():
                        self.configs[name] = DatabaseConfig(name=name, **config)
                logger.info(f"Loaded {len(self.configs)} database configurations")
            except Exception as e:
                logger.error(f"Failed to load database configs: {e}")
    
    def save_configs(self):
        """Save database configurations to file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        configs_dict = {name: asdict(config) for name, config in self.configs.items()}
        
        with open(self.config_path, 'w') as f:
            json.dump(configs_dict, f, indent=2)
        logger.info(f"Saved {len(self.configs)} database configurations")
    
    def add_config(self, config: DatabaseConfig):
        """Add a database configuration"""
        self.configs[config.name] = config
        self.save_configs()
    
    def get_connection_string(self, config: DatabaseConfig) -> str:
        """Build connection string based on database type and configuration"""
        if config.connection_string:
            return config.connection_string
        
        if config.db_type == 'sqlite':
            # SQLite with Windows path support
            db_path = Path(config.database).resolve()
            return f"sqlite:///{db_path}"
        
        elif config.db_type == 'postgresql':
            if config.use_windows_auth:
                # PostgreSQL with SSPI (Windows auth)
                return (f"postgresql://{config.host}:{config.port or 5432}/"
                       f"{config.database}?sslmode=prefer&gssencmode=prefer")
            else:
                password = quote_plus(config.password) if config.password else ''
                return (f"postgresql://{config.username}:{password}@"
                       f"{config.host}:{config.port or 5432}/{config.database}")
        
        elif config.db_type == 'mysql':
            password = quote_plus(config.password) if config.password else ''
            driver = config.options.get('driver', 'pymysql')
            return (f"mysql+{driver}://{config.username}:{password}@"
                   f"{config.host}:{config.port or 3306}/{config.database}")
        
        elif config.db_type == 'mssql':
            # SQL Server with Windows Authentication or SQL Auth
            driver = config.options.get('driver', 'ODBC Driver 17 for SQL Server')
            
            if config.use_windows_auth:
                # Windows Authentication
                conn_str = (
                    f"mssql+pyodbc://{config.host}\\{config.options.get('instance', 'SQLEXPRESS')}/"
                    f"{config.database}?driver={driver}&trusted_connection=yes"
                )
            else:
                # SQL Authentication
                password = quote_plus(config.password) if config.password else ''
                conn_str = (
                    f"mssql+pyodbc://{config.username}:{password}@"
                    f"{config.host}\\{config.options.get('instance', 'SQLEXPRESS')}/"
                    f"{config.database}?driver={driver}"
                )
            
            return conn_str
        
        else:
            raise ValueError(f"Unsupported database type: {config.db_type}")
    
    def create_engine(self, config: DatabaseConfig) -> Engine:
        """Create SQLAlchemy engine with appropriate settings"""
        connection_string = self.get_connection_string(config)
        
        # Engine configuration
        engine_config = {
            'echo': config.echo,
            'pool_pre_ping': True,  # Verify connections before using
            'pool_recycle': 3600,   # Recycle connections after 1 hour
        }
        
        # Configure connection pooling based on database type
        if config.db_type == 'sqlite':
            # SQLite doesn't need connection pooling
            engine_config['poolclass'] = NullPool
        else:
            # Use QueuePool for other databases
            engine_config['pool_size'] = config.pool_size
            engine_config['max_overflow'] = config.max_overflow
            engine_config['pool_timeout'] = config.pool_timeout
        
        # Add Windows-specific options for SQL Server
        if config.db_type == 'mssql' and config.use_windows_auth:
            engine_config['connect_args'] = {
                'trusted_connection': 'yes',
                'timeout': 30
            }
        
        try:
            engine = create_engine(connection_string, **engine_config)
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info(f"Successfully created engine for database: {config.name}")
            return engine
            
        except Exception as e:
            logger.error(f"Failed to create engine for {config.name}: {e}")
            raise
    
    def get_connection(self, name: str) -> Engine:
        """Get or create a database connection"""
        if name not in self.configs:
            raise ValueError(f"Database configuration '{name}' not found")
        
        if name not in self.connections:
            config = self.configs[name]
            self.connections[name] = self.create_engine(config)
        
        return self.connections[name]
    
    @contextmanager
    def get_session(self, name: str):
        """Context manager for database sessions"""
        engine = self.get_connection(name)
        connection = engine.connect()
        
        try:
            yield connection
        finally:
            connection.close()
    
    def test_connection(self, name: str) -> Dict[str, Any]:
        """Test database connection and return status"""
        try:
            engine = self.get_connection(name)
            config = self.configs[name]
            
            with engine.connect() as conn:
                # Get version info
                if config.db_type == 'postgresql':
                    result = conn.execute(text("SELECT version()"))
                    version = result.scalar()
                elif config.db_type == 'mysql':
                    result = conn.execute(text("SELECT VERSION()"))
                    version = result.scalar()
                elif config.db_type == 'mssql':
                    result = conn.execute(text("SELECT @@VERSION"))
                    version = result.scalar()
                elif config.db_type == 'sqlite':
                    result = conn.execute(text("SELECT sqlite_version()"))
                    version = f"SQLite {result.scalar()}"
                else:
                    version = "Unknown"
                
                # Get database size (if applicable)
                size = None
                if config.db_type == 'postgresql':
                    result = conn.execute(
                        text(f"SELECT pg_database_size('{config.database}')")
                    )
                    size = result.scalar()
                elif config.db_type == 'mysql':
                    result = conn.execute(
                        text(
                            "SELECT SUM(data_length + index_length) "
                            "FROM information_schema.tables "
                            f"WHERE table_schema = '{config.database}'"
                        )
                    )
                    size = result.scalar() or 0
                
                return {
                    'status': 'connected',
                    'version': version,
                    'database': config.database,
                    'type': config.db_type,
                    'host': config.host,
                    'size_bytes': size,
                    'windows_auth': config.use_windows_auth
                }
        
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'database': name,
                'type': self.configs[name].db_type if name in self.configs else 'unknown'
            }
    
    def get_table_list(self, name: str) -> List[str]:
        """Get list of tables in database"""
        engine = self.get_connection(name)
        inspector = inspect(engine)
        return inspector.get_table_names()
    
    def get_table_info(self, name: str, table_name: str) -> Dict[str, Any]:
        """Get detailed information about a table"""
        engine = self.get_connection(name)
        inspector = inspect(engine)
        
        # Get columns
        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                'name': col['name'],
                'type': str(col['type']),
                'nullable': col['nullable'],
                'default': col.get('default'),
                'primary_key': col.get('primary_key', False)
            })
        
        # Get primary keys
        pk_constraint = inspector.get_pk_constraint(table_name)
        primary_keys = pk_constraint['constrained_columns'] if pk_constraint else []
        
        # Get foreign keys
        foreign_keys = []
        for fk in inspector.get_foreign_keys(table_name):
            foreign_keys.append({
                'name': fk.get('name'),
                'columns': fk['constrained_columns'],
                'referred_table': fk['referred_table'],
                'referred_columns': fk['referred_columns']
            })
        
        # Get indexes
        indexes = []
        for idx in inspector.get_indexes(table_name):
            indexes.append({
                'name': idx['name'],
                'columns': idx['column_names'],
                'unique': idx.get('unique', False)
            })
        
        # Get row count
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_count = result.scalar()
        
        return {
            'table_name': table_name,
            'columns': columns,
            'primary_keys': primary_keys,
            'foreign_keys': foreign_keys,
            'indexes': indexes,
            'row_count': row_count
        }
    
    def execute_query(self, name: str, query: str, 
                     params: Optional[Dict] = None,
                     limit: Optional[int] = None) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame"""
        engine = self.get_connection(name)
        
        # Add limit if specified and not already in query
        if limit and 'limit' not in query.lower():
            query = f"{query} LIMIT {limit}"
        
        try:
            df = pd.read_sql_query(query, engine, params=params)
            return df
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def get_sample_data(self, name: str, table_name: str, 
                       sample_size: int = 100) -> pd.DataFrame:
        """Get sample data from a table"""
        config = self.configs[name]
        
        # Build appropriate query based on database type
        if config.db_type in ['postgresql', 'sqlite']:
            query = f"SELECT * FROM {table_name} LIMIT {sample_size}"
        elif config.db_type == 'mysql':
            query = f"SELECT * FROM {table_name} LIMIT {sample_size}"
        elif config.db_type == 'mssql':
            query = f"SELECT TOP {sample_size} * FROM {table_name}"
        else:
            query = f"SELECT * FROM {table_name}"
        
        return self.execute_query(name, query)
    
    def close_all(self):
        """Close all database connections"""
        for name, engine in self.connections.items():
            try:
                engine.dispose()
                logger.info(f"Closed connection: {name}")
            except Exception as e:
                logger.error(f"Failed to close connection {name}: {e}")
        
        self.connections.clear()

# Utility functions for Windows authentication
def get_windows_username() -> str:
    """Get current Windows username"""
    try:
        return win32api.GetUserName()
    except:
        return os.environ.get('USERNAME', 'Unknown')

def get_windows_domain() -> str:
    """Get current Windows domain"""
    try:
        return win32api.GetDomainName()
    except:
        return os.environ.get('USERDOMAIN', 'Unknown')

# Example configurations
def create_example_configs() -> List[DatabaseConfig]:
    """Create example database configurations"""
    configs = []
    
    # SQLite example
    configs.append(DatabaseConfig(
        name="local_sqlite",
        db_type="sqlite",
        database=str(Path.home() / "Documents" / "midas_test.db")
    ))
    
    # PostgreSQL with standard auth
    configs.append(DatabaseConfig(
        name="postgres_main",
        db_type="postgresql",
        host="localhost",
        port=5432,
        database="midas_db",
        username="midas_user",
        password="midas_password"
    ))
    
    # SQL Server with Windows auth
    configs.append(DatabaseConfig(
        name="sqlserver_local",
        db_type="mssql",
        host="localhost",
        database="MIDAS",
        use_windows_auth=True,
        options={'instance': 'SQLEXPRESS'}
    ))
    
    # MySQL example
    configs.append(DatabaseConfig(
        name="mysql_dev",
        db_type="mysql",
        host="localhost",
        port=3306,
        database="midas_dev",
        username="root",
        password="mysql_password"
    ))
    
    return configs

if __name__ == "__main__":
    # Test database connection manager
    manager = DatabaseConnectionManager()
    
    # Add example configurations if none exist
    if not manager.configs:
        for config in create_example_configs():
            manager.add_config(config)
    
    # Test connections
    for name in manager.configs:
        print(f"\nTesting connection: {name}")
        result = manager.test_connection(name)
        print(f"Result: {result}")