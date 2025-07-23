import redis
import json
import pickle
import hashlib
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
from functools import wraps
import numpy as np
from redis.connection import ConnectionPool
from redis.retry import Retry
from redis.backoff import ExponentialBackoff
import gc
import psutil
import os

logger = logging.getLogger(__name__)

class WindowsOptimizedCacheManager:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 50,
        socket_keepalive_options: Dict = None,
        socket_connect_timeout: int = 5,
        socket_timeout: int = 5,
        retry_on_timeout: bool = True,
        health_check_interval: int = 30,
        max_memory_usage_percent: int = 80
    ):
        socket_keepalive_options = socket_keepalive_options or {
            'TCP_KEEPIDLE': 600,
            'TCP_KEEPINTVL': 30,
            'TCP_KEEPCNT': 3,
        }
        
        self.connection_pool = ConnectionPool.from_url(
            redis_url,
            max_connections=max_connections,
            socket_keepalive_options=socket_keepalive_options,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            retry=Retry(ExponentialBackoff(), retries=3),
            health_check_interval=health_check_interval
        )
        
        self.client = redis.Redis(
            connection_pool=self.connection_pool,
            decode_responses=False
        )
        
        self.max_memory_usage_percent = max_memory_usage_percent
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'memory_cleanups': 0
        }
        
        self._initialize_cache_keys()
    
    def _initialize_cache_keys(self):
        self.QUERY_CACHE_PREFIX = "midas:query:"
        self.EMBEDDING_CACHE_PREFIX = "midas:embedding:"
        self.DOCUMENT_CACHE_PREFIX = "midas:document:"
        self.SEARCH_RESULT_PREFIX = "midas:search:"
        self.USER_SESSION_PREFIX = "midas:session:"
        self.ANALYTICS_PREFIX = "midas:analytics:"
    
    def _get_cache_key(self, prefix: str, identifier: str) -> str:
        if isinstance(identifier, dict):
            identifier = json.dumps(identifier, sort_keys=True)
        
        key_hash = hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return f"{prefix}{key_hash}"
    
    def _serialize_data(self, data: Any) -> bytes:
        if isinstance(data, (str, int, float)):
            return json.dumps(data).encode()
        elif isinstance(data, np.ndarray):
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        elif isinstance(data, (dict, list)):
            return json.dumps(data, default=str).encode()
        else:
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    
    def _deserialize_data(self, data: bytes) -> Any:
        try:
            return json.loads(data.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return pickle.loads(data)
    
    def _check_memory_usage(self):
        memory = psutil.virtual_memory()
        if memory.percent > self.max_memory_usage_percent:
            self._cleanup_cache()
            gc.collect()
            self._cache_stats['memory_cleanups'] += 1
    
    def _cleanup_cache(self):
        try:
            info = self.client.info('memory')
            used_memory = info.get('used_memory', 0)
            max_memory = info.get('maxmemory', 0)
            
            if max_memory > 0 and used_memory > (max_memory * 0.8):
                logger.info("Redis memory usage high, cleaning up old entries")
                
                for prefix in [self.QUERY_CACHE_PREFIX, self.SEARCH_RESULT_PREFIX]:
                    keys = self.client.keys(f"{prefix}*")
                    if keys:
                        oldest_keys = sorted(keys, 
                                           key=lambda k: self.client.ttl(k))[:len(keys)//4]
                        if oldest_keys:
                            self.client.delete(*oldest_keys)
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
    
    async def get(self, cache_type: str, key: str) -> Optional[Any]:
        try:
            cache_key = self._get_cache_key(cache_type, key)
            data = self.client.get(cache_key)
            
            if data is not None:
                self._cache_stats['hits'] += 1
                return self._deserialize_data(data)
            else:
                self._cache_stats['misses'] += 1
                return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self._cache_stats['misses'] += 1
            return None
    
    async def set(
        self, 
        cache_type: str, 
        key: str, 
        value: Any, 
        ttl: int = 3600
    ) -> bool:
        try:
            self._check_memory_usage()
            
            cache_key = self._get_cache_key(cache_type, key)
            serialized_data = self._serialize_data(value)
            
            result = self.client.setex(cache_key, ttl, serialized_data)
            if result:
                self._cache_stats['sets'] += 1
            return result
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def delete(self, cache_type: str, key: str) -> bool:
        try:
            cache_key = self._get_cache_key(cache_type, key)
            result = self.client.delete(cache_key)
            if result:
                self._cache_stats['deletes'] += 1
            return bool(result)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    async def get_many(self, cache_type: str, keys: List[str]) -> Dict[str, Any]:
        try:
            cache_keys = [self._get_cache_key(cache_type, key) for key in keys]
            values = self.client.mget(cache_keys)
            
            result = {}
            for i, (original_key, value) in enumerate(zip(keys, values)):
                if value is not None:
                    result[original_key] = self._deserialize_data(value)
                    self._cache_stats['hits'] += 1
                else:
                    self._cache_stats['misses'] += 1
            
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            return {}
    
    async def set_many(
        self, 
        cache_type: str, 
        data: Dict[str, Any], 
        ttl: int = 3600
    ) -> bool:
        try:
            self._check_memory_usage()
            
            pipe = self.client.pipeline()
            for key, value in data.items():
                cache_key = self._get_cache_key(cache_type, key)
                serialized_data = self._serialize_data(value)
                pipe.setex(cache_key, ttl, serialized_data)
            
            results = pipe.execute()
            successful = sum(1 for r in results if r)
            self._cache_stats['sets'] += successful
            
            return successful == len(data)
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            return False
    
    async def cache_query_result(
        self, 
        query: str, 
        result: Any, 
        ttl: int = 1800
    ) -> bool:
        return await self.set(self.QUERY_CACHE_PREFIX, query, result, ttl)
    
    async def get_cached_query(self, query: str) -> Optional[Any]:
        return await self.get(self.QUERY_CACHE_PREFIX, query)
    
    async def cache_embeddings(
        self, 
        text_chunks: List[str], 
        embeddings: List[np.ndarray], 
        ttl: int = 7200
    ) -> bool:
        embedding_data = {}
        for text, embedding in zip(text_chunks, embeddings):
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            embedding_data[text_hash] = embedding
        
        return await self.set_many(self.EMBEDDING_CACHE_PREFIX, embedding_data, ttl)
    
    async def get_cached_embeddings(self, text_chunks: List[str]) -> Dict[str, np.ndarray]:
        text_hashes = [hashlib.sha256(text.encode()).hexdigest() for text in text_chunks]
        cached_embeddings = await self.get_many(self.EMBEDDING_CACHE_PREFIX, text_hashes)
        
        result = {}
        for text, text_hash in zip(text_chunks, text_hashes):
            if text_hash in cached_embeddings:
                result[text] = cached_embeddings[text_hash]
        
        return result
    
    async def cache_search_results(
        self, 
        query: str, 
        filters: Dict, 
        results: List[Dict], 
        ttl: int = 900
    ) -> bool:
        search_key = json.dumps({
            'query': query,
            'filters': filters
        }, sort_keys=True)
        
        return await self.set(self.SEARCH_RESULT_PREFIX, search_key, results, ttl)
    
    async def get_cached_search_results(
        self, 
        query: str, 
        filters: Dict
    ) -> Optional[List[Dict]]:
        search_key = json.dumps({
            'query': query,
            'filters': filters
        }, sort_keys=True)
        
        return await self.get(self.SEARCH_RESULT_PREFIX, search_key)
    
    async def cache_document_metadata(
        self, 
        document_id: str, 
        metadata: Dict, 
        ttl: int = 3600
    ) -> bool:
        return await self.set(self.DOCUMENT_CACHE_PREFIX, document_id, metadata, ttl)
    
    async def get_cached_document_metadata(self, document_id: str) -> Optional[Dict]:
        return await self.get(self.DOCUMENT_CACHE_PREFIX, document_id)
    
    async def invalidate_document_cache(self, document_id: str) -> bool:
        tasks = [
            self.delete(self.DOCUMENT_CACHE_PREFIX, document_id),
            self.delete_pattern(self.EMBEDDING_CACHE_PREFIX, f"*{document_id}*"),
            self.delete_pattern(self.SEARCH_RESULT_PREFIX, "*")
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return all(r is True or not isinstance(r, Exception) for r in results)
    
    async def delete_pattern(self, cache_type: str, pattern: str) -> bool:
        try:
            full_pattern = cache_type + pattern
            keys = self.client.keys(full_pattern)
            if keys:
                result = self.client.delete(*keys)
                self._cache_stats['deletes'] += result
                return True
            return True
        except Exception as e:
            logger.error(f"Cache delete pattern error: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        try:
            redis_info = self.client.info()
            return {
                'redis_stats': {
                    'connected_clients': redis_info.get('connected_clients', 0),
                    'used_memory_human': redis_info.get('used_memory_human', '0B'),
                    'used_memory_peak_human': redis_info.get('used_memory_peak_human', '0B'),
                    'keyspace_hits': redis_info.get('keyspace_hits', 0),
                    'keyspace_misses': redis_info.get('keyspace_misses', 0),
                },
                'midas_cache_stats': self._cache_stats,
                'cache_prefixes': {
                    'queries': len(self.client.keys(f"{self.QUERY_CACHE_PREFIX}*")),
                    'embeddings': len(self.client.keys(f"{self.EMBEDDING_CACHE_PREFIX}*")),
                    'documents': len(self.client.keys(f"{self.DOCUMENT_CACHE_PREFIX}*")),
                    'search_results': len(self.client.keys(f"{self.SEARCH_RESULT_PREFIX}*")),
                }
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}
    
    async def health_check(self) -> bool:
        try:
            result = self.client.ping()
            return result
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return False
    
    def __del__(self):
        if hasattr(self, 'connection_pool'):
            self.connection_pool.disconnect()


def cache_result(
    cache_type: str,
    ttl: int = 3600,
    key_func: Optional[Callable] = None
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not hasattr(wrapper, '_cache_manager'):
                wrapper._cache_manager = WindowsOptimizedCacheManager()
            
            cache_manager = wrapper._cache_manager
            
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            cached_result = await cache_manager.get(cache_type, cache_key)
            if cached_result is not None:
                return cached_result
            
            result = await func(*args, **kwargs)
            
            if result is not None:
                await cache_manager.set(cache_type, cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


cache_manager = WindowsOptimizedCacheManager()