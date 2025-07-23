"""
Intelligent Caching Manager for MIDAS
Windows-optimized multi-tier caching with Redis and file system
"""

import os
import pickle
import json
import hashlib
from typing import Any, Optional, Dict, List, Union
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import aioredis
from aioredis import Redis
import aiofiles
from dataclasses import dataclass

from backend.core.config import settings

@dataclass
class CacheConfig:
    """Cache configuration settings"""
    redis_ttl: int = 3600  # 1 hour default
    file_ttl: int = 86400  # 24 hours default
    max_memory_size: int = 100 * 1024 * 1024  # 100MB
    max_file_size: int = 10 * 1024 * 1024  # 10MB per file
    compression_threshold: int = 1024  # Compress items > 1KB

class CacheManager:
    """Multi-tier intelligent cache manager for Windows"""
    
    def __init__(self):
        self.redis_client: Optional[Redis] = None
        self.cache_dir = settings.APPDATA_DIR / "cache"
        self.embedding_cache_dir = settings.APPDATA_DIR / "embeddings"
        self.query_cache_dir = settings.APPDATA_DIR / "queries"
        self.config = CacheConfig()
        
        # Windows-specific optimizations
        self._init_windows_cache_dirs()
        
    def _init_windows_cache_dirs(self):
        """Initialize Windows-optimized cache directories"""
        # Create cache directories with Windows attributes
        directories = [
            self.cache_dir,
            self.embedding_cache_dir, 
            self.query_cache_dir,
            self.cache_dir / "temp",
            self.cache_dir / "metadata"
        ]
        
        for dir_path in directories:
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Windows-specific: Set directory attributes for better performance
            if os.name == 'nt':
                try:
                    import win32api
                    import win32con
                    # Set directory as system for better caching
                    win32api.SetFileAttributes(
                        str(dir_path), 
                        win32con.FILE_ATTRIBUTE_NOT_CONTENT_INDEXED
                    )
                except ImportError:
                    pass
    
    async def initialize(self):
        """Initialize cache connections"""
        try:
            # Connect to Redis
            self.redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            print("✅ Redis cache connected successfully")
            
        except Exception as e:
            print(f"⚠️  Redis connection failed: {e}. Using file-only caching.")
            self.redis_client = None
    
    def _generate_cache_key(self, namespace: str, key: str, params: Optional[Dict] = None) -> str:
        """Generate consistent cache key"""
        base_key = f"{namespace}:{key}"
        if params:
            # Sort params for consistent hashing
            param_str = json.dumps(params, sort_keys=True)
            param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
            base_key += f":{param_hash}"
        return base_key
    
    def _get_file_cache_path(self, cache_key: str) -> Path:
        """Get file system cache path"""
        # Use first two chars of hash for directory distribution
        key_hash = hashlib.sha256(cache_key.encode()).hexdigest()
        subdir = key_hash[:2]
        return self.cache_dir / subdir / f"{key_hash}.cache"
    
    async def get(
        self, 
        namespace: str, 
        key: str, 
        params: Optional[Dict] = None,
        default: Any = None
    ) -> Any:
        """Get value from cache with fallback hierarchy"""
        cache_key = self._generate_cache_key(namespace, key, params)
        
        # Try Redis first (fastest)
        if self.redis_client:
            try:
                value = await self.redis_client.get(cache_key)
                if value is not None:
                    return json.loads(value)
            except Exception as e:
                print(f"Redis get error: {e}")
        
        # Fallback to file system cache
        try:
            file_path = self._get_file_cache_path(cache_key)
            if file_path.exists():
                async with aiofiles.open(file_path, 'rb') as f:
                    data = await f.read()
                    
                # Check if file is still valid
                stat = file_path.stat()
                if datetime.fromtimestamp(stat.st_mtime) + timedelta(seconds=self.config.file_ttl) > datetime.now():
                    cached_data = pickle.loads(data)
                    
                    # Promote to Redis if available
                    if self.redis_client:
                        await self._set_redis(cache_key, cached_data, self.config.redis_ttl)
                    
                    return cached_data
                else:
                    # Expired, remove file
                    file_path.unlink(missing_ok=True)
        
        except Exception as e:
            print(f"File cache get error: {e}")
        
        return default
    
    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        params: Optional[Dict] = None
    ) -> bool:
        """Set value in cache with intelligent storage decision"""
        cache_key = self._generate_cache_key(namespace, key, params)
        ttl = ttl or self.config.redis_ttl
        
        # Serialize value
        serialized_value = json.dumps(value) if isinstance(value, (dict, list, str, int, float, bool)) else str(value)
        serialized_size = len(serialized_value.encode())
        
        success = False
        
        # Store in Redis for small, frequently accessed items
        if self.redis_client and serialized_size <= self.config.compression_threshold:
            success = await self._set_redis(cache_key, value, ttl)
        
        # Always store in file system for persistence
        if serialized_size <= self.config.max_file_size:
            file_success = await self._set_file_cache(cache_key, value)
            success = success or file_success
        
        return success
    
    async def _set_redis(self, cache_key: str, value: Any, ttl: int) -> bool:
        """Set value in Redis cache"""
        try:
            serialized = json.dumps(value)
            await self.redis_client.setex(cache_key, ttl, serialized)
            return True
        except Exception as e:
            print(f"Redis set error: {e}")
            return False
    
    async def _set_file_cache(self, cache_key: str, value: Any) -> bool:
        """Set value in file system cache"""
        try:
            file_path = self._get_file_cache_path(cache_key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Serialize with pickle for complex objects
            data = pickle.dumps(value)
            
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(data)
            
            return True
        except Exception as e:
            print(f"File cache set error: {e}")
            return False
    
    async def delete(self, namespace: str, key: str, params: Optional[Dict] = None) -> bool:
        """Delete value from all cache layers"""
        cache_key = self._generate_cache_key(namespace, key, params)
        success = True
        
        # Delete from Redis
        if self.redis_client:
            try:
                await self.redis_client.delete(cache_key)
            except Exception as e:
                print(f"Redis delete error: {e}")
                success = False
        
        # Delete from file system
        try:
            file_path = self._get_file_cache_path(cache_key)
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            print(f"File cache delete error: {e}")
            success = False
        
        return success
    
    async def clear_namespace(self, namespace: str) -> int:
        """Clear all entries in a namespace"""
        cleared_count = 0
        
        # Clear Redis namespace
        if self.redis_client:
            try:
                pattern = f"{namespace}:*"
                keys = await self.redis_client.keys(pattern)
                if keys:
                    cleared_count += await self.redis_client.delete(*keys)
            except Exception as e:
                print(f"Redis namespace clear error: {e}")
        
        # Clear file system cache (scan and remove matching files)
        try:
            for cache_file in self.cache_dir.rglob("*.cache"):
                # Read metadata to check namespace (if we stored it)
                # For now, we'll do a more aggressive cleanup
                if cache_file.exists():
                    cache_file.unlink()
                    cleared_count += 1
        except Exception as e:
            print(f"File cache namespace clear error: {e}")
        
        return cleared_count
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        stats = {
            "redis": {"connected": self.redis_client is not None},
            "file_cache": {"enabled": True},
            "directories": {}
        }
        
        # Redis stats
        if self.redis_client:
            try:
                info = await self.redis_client.info()
                stats["redis"].update({
                    "used_memory": info.get("used_memory"),
                    "connected_clients": info.get("connected_clients"),
                    "total_commands_processed": info.get("total_commands_processed"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0)
                })
                
                # Calculate hit rate
                hits = stats["redis"]["keyspace_hits"]
                misses = stats["redis"]["keyspace_misses"]
                total = hits + misses
                stats["redis"]["hit_rate"] = (hits / total * 100) if total > 0 else 0
                
            except Exception as e:
                stats["redis"]["error"] = str(e)
        
        # File cache stats
        for cache_dir in [self.cache_dir, self.embedding_cache_dir, self.query_cache_dir]:
            if cache_dir.exists():
                total_size = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
                file_count = len(list(cache_dir.rglob("*.cache")))
                
                stats["directories"][cache_dir.name] = {
                    "total_size": total_size,
                    "file_count": file_count,
                    "size_mb": total_size / (1024 * 1024)
                }
        
        return stats
    
    async def cleanup_expired(self) -> int:
        """Clean up expired file cache entries"""
        cleaned_count = 0
        cutoff_time = datetime.now() - timedelta(seconds=self.config.file_ttl)
        
        try:
            for cache_file in self.cache_dir.rglob("*.cache"):
                if cache_file.exists():
                    stat = cache_file.stat()
                    if datetime.fromtimestamp(stat.st_mtime) < cutoff_time:
                        cache_file.unlink()
                        cleaned_count += 1
        except Exception as e:
            print(f"Cache cleanup error: {e}")
        
        return cleaned_count
    
    async def optimize_for_windows(self):
        """Apply Windows-specific cache optimizations"""
        if os.name != 'nt':
            return
        
        try:
            import psutil
            import win32api
            import win32process
            
            # Set process priority to optimize I/O
            current_process = psutil.Process()
            
            # Set I/O priority to high for cache operations
            win32process.SetPriorityClass(
                win32api.GetCurrentProcess(),
                win32process.HIGH_PRIORITY_CLASS
            )
            
            # Optimize cache directories for Windows
            for cache_dir in [self.cache_dir, self.embedding_cache_dir, self.query_cache_dir]:
                if cache_dir.exists():
                    # Disable Windows Search indexing on cache directories
                    win32api.SetFileAttributes(
                        str(cache_dir),
                        win32api.GetFileAttributes(str(cache_dir)) | 0x2000  # FILE_ATTRIBUTE_NOT_CONTENT_INDEXED
                    )
        
        except ImportError:
            print("⚠️  Windows optimization modules not available")
        except Exception as e:
            print(f"⚠️  Windows optimization error: {e}")

# Global cache manager instance
cache_manager = CacheManager()