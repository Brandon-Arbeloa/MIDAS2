"""
MIDAS Query Cache Manager
Caches SQL query results using Redis on Windows
"""

import json
import hashlib
import pickle
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import pandas as pd
import redis
from redis.exceptions import RedisError
import pyarrow as pa
import pyarrow.parquet as pq
from io import BytesIO

logger = logging.getLogger(__name__)

class QueryCacheManager:
    """Manages query result caching with Redis"""
    
    def __init__(self, 
                 redis_host: str = "localhost",
                 redis_port: int = 6379,
                 redis_db: int = 1,
                 default_ttl: int = 3600,
                 max_cache_size_mb: int = 100):
        
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_db = redis_db
        self.default_ttl = default_ttl  # seconds
        self.max_cache_size_mb = max_cache_size_mb
        
        # Initialize Redis connection
        self._init_redis()
        
        # Cache statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0
        }
    
    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=False  # We'll handle encoding ourselves
            )
            
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_host}:{self.redis_port}")
            
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def _generate_cache_key(self, 
                          query: str, 
                          database: str,
                          params: Optional[Dict] = None) -> str:
        """Generate unique cache key for query"""
        # Create a unique key from query components
        key_parts = {
            'query': query.strip().lower(),
            'database': database,
            'params': params or {}
        }
        
        # Hash the key parts
        key_string = json.dumps(key_parts, sort_keys=True)
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()
        
        return f"midas:query_cache:{database}:{key_hash[:16]}"
    
    def _serialize_dataframe(self, df: pd.DataFrame) -> bytes:
        """Serialize DataFrame to bytes using Parquet format"""
        # Use Parquet for efficient serialization
        buffer = BytesIO()
        table = pa.Table.from_pandas(df)
        pq.write_table(table, buffer, compression='snappy')
        return buffer.getvalue()
    
    def _deserialize_dataframe(self, data: bytes) -> pd.DataFrame:
        """Deserialize bytes back to DataFrame"""
        buffer = BytesIO(data)
        table = pq.read_table(buffer)
        return table.to_pandas()
    
    def get(self, 
            query: str, 
            database: str,
            params: Optional[Dict] = None) -> Optional[pd.DataFrame]:
        """Get cached query result"""
        if not self.redis_client:
            return None
        
        cache_key = self._generate_cache_key(query, database, params)
        
        try:
            # Get from cache
            cached_data = self.redis_client.get(cache_key)
            
            if cached_data:
                # Get metadata
                meta_key = f"{cache_key}:meta"
                metadata = self.redis_client.get(meta_key)
                
                if metadata:
                    meta = json.loads(metadata)
                    logger.info(f"Cache hit for query. Cached at: {meta.get('cached_at')}")
                
                # Deserialize DataFrame
                df = self._deserialize_dataframe(cached_data)
                
                self.stats['hits'] += 1
                return df
            else:
                self.stats['misses'] += 1
                return None
                
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats['errors'] += 1
            return None
    
    def set(self, 
            query: str, 
            database: str,
            result: pd.DataFrame,
            params: Optional[Dict] = None,
            ttl: Optional[int] = None) -> bool:
        """Cache query result"""
        if not self.redis_client or result is None:
            return False
        
        cache_key = self._generate_cache_key(query, database, params)
        ttl = ttl or self.default_ttl
        
        try:
            # Check size
            serialized_data = self._serialize_dataframe(result)
            size_mb = len(serialized_data) / (1024 * 1024)
            
            if size_mb > self.max_cache_size_mb:
                logger.warning(f"Result too large to cache: {size_mb:.2f} MB")
                return False
            
            # Store data
            self.redis_client.setex(cache_key, ttl, serialized_data)
            
            # Store metadata
            metadata = {
                'query': query[:200],  # Truncate long queries
                'database': database,
                'row_count': len(result),
                'column_count': len(result.columns),
                'size_bytes': len(serialized_data),
                'cached_at': datetime.now().isoformat(),
                'ttl': ttl
            }
            
            meta_key = f"{cache_key}:meta"
            self.redis_client.setex(meta_key, ttl, json.dumps(metadata))
            
            logger.info(f"Cached query result: {len(result)} rows, {size_mb:.2f} MB")
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self.stats['errors'] += 1
            return False
    
    def invalidate(self, 
                  query: Optional[str] = None, 
                  database: Optional[str] = None) -> int:
        """Invalidate cached queries"""
        if not self.redis_client:
            return 0
        
        invalidated = 0
        
        try:
            if query and database:
                # Invalidate specific query
                cache_key = self._generate_cache_key(query, database)
                if self.redis_client.delete(cache_key, f"{cache_key}:meta"):
                    invalidated = 1
            
            elif database:
                # Invalidate all queries for database
                pattern = f"midas:query_cache:{database}:*"
                for key in self.redis_client.scan_iter(match=pattern):
                    self.redis_client.delete(key)
                    invalidated += 1
            
            else:
                # Invalidate all query cache
                pattern = "midas:query_cache:*"
                for key in self.redis_client.scan_iter(match=pattern):
                    self.redis_client.delete(key)
                    invalidated += 1
            
            logger.info(f"Invalidated {invalidated} cached queries")
            return invalidated
            
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = self.stats.copy()
        
        if self.redis_client:
            try:
                # Get Redis info
                info = self.redis_client.info()
                stats['redis_memory_used'] = info.get('used_memory_human', 'N/A')
                stats['redis_connected_clients'] = info.get('connected_clients', 0)
                
                # Count cached queries
                pattern = "midas:query_cache:*:meta"
                cached_queries = []
                
                for key in self.redis_client.scan_iter(match=pattern):
                    try:
                        meta = json.loads(self.redis_client.get(key))
                        cached_queries.append(meta)
                    except:
                        pass
                
                stats['cached_query_count'] = len(cached_queries)
                stats['total_cache_size_mb'] = sum(
                    q.get('size_bytes', 0) for q in cached_queries
                ) / (1024 * 1024)
                
                # Calculate hit rate
                total_requests = stats['hits'] + stats['misses']
                stats['hit_rate'] = (
                    stats['hits'] / total_requests if total_requests > 0 else 0
                )
                
            except Exception as e:
                logger.error(f"Failed to get cache stats: {e}")
        
        return stats
    
    def get_cached_queries(self, database: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of cached queries"""
        if not self.redis_client:
            return []
        
        cached_queries = []
        
        try:
            if database:
                pattern = f"midas:query_cache:{database}:*:meta"
            else:
                pattern = "midas:query_cache:*:meta"
            
            for key in self.redis_client.scan_iter(match=pattern):
                try:
                    meta = json.loads(self.redis_client.get(key))
                    
                    # Add TTL info
                    ttl = self.redis_client.ttl(key.decode().replace(':meta', ''))
                    meta['remaining_ttl'] = ttl
                    
                    cached_queries.append(meta)
                except:
                    pass
            
            # Sort by cached_at descending
            cached_queries.sort(
                key=lambda x: x.get('cached_at', ''), 
                reverse=True
            )
            
        except Exception as e:
            logger.error(f"Failed to get cached queries: {e}")
        
        return cached_queries
    
    def cleanup_expired(self) -> int:
        """Clean up expired cache entries (Redis does this automatically)"""
        # Redis handles expiration automatically
        # This method is for compatibility
        return 0
    
    def clear_all(self) -> int:
        """Clear all cached queries"""
        return self.invalidate()

class QueryResultPaginator:
    """Handles pagination of large query results"""
    
    def __init__(self, page_size: int = 100):
        self.page_size = page_size
        self._results_cache = {}
    
    def paginate_dataframe(self, 
                          df: pd.DataFrame, 
                          page: int = 1) -> Dict[str, Any]:
        """Paginate DataFrame results"""
        total_rows = len(df)
        total_pages = (total_rows + self.page_size - 1) // self.page_size
        
        # Calculate slice
        start_idx = (page - 1) * self.page_size
        end_idx = min(start_idx + self.page_size, total_rows)
        
        # Get page data
        page_data = df.iloc[start_idx:end_idx]
        
        return {
            'data': page_data,
            'page': page,
            'page_size': self.page_size,
            'total_rows': total_rows,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_prev': page > 1
        }
    
    def cache_result_for_pagination(self, 
                                  result_id: str, 
                                  df: pd.DataFrame,
                                  ttl: int = 600) -> str:
        """Cache result for pagination"""
        # Store in memory cache (in production, use Redis)
        self._results_cache[result_id] = {
            'data': df,
            'cached_at': datetime.now(),
            'ttl': ttl
        }
        
        # Clean old entries
        self._cleanup_old_results()
        
        return result_id
    
    def get_page(self, result_id: str, page: int = 1) -> Optional[Dict[str, Any]]:
        """Get specific page from cached result"""
        if result_id not in self._results_cache:
            return None
        
        cached = self._results_cache[result_id]
        df = cached['data']
        
        return self.paginate_dataframe(df, page)
    
    def _cleanup_old_results(self):
        """Clean up expired results from cache"""
        now = datetime.now()
        expired = []
        
        for result_id, cached in self._results_cache.items():
            age = (now - cached['cached_at']).total_seconds()
            if age > cached['ttl']:
                expired.append(result_id)
        
        for result_id in expired:
            del self._results_cache[result_id]

# Example usage
if __name__ == "__main__":
    # Initialize cache manager
    cache_manager = QueryCacheManager()
    
    # Test with sample data
    test_df = pd.DataFrame({
        'id': range(1, 101),
        'name': [f'Item {i}' for i in range(1, 101)],
        'value': [i * 10 for i in range(1, 101)]
    })
    
    # Cache the result
    query = "SELECT * FROM items"
    database = "test_db"
    
    # Set cache
    cache_manager.set(query, database, test_df)
    
    # Get from cache
    cached_df = cache_manager.get(query, database)
    if cached_df is not None:
        print(f"Retrieved {len(cached_df)} rows from cache")
    
    # Get cache stats
    stats = cache_manager.get_cache_stats()
    print(f"Cache stats: {json.dumps(stats, indent=2)}")
    
    # Test pagination
    paginator = QueryResultPaginator(page_size=25)
    
    for page in range(1, 5):
        page_result = paginator.paginate_dataframe(test_df, page)
        print(f"\nPage {page}: {len(page_result['data'])} rows")
        print(f"Total pages: {page_result['total_pages']}")