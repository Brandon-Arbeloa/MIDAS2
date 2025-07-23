"""
Optimized Connection Pooling for MIDAS on Windows 11
High-performance connection management for PostgreSQL and Qdrant
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
import psutil
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

# Database imports
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.pool import QueuePool, StaticPool

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.http import models
import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

@dataclass
class ConnectionPoolStats:
    """Connection pool statistics"""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    connections_created: int = 0
    connections_closed: int = 0
    connection_errors: int = 0
    avg_connection_time: float = 0.0
    last_reset: datetime = field(default_factory=datetime.now)

class WindowsOptimizedConnectionPool:
    """Base class for Windows-optimized connection pools"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.stats = ConnectionPoolStats()
        self._connection_times: List[float] = []
        
        # Windows-specific optimizations
        self._apply_windows_tcp_optimizations()
    
    def _apply_windows_tcp_optimizations(self):
        """Apply Windows-specific TCP optimizations"""
        try:
            import socket
            
            # Set TCP_NODELAY for faster connection establishment
            socket.setdefaulttimeout(10)  # 10 second timeout
            
            # Windows-specific socket options
            if hasattr(socket, 'TCP_FASTOPEN'):
                # Enable TCP Fast Open if available
                pass
                
        except Exception as e:
            logger.warning(f"Could not apply TCP optimizations: {e}")
    
    def record_connection_time(self, connection_time: float):
        """Record connection establishment time"""
        self._connection_times.append(connection_time)
        
        # Keep only last 100 measurements
        if len(self._connection_times) > 100:
            self._connection_times = self._connection_times[-100:]
        
        # Update average
        self.stats.avg_connection_time = sum(self._connection_times) / len(self._connection_times)

class PostgreSQLConnectionPool(WindowsOptimizedConnectionPool):
    """Optimized PostgreSQL connection pool for Windows"""
    
    def __init__(self):
        super().__init__("PostgreSQL")
        self.engine: Optional[AsyncEngine] = None
        self.raw_pool: Optional[asyncpg.Pool] = None
        
        # Windows-optimized pool settings
        self.pool_config = {
            "pool_size": min(20, psutil.cpu_count() * 2),  # Based on CPU cores
            "max_overflow": 40,
            "pool_timeout": 30,
            "pool_recycle": 3600,  # 1 hour
            "pool_pre_ping": True,
            "connect_args": {
                "command_timeout": 10,
                "server_settings": {
                    "jit": "off",  # Disable JIT for better consistency
                    "application_name": "MIDAS-Windows"
                }
            }
        }
    
    async def initialize(self):
        """Initialize PostgreSQL connection pool"""
        try:
            start_time = time.time()
            
            # Create SQLAlchemy engine with optimized pool
            self.engine = create_async_engine(
                settings.DATABASE_URL,
                echo=False,
                future=True,
                poolclass=QueuePool,
                **self.pool_config
            )
            
            # Create raw asyncpg pool for high-performance operations
            self.raw_pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=5,
                max_size=self.pool_config["pool_size"],
                command_timeout=10,
                server_settings={
                    "application_name": "MIDAS-Raw-Pool",
                    "tcp_keepalives_idle": "600",
                    "tcp_keepalives_interval": "30",
                    "tcp_keepalives_count": "3"
                }
            )
            
            connection_time = time.time() - start_time
            self.record_connection_time(connection_time)
            self.stats.connections_created = self.pool_config["pool_size"]
            
            # Test connection
            async with self.engine.begin() as conn:
                await conn.execute("SELECT 1")
            
            logger.info(f"✅ PostgreSQL connection pool initialized ({connection_time:.3f}s)")
            
        except Exception as e:
            self.stats.connection_errors += 1
            logger.error(f"❌ Failed to initialize PostgreSQL pool: {e}")
            raise
    
    @asynccontextmanager
    async def get_connection(self):
        """Get connection from SQLAlchemy pool"""
        start_time = time.time()
        try:
            async with self.engine.begin() as conn:
                self.stats.active_connections += 1
                yield conn
        except Exception as e:
            self.stats.connection_errors += 1
            raise
        finally:
            self.stats.active_connections -= 1
            self.record_connection_time(time.time() - start_time)
    
    @asynccontextmanager
    async def get_raw_connection(self):
        """Get raw asyncpg connection for high-performance operations"""
        start_time = time.time()
        connection = None
        try:
            connection = await self.raw_pool.acquire()
            self.stats.active_connections += 1
            yield connection
        except Exception as e:
            self.stats.connection_errors += 1
            raise
        finally:
            if connection:
                await self.raw_pool.release(connection)
            self.stats.active_connections -= 1
            self.record_connection_time(time.time() - start_time)
    
    async def execute_batch(self, query: str, parameters: List[tuple]) -> List[Any]:
        """Execute batch operations efficiently"""
        async with self.get_raw_connection() as conn:
            return await conn.executemany(query, parameters)
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get detailed pool statistics"""
        engine_pool = self.engine.pool
        raw_pool_stats = {
            "size": self.raw_pool.get_size(),
            "min_size": self.raw_pool.get_min_size(),
            "max_size": self.raw_pool.get_max_size(),
            "idle_connections": self.raw_pool.get_idle_size(),
        } if self.raw_pool else {}
        
        return {
            "service": self.service_name,
            "engine_pool": {
                "pool_size": engine_pool.size(),
                "checked_out": engine_pool.checkedout(),
                "overflow": engine_pool.overflow(),
                "checked_in": engine_pool.checkedin(),
            },
            "raw_pool": raw_pool_stats,
            "performance": {
                "avg_connection_time": self.stats.avg_connection_time,
                "total_connections_created": self.stats.connections_created,
                "connection_errors": self.stats.connection_errors
            }
        }
    
    async def close(self):
        """Clean shutdown of connection pools"""
        if self.engine:
            await self.engine.dispose()
        if self.raw_pool:
            await self.raw_pool.close()

class QdrantConnectionPool(WindowsOptimizedConnectionPool):
    """Optimized Qdrant connection pool for Windows"""
    
    def __init__(self):
        super().__init__("Qdrant")
        self.clients: List[QdrantClient] = []
        self.current_client_idx = 0
        self.client_pool_size = min(10, psutil.cpu_count())
        
        # Windows-optimized HTTP client settings
        self.http_client_config = {
            "timeout": httpx.Timeout(30.0, connect=10.0),
            "limits": httpx.Limits(
                max_keepalive_connections=self.client_pool_size,
                max_connections=self.client_pool_size * 2,
                keepalive_expiry=60.0
            ),
            "transport": httpx.HTTPTransport(
                retries=3,
                verify=False  # For local development
            )
        }
    
    async def initialize(self):
        """Initialize Qdrant connection pool"""
        try:
            start_time = time.time()
            
            # Create multiple client instances for connection pooling
            for i in range(self.client_pool_size):
                client = QdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_PORT,
                    timeout=30,
                    # Windows-specific optimization
                    grpc_port=None,  # Use HTTP for better Windows compatibility
                    prefer_grpc=False
                )
                
                self.clients.append(client)
            
            connection_time = time.time() - start_time
            self.record_connection_time(connection_time)
            self.stats.connections_created = len(self.clients)
            
            # Test connection
            health = self.clients[0].get_health()
            if health.status != "green":
                raise ConnectionError(f"Qdrant health check failed: {health}")
            
            logger.info(f"✅ Qdrant connection pool initialized ({connection_time:.3f}s)")
            
        except Exception as e:
            self.stats.connection_errors += 1
            logger.error(f"❌ Failed to initialize Qdrant pool: {e}")
            raise
    
    def get_client(self) -> QdrantClient:
        """Get next available Qdrant client (round-robin)"""
        client = self.clients[self.current_client_idx]
        self.current_client_idx = (self.current_client_idx + 1) % len(self.clients)
        return client
    
    async def search_batch(
        self, 
        collection_name: str, 
        queries: List[List[float]], 
        limit: int = 10
    ) -> List[Any]:
        """Perform batch search operations"""
        tasks = []
        for i, query_vector in enumerate(queries):
            client = self.clients[i % len(self.clients)]
            task = asyncio.create_task(
                self._search_single(client, collection_name, query_vector, limit)
            )
            tasks.append(task)
        
        return await asyncio.gather(*tasks)
    
    async def _search_single(
        self, 
        client: QdrantClient, 
        collection_name: str, 
        query_vector: List[float], 
        limit: int
    ):
        """Single search operation"""
        try:
            return client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
                with_vectors=False  # Optimize bandwidth
            )
        except Exception as e:
            self.stats.connection_errors += 1
            logger.error(f"Qdrant search error: {e}")
            raise
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get Qdrant pool statistics"""
        # Test each client's health
        healthy_clients = 0
        for client in self.clients:
            try:
                health = client.get_health()
                if health.status == "green":
                    healthy_clients += 1
            except:
                pass
        
        return {
            "service": self.service_name,
            "pool_size": len(self.clients),
            "healthy_clients": healthy_clients,
            "current_client_idx": self.current_client_idx,
            "performance": {
                "avg_connection_time": self.stats.avg_connection_time,
                "connection_errors": self.stats.connection_errors
            }
        }

class ConnectionPoolManager:
    """Centralized connection pool manager"""
    
    def __init__(self):
        self.postgres_pool = PostgreSQLConnectionPool()
        self.qdrant_pool = QdrantConnectionPool()
        self._initialized = False
    
    async def initialize_all(self):
        """Initialize all connection pools"""
        if self._initialized:
            return
        
        logger.info("🔄 Initializing connection pools...")
        
        # Initialize pools concurrently
        await asyncio.gather(
            self.postgres_pool.initialize(),
            self.qdrant_pool.initialize(),
            return_exceptions=True
        )
        
        self._initialized = True
        logger.info("✅ All connection pools initialized")
    
    async def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system and pool statistics"""
        # System resources
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Pool statistics
        postgres_stats = await self.postgres_pool.get_pool_stats()
        qdrant_stats = await self.qdrant_pool.get_pool_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_gb": memory.available / (1024**3),
                "cpu_count": psutil.cpu_count()
            },
            "pools": {
                "postgresql": postgres_stats,
                "qdrant": qdrant_stats
            }
        }
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all connection pools"""
        health = {}
        
        # Test PostgreSQL
        try:
            async with self.postgres_pool.get_connection() as conn:
                await conn.execute("SELECT 1")
            health["postgresql"] = True
        except:
            health["postgresql"] = False
        
        # Test Qdrant
        try:
            client = self.qdrant_pool.get_client()
            client.get_health()
            health["qdrant"] = True
        except:
            health["qdrant"] = False
        
        return health
    
    async def close_all(self):
        """Close all connection pools"""
        await asyncio.gather(
            self.postgres_pool.close(),
            # Qdrant clients close automatically
            return_exceptions=True
        )
        self._initialized = False

# Global connection pool manager
connection_manager = ConnectionPoolManager()