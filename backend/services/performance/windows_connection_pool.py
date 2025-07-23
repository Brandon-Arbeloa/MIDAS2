import asyncio
import logging
import psutil
import threading
from typing import Dict, Any, Optional, List, Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed

import asyncpg
import psycopg2
from psycopg2 import pool as pg_pool
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
import redis
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

logger = logging.getLogger(__name__)

@dataclass
class ConnectionMetrics:
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    failed_connections: int = 0
    avg_response_time: float = 0.0
    last_health_check: datetime = None
    memory_usage_mb: float = 0.0

class WindowsPostgreSQLConnectionPool:
    def __init__(
        self,
        database_url: str,
        min_connections: int = 5,
        max_connections: int = 50,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        windows_optimizations: bool = True
    ):
        self.database_url = database_url
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.pool_timeout = pool_timeout
        self.windows_optimizations = windows_optimizations
        
        # Windows-specific connection parameters
        connect_args = {
            "connect_timeout": 10,
            "application_name": "MIDAS_RAG_System",
            "options": "-c statement_timeout=30s -c idle_in_transaction_session_timeout=60s"
        }
        
        if windows_optimizations:
            connect_args.update({
                "keepalives_idle": "600",
                "keepalives_interval": "30",
                "keepalives_count": "3",
                "tcp_user_timeout": "30000"
            })
        
        self.engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=min_connections,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            connect_args=connect_args,
            echo=False
        )
        
        # Add connection event listeners for monitoring
        event.listen(self.engine, "connect", self._on_connect)
        event.listen(self.engine, "checkout", self._on_checkout)
        event.listen(self.engine, "checkin", self._on_checkin)
        
        self.SessionLocal = sessionmaker(
            autocommit=False, 
            autoflush=False, 
            bind=self.engine
        )
        
        self.metrics = ConnectionMetrics()
        self._connection_times = []
        self._lock = threading.Lock()
        
        # Async pool for high-performance operations
        self._async_pool = None
        self._initialize_async_pool()
    
    async def _initialize_async_pool(self):
        try:
            self._async_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self.min_connections,
                max_size=self.max_connections,
                max_queries=50000,
                max_inactive_connection_lifetime=3600,
                command_timeout=30,
                server_settings={
                    'application_name': 'MIDAS_RAG_System_Async',
                    'tcp_keepalives_idle': '600',
                    'tcp_keepalives_interval': '30',
                    'tcp_keepalives_count': '3'
                }
            )
        except Exception as e:
            logger.error(f"Failed to create async pool: {e}")
    
    def _on_connect(self, dbapi_connection, connection_record):
        with self._lock:
            self.metrics.total_connections += 1
    
    def _on_checkout(self, dbapi_connection, connection_record, connection_proxy):
        with self._lock:
            self.metrics.active_connections += 1
            self.metrics.idle_connections = max(0, self.metrics.idle_connections - 1)
    
    def _on_checkin(self, dbapi_connection, connection_record):
        with self._lock:
            self.metrics.active_connections = max(0, self.metrics.active_connections - 1)
            self.metrics.idle_connections += 1
    
    @contextmanager
    def get_db_session(self):
        start_time = time.time()
        session = None
        try:
            session = self.SessionLocal()
            yield session
            session.commit()
        except Exception as e:
            if session:
                session.rollback()
            with self._lock:
                self.metrics.failed_connections += 1
            raise
        finally:
            if session:
                session.close()
            
            # Update metrics
            response_time = time.time() - start_time
            with self._lock:
                self._connection_times.append(response_time)
                if len(self._connection_times) > 100:
                    self._connection_times = self._connection_times[-100:]
                
                if self._connection_times:
                    self.metrics.avg_response_time = sum(self._connection_times) / len(self._connection_times)
    
    @asynccontextmanager
    async def get_async_connection(self):
        if not self._async_pool:
            await self._initialize_async_pool()
        
        start_time = time.time()
        connection = None
        try:
            connection = await self._async_pool.acquire(timeout=self.pool_timeout)
            yield connection
        except Exception as e:
            with self._lock:
                self.metrics.failed_connections += 1
            raise
        finally:
            if connection:
                await self._async_pool.release(connection)
            
            response_time = time.time() - start_time
            with self._lock:
                self._connection_times.append(response_time)
                if len(self._connection_times) > 100:
                    self._connection_times = self._connection_times[-100:]
    
    async def execute_batch_queries(self, queries: List[str]) -> List[Any]:
        async with self.get_async_connection() as conn:
            results = []
            async with conn.transaction():
                for query in queries:
                    result = await conn.fetch(query)
                    results.append(result)
            return results
    
    def get_pool_status(self) -> Dict[str, Any]:
        pool = self.engine.pool
        return {
            'size': pool.size(),
            'checked_in': pool.checkedin(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow(),
            'total': pool.size() + pool.overflow()
        }
    
    async def health_check(self) -> bool:
        try:
            async with self.get_async_connection() as conn:
                await conn.fetchval("SELECT 1")
            
            self.metrics.last_health_check = datetime.now()
            return True
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False
    
    def cleanup(self):
        if self._async_pool:
            asyncio.create_task(self._async_pool.close())
        self.engine.dispose()

class WindowsQdrantConnectionPool:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        prefer_grpc: bool = False,
        timeout: int = 30,
        max_retries: int = 3,
        pool_size: int = 10,
        windows_optimizations: bool = True
    ):
        self.host = host
        self.port = port
        self.grpc_port = grpc_port
        self.prefer_grpc = prefer_grpc
        self.timeout = timeout
        self.max_retries = max_retries
        self.pool_size = pool_size
        
        self._clients: List[QdrantClient] = []
        self._client_index = 0
        self._lock = threading.Lock()
        self.metrics = ConnectionMetrics()
        
        self._initialize_client_pool()
    
    def _initialize_client_pool(self):
        for i in range(self.pool_size):
            try:
                if self.prefer_grpc:
                    client = QdrantClient(
                        host=self.host,
                        grpc_port=self.grpc_port,
                        prefer_grpc=True,
                        timeout=self.timeout
                    )
                else:
                    client = QdrantClient(
                        host=self.host,
                        port=self.port,
                        timeout=self.timeout
                    )
                
                self._clients.append(client)
                self.metrics.total_connections += 1
            except Exception as e:
                logger.error(f"Failed to create Qdrant client {i}: {e}")
                self.metrics.failed_connections += 1
    
    def get_client(self) -> QdrantClient:
        with self._lock:
            if not self._clients:
                raise RuntimeError("No available Qdrant clients")
            
            client = self._clients[self._client_index % len(self._clients)]
            self._client_index = (self._client_index + 1) % len(self._clients)
            self.metrics.active_connections += 1
            return client
    
    def release_client(self):
        with self._lock:
            self.metrics.active_connections = max(0, self.metrics.active_connections - 1)
            self.metrics.idle_connections += 1
    
    @contextmanager
    def get_qdrant_client(self):
        start_time = time.time()
        client = None
        try:
            client = self.get_client()
            yield client
        except Exception as e:
            with self._lock:
                self.metrics.failed_connections += 1
            raise
        finally:
            if client:
                self.release_client()
            
            response_time = time.time() - start_time
            with self._lock:
                if not hasattr(self, '_response_times'):
                    self._response_times = []
                self._response_times.append(response_time)
                if len(self._response_times) > 100:
                    self._response_times = self._response_times[-100:]
                
                if self._response_times:
                    self.metrics.avg_response_time = sum(self._response_times) / len(self._response_times)
    
    async def batch_operations(self, operations: List[Callable]) -> List[Any]:
        with ThreadPoolExecutor(max_workers=min(len(operations), self.pool_size)) as executor:
            futures = []
            
            for operation in operations:
                future = executor.submit(operation)
                futures.append(future)
            
            results = []
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=self.timeout)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Batch operation failed: {e}")
                    results.append(None)
            
            return results
    
    async def health_check(self) -> bool:
        try:
            with self.get_qdrant_client() as client:
                collections = client.get_collections()
                self.metrics.last_health_check = datetime.now()
                return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False

class WindowsRedisConnectionPool:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 50,
        socket_keepalive_options: Dict = None,
        health_check_interval: int = 30
    ):
        socket_keepalive_options = socket_keepalive_options or {
            'TCP_KEEPIDLE': 600,
            'TCP_KEEPINTVL': 30,
            'TCP_KEEPCNT': 3,
        }
        
        self.connection_pool = redis.ConnectionPool.from_url(
            redis_url,
            max_connections=max_connections,
            socket_keepalive_options=socket_keepalive_options,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=health_check_interval
        )
        
        self.client = redis.Redis(connection_pool=self.connection_pool)
        self.metrics = ConnectionMetrics()
    
    @contextmanager
    def get_redis_client(self):
        start_time = time.time()
        try:
            yield self.client
            self.metrics.active_connections += 1
        except Exception as e:
            self.metrics.failed_connections += 1
            raise
        finally:
            response_time = time.time() - start_time
            if not hasattr(self, '_response_times'):
                self._response_times = []
            self._response_times.append(response_time)
            if len(self._response_times) > 100:
                self._response_times = self._response_times[-100:]
            
            if self._response_times:
                self.metrics.avg_response_time = sum(self._response_times) / len(self._response_times)
    
    async def health_check(self) -> bool:
        try:
            with self.get_redis_client() as client:
                result = client.ping()
                self.metrics.last_health_check = datetime.now()
                return result
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

class WindowsConnectionManager:
    def __init__(
        self,
        database_url: str,
        redis_url: str = "redis://localhost:6379",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        enable_monitoring: bool = True
    ):
        self.postgres_pool = WindowsPostgreSQLConnectionPool(database_url)
        self.qdrant_pool = WindowsQdrantConnectionPool(qdrant_host, qdrant_port)
        self.redis_pool = WindowsRedisConnectionPool(redis_url)
        
        self.enable_monitoring = enable_monitoring
        self._monitoring_task = None
        
        if enable_monitoring:
            self._start_monitoring()
    
    def _start_monitoring(self):
        async def monitor():
            while True:
                try:
                    await self._update_metrics()
                    await asyncio.sleep(60)
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")
                    await asyncio.sleep(60)
        
        self._monitoring_task = asyncio.create_task(monitor())
    
    async def _update_metrics(self):
        # Update memory usage
        process = psutil.Process()
        memory_info = process.memory_info()
        
        self.postgres_pool.metrics.memory_usage_mb = memory_info.rss / 1024 / 1024
        self.qdrant_pool.metrics.memory_usage_mb = memory_info.rss / 1024 / 1024
        self.redis_pool.metrics.memory_usage_mb = memory_info.rss / 1024 / 1024
        
        # Force garbage collection if memory usage is high
        if memory_info.rss > 1024 * 1024 * 1024:  # 1GB
            gc.collect()
    
    def get_db_session(self):
        return self.postgres_pool.get_db_session()
    
    def get_async_db_connection(self):
        return self.postgres_pool.get_async_connection()
    
    def get_qdrant_client(self):
        return self.qdrant_pool.get_qdrant_client()
    
    def get_redis_client(self):
        return self.redis_pool.get_redis_client()
    
    async def health_check_all(self) -> Dict[str, bool]:
        postgres_healthy = await self.postgres_pool.health_check()
        qdrant_healthy = await self.qdrant_pool.health_check()
        redis_healthy = await self.redis_pool.health_check()
        
        return {
            'postgresql': postgres_healthy,
            'qdrant': qdrant_healthy,
            'redis': redis_healthy,
            'overall': all([postgres_healthy, qdrant_healthy, redis_healthy])
        }
    
    def get_all_metrics(self) -> Dict[str, Dict]:
        return {
            'postgresql': {
                'metrics': self.postgres_pool.metrics.__dict__,
                'pool_status': self.postgres_pool.get_pool_status()
            },
            'qdrant': self.qdrant_pool.metrics.__dict__,
            'redis': self.redis_pool.metrics.__dict__,
            'system': {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:').percent
            }
        }
    
    def cleanup(self):
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
        self.postgres_pool.cleanup()
        # Qdrant and Redis pools will be cleaned up automatically


# Global connection manager instance
connection_manager: Optional[WindowsConnectionManager] = None

def initialize_connection_manager(
    database_url: str,
    redis_url: str = "redis://localhost:6379",
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333
):
    global connection_manager
    connection_manager = WindowsConnectionManager(
        database_url=database_url,
        redis_url=redis_url,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port
    )
    return connection_manager

def get_connection_manager() -> WindowsConnectionManager:
    if connection_manager is None:
        raise RuntimeError("Connection manager not initialized")
    return connection_manager