import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading
import psutil
import numpy as np
from datetime import datetime, timedelta

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    VectorParams, 
    Distance, 
    HnswConfigDiff,
    OptimizersConfigDiff,
    QuantizationConfig,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    CollectionStatus,
    PayloadSchemaType
)

logger = logging.getLogger(__name__)

@dataclass
class CollectionOptimizationConfig:
    vector_size: int = 1536
    distance_metric: Distance = Distance.COSINE
    hnsw_m: int = 64
    hnsw_ef_construct: int = 256
    max_segment_size: int = 500000
    memmap_threshold: int = 500000
    indexing_threshold: int = 20000
    flush_interval_sec: int = 5
    max_optimization_threads: int = 8
    enable_quantization: bool = True
    quantization_type: ScalarType = ScalarType.INT8

class WindowsQdrantOptimizer:
    def __init__(
        self,
        qdrant_client: QdrantClient,
        max_concurrent_optimizations: int = 4,
        optimization_interval: int = 300,  # 5 minutes
        enable_auto_optimization: bool = True
    ):
        self.client = qdrant_client
        self.max_concurrent_optimizations = max_concurrent_optimizations
        self.optimization_interval = optimization_interval
        self.enable_auto_optimization = enable_auto_optimization
        
        self._optimization_stats = {}
        self._optimization_lock = threading.Lock()
        self._optimization_executor = ThreadPoolExecutor(
            max_workers=max_concurrent_optimizations,
            thread_name_prefix="qdrant_optimizer"
        )
        
        self._auto_optimization_task = None
        if enable_auto_optimization:
            self._start_auto_optimization()
    
    def _start_auto_optimization(self):
        async def auto_optimize():
            while True:
                try:
                    await self.auto_optimize_collections()
                    await asyncio.sleep(self.optimization_interval)
                except Exception as e:
                    logger.error(f"Auto-optimization error: {e}")
                    await asyncio.sleep(60)
        
        self._auto_optimization_task = asyncio.create_task(auto_optimize())
    
    def create_optimized_collection(
        self,
        collection_name: str,
        config: CollectionOptimizationConfig = None
    ) -> bool:
        if config is None:
            config = CollectionOptimizationConfig()
        
        try:
            # Windows-optimized collection configuration
            vectors_config = VectorParams(
                size=config.vector_size,
                distance=config.distance_metric,
                hnsw_config=models.HnswConfig(
                    m=config.hnsw_m,
                    ef_construct=config.hnsw_ef_construct,
                    full_scan_threshold=10000,
                    max_indexing_threads=config.max_optimization_threads,
                    on_disk=False  # Keep in memory for Windows performance
                )
            )
            
            # Optimization configuration
            optimizers_config = OptimizersConfigDiff(
                deleted_threshold=0.2,
                vacuum_min_vector_number=1000,
                default_segment_number=8,
                max_segment_size=config.max_segment_size,
                memmap_threshold=config.memmap_threshold,
                indexing_threshold=config.indexing_threshold,
                flush_interval_sec=config.flush_interval_sec,
                max_optimization_threads=config.max_optimization_threads
            )
            
            # Quantization for memory efficiency on Windows
            quantization_config = None
            if config.enable_quantization:
                quantization_config = QuantizationConfig(
                    scalar=ScalarQuantizationConfig(
                        type=config.quantization_type,
                        quantile=0.99,
                        always_ram=False
                    )
                )
            
            # WAL configuration optimized for Windows
            wal_config = models.WalConfig(
                wal_capacity_mb=512,
                wal_segments_ahead=2
            )
            
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                optimizers_config=optimizers_config,
                wal_config=wal_config,
                quantization_config=quantization_config,
                shard_number=1,  # Single shard for Windows single-node deployment
                replication_factor=1,
                write_consistency_factor=1,
                on_disk_payload=False,  # Keep payload in memory
                hnsw_config=models.HnswConfig(
                    m=config.hnsw_m,
                    ef_construct=config.hnsw_ef_construct,
                    full_scan_threshold=10000,
                    max_indexing_threads=config.max_optimization_threads
                )
            )
            
            logger.info(f"Created optimized collection: {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create optimized collection {collection_name}: {e}")
            return False
    
    def optimize_collection_indexes(self, collection_name: str) -> bool:
        try:
            collection_info = self.client.get_collection(collection_name)
            
            # Check if optimization is needed
            if collection_info.status == CollectionStatus.GREEN:
                logger.info(f"Collection {collection_name} is already optimized")
                return True
            
            # Create payload field indexes for common filtering operations
            common_payload_fields = [
                ("document_id", PayloadSchemaType.TEXT),
                ("chunk_id", PayloadSchemaType.TEXT),
                ("source", PayloadSchemaType.TEXT),
                ("timestamp", PayloadSchemaType.DATETIME),
                ("metadata.category", PayloadSchemaType.TEXT),
                ("metadata.language", PayloadSchemaType.TEXT)
            ]
            
            for field_name, field_type in common_payload_fields:
                try:
                    self.client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field_name,
                        field_schema=field_type
                    )
                    logger.info(f"Created payload index for {field_name} in {collection_name}")
                except Exception as e:
                    # Index might already exist
                    logger.debug(f"Could not create index for {field_name}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to optimize collection indexes {collection_name}: {e}")
            return False
    
    def batch_upsert_optimized(
        self,
        collection_name: str,
        points: List[models.PointStruct],
        batch_size: int = 1000,
        max_retries: int = 3
    ) -> bool:
        try:
            total_points = len(points)
            logger.info(f"Starting batch upsert of {total_points} points to {collection_name}")
            
            # Process in batches for Windows memory management
            for i in range(0, total_points, batch_size):
                batch = points[i:i + batch_size]
                
                for retry in range(max_retries):
                    try:
                        operation_info = self.client.upsert(
                            collection_name=collection_name,
                            wait=False,  # Async for better performance
                            points=batch
                        )
                        
                        logger.info(
                            f"Batch {i//batch_size + 1}: Upserted {len(batch)} points "
                            f"(operation_id: {operation_info.operation_id})"
                        )
                        break
                        
                    except Exception as e:
                        if retry < max_retries - 1:
                            logger.warning(f"Batch upsert retry {retry + 1}: {e}")
                            time.sleep(2 ** retry)  # Exponential backoff
                        else:
                            logger.error(f"Batch upsert failed after {max_retries} retries: {e}")
                            return False
                
                # Memory management for Windows
                if i % (batch_size * 10) == 0:  # Every 10 batches
                    import gc
                    gc.collect()
            
            logger.info(f"Completed batch upsert of {total_points} points")
            return True
            
        except Exception as e:
            logger.error(f"Batch upsert failed: {e}")
            return False
    
    def optimize_search_parameters(self, collection_name: str) -> Dict[str, Any]:
        try:
            collection_info = self.client.get_collection(collection_name)
            vector_count = collection_info.vectors_count or 0
            
            # Dynamic EF parameter based on collection size and Windows performance
            if vector_count < 1000:
                ef = 64
            elif vector_count < 10000:
                ef = 128
            elif vector_count < 100000:
                ef = 256
            else:
                ef = 512
            
            # Windows-optimized search parameters
            search_params = {
                "hnsw_ef": min(ef, vector_count) if vector_count > 0 else 64,
                "exact": False,
                "indexed_only": False
            }
            
            # Memory considerations for Windows
            memory_info = psutil.virtual_memory()
            if memory_info.percent > 80:  # High memory usage
                search_params["hnsw_ef"] = max(32, search_params["hnsw_ef"] // 2)
                logger.warning(f"Reduced search EF due to high memory usage: {search_params['hnsw_ef']}")
            
            return search_params
            
        except Exception as e:
            logger.error(f"Failed to optimize search parameters for {collection_name}: {e}")
            return {"hnsw_ef": 64, "exact": False, "indexed_only": False}
    
    async def parallel_search(
        self,
        collection_name: str,
        query_vectors: List[np.ndarray],
        limit: int = 10,
        search_filter: Optional[models.Filter] = None
    ) -> List[List[models.ScoredPoint]]:
        search_params = self.optimize_search_parameters(collection_name)
        
        async def single_search(query_vector: np.ndarray) -> List[models.ScoredPoint]:
            try:
                results = await asyncio.get_event_loop().run_in_executor(
                    self._optimization_executor,
                    lambda: self.client.search(
                        collection_name=collection_name,
                        query_vector=query_vector.tolist(),
                        query_filter=search_filter,
                        limit=limit,
                        search_params=search_params
                    )
                )
                return results
            except Exception as e:
                logger.error(f"Search failed: {e}")
                return []
        
        # Execute searches in parallel with concurrency limit
        semaphore = asyncio.Semaphore(self.max_concurrent_optimizations)
        
        async def limited_search(query_vector):
            async with semaphore:
                return await single_search(query_vector)
        
        tasks = [limited_search(qv) for qv in query_vectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Search {i} failed: {result}")
                valid_results.append([])
            else:
                valid_results.append(result)
        
        return valid_results
    
    async def auto_optimize_collections(self):
        try:
            collections = self.client.get_collections()
            
            for collection in collections.collections:
                collection_name = collection.name
                
                # Skip if recently optimized
                last_optimized = self._optimization_stats.get(collection_name, {}).get('last_optimized')
                if last_optimized and (datetime.now() - last_optimized).seconds < 3600:  # 1 hour
                    continue
                
                try:
                    # Get collection info
                    info = self.client.get_collection(collection_name)
                    
                    # Check if optimization is needed
                    needs_optimization = (
                        info.status != CollectionStatus.GREEN or
                        info.optimizer_status.get('ok', False) is False
                    )
                    
                    if needs_optimization:
                        logger.info(f"Auto-optimizing collection: {collection_name}")
                        
                        # Run optimization
                        await asyncio.get_event_loop().run_in_executor(
                            self._optimization_executor,
                            lambda: self.optimize_collection_indexes(collection_name)
                        )
                        
                        # Update stats
                        with self._optimization_lock:
                            if collection_name not in self._optimization_stats:
                                self._optimization_stats[collection_name] = {}
                            self._optimization_stats[collection_name]['last_optimized'] = datetime.now()
                            self._optimization_stats[collection_name]['optimization_count'] = \
                                self._optimization_stats[collection_name].get('optimization_count', 0) + 1
                    
                except Exception as e:
                    logger.error(f"Failed to auto-optimize collection {collection_name}: {e}")
                    
        except Exception as e:
            logger.error(f"Auto-optimization task failed: {e}")
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        try:
            collections = self.client.get_collections()
            stats = {
                'total_collections': len(collections.collections),
                'optimization_history': self._optimization_stats.copy(),
                'system_resources': {
                    'cpu_percent': psutil.cpu_percent(),
                    'memory_percent': psutil.virtual_memory().percent,
                    'available_memory_gb': psutil.virtual_memory().available / (1024**3)
                },
                'collection_details': {}
            }
            
            for collection in collections.collections:
                try:
                    info = self.client.get_collection(collection.name)
                    stats['collection_details'][collection.name] = {
                        'status': info.status,
                        'vectors_count': info.vectors_count,
                        'segments_count': info.segments_count,
                        'disk_data_size': info.disk_data_size,
                        'ram_data_size': info.ram_data_size
                    }
                except Exception as e:
                    logger.error(f"Failed to get stats for collection {collection.name}: {e}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get optimization stats: {e}")
            return {'error': str(e)}
    
    def cleanup(self):
        if self._auto_optimization_task:
            self._auto_optimization_task.cancel()
        
        if self._optimization_executor:
            self._optimization_executor.shutdown(wait=True)

# Global optimizer instance
qdrant_optimizer: Optional[WindowsQdrantOptimizer] = None

def initialize_qdrant_optimizer(qdrant_client: QdrantClient) -> WindowsQdrantOptimizer:
    global qdrant_optimizer
    qdrant_optimizer = WindowsQdrantOptimizer(qdrant_client)
    return qdrant_optimizer

def get_qdrant_optimizer() -> WindowsQdrantOptimizer:
    if qdrant_optimizer is None:
        raise RuntimeError("Qdrant optimizer not initialized")
    return qdrant_optimizer