import os
import multiprocessing as mp
import threading
import asyncio
import logging
import time
import gc
import psutil
from typing import List, Dict, Any, Callable, Optional, Union, Iterator, Tuple
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from queue import Queue, Empty
from datetime import datetime
import numpy as np
import pickle
import tempfile
import mmap
from functools import partial
from pathlib import Path

# Windows-specific imports
import ctypes
from ctypes import wintypes
import win32process
import win32api

logger = logging.getLogger(__name__)

@dataclass
class BatchProcessingConfig:
    max_workers: int = None
    batch_size: int = 100
    use_multiprocessing: bool = True
    memory_limit_mb: int = 8192  # 8GB default
    temp_dir: str = None
    enable_memory_mapping: bool = True
    process_priority: str = "normal"  # low, normal, high
    cpu_affinity_enabled: bool = True

class WindowsProcessManager:
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32
        self.psapi = ctypes.windll.psapi
        
        # Windows priority classes
        self.priority_classes = {
            'idle': 0x00000040,
            'below_normal': 0x00004000,
            'normal': 0x00000020,
            'above_normal': 0x00008000,
            'high': 0x00000080,
            'realtime': 0x00000100
        }
    
    def set_process_priority(self, priority: str = "normal"):
        try:
            handle = win32api.GetCurrentProcess()
            priority_class = self.priority_classes.get(priority, self.priority_classes['normal'])
            win32process.SetPriorityClass(handle, priority_class)
            logger.info(f"Set process priority to {priority}")
        except Exception as e:
            logger.warning(f"Failed to set process priority: {e}")
    
    def set_cpu_affinity(self, cpu_list: List[int] = None):
        try:
            if cpu_list is None:
                cpu_count = psutil.cpu_count()
                cpu_list = list(range(min(cpu_count, 8)))  # Use up to 8 CPUs
            
            process = psutil.Process()
            process.cpu_affinity(cpu_list)
            logger.info(f"Set CPU affinity to cores: {cpu_list}")
        except Exception as e:
            logger.warning(f"Failed to set CPU affinity: {e}")
    
    def get_memory_info(self) -> Dict[str, float]:
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()
            
            return {
                'process_memory_mb': memory_info.rss / 1024 / 1024,
                'process_memory_percent': process.memory_percent(),
                'system_memory_percent': system_memory.percent,
                'available_memory_mb': system_memory.available / 1024 / 1024
            }
        except Exception as e:
            logger.error(f"Failed to get memory info: {e}")
            return {}

class WindowsMemoryMappedArray:
    def __init__(self, shape: Tuple, dtype: np.dtype = np.float32, mode: str = 'w+'):
        self.shape = shape
        self.dtype = dtype
        self.mode = mode
        self.size = np.prod(shape) * np.dtype(dtype).itemsize
        
        # Create temporary file for memory mapping
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.write(b'\0' * self.size)
        self.temp_file.flush()
        
        # Create memory map
        self.mmap = mmap.mmap(
            self.temp_file.fileno(), 
            self.size,
            access=mmap.ACCESS_WRITE
        )
        
        # Create numpy array from memory map
        self.array = np.frombuffer(self.mmap, dtype=dtype).reshape(shape)
    
    def __getitem__(self, key):
        return self.array[key]
    
    def __setitem__(self, key, value):
        self.array[key] = value
    
    def close(self):
        if hasattr(self, 'mmap'):
            self.mmap.close()
        if hasattr(self, 'temp_file'):
            self.temp_file.close()
            try:
                os.unlink(self.temp_file.name)
            except:
                pass
    
    def __del__(self):
        self.close()

class WindowsBatchProcessor:
    def __init__(self, config: BatchProcessingConfig = None):
        self.config = config or BatchProcessingConfig()
        self.process_manager = WindowsProcessManager()
        
        # Set up Windows-specific optimizations
        self._setup_windows_optimizations()
        
        # Initialize executors
        self.max_workers = self.config.max_workers or min(32, (os.cpu_count() or 1) + 4)
        self.process_executor = None
        self.thread_executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="batch_processor"
        )
        
        # Memory management
        self.memory_monitor = threading.Thread(
            target=self._monitor_memory,
            daemon=True
        )
        self.memory_monitor.start()
        
        # Performance metrics
        self._reset_metrics()
    
    def _setup_windows_optimizations(self):
        # Set process priority
        self.process_manager.set_process_priority(self.config.process_priority)
        
        # Set CPU affinity if enabled
        if self.config.cpu_affinity_enabled:
            self.process_manager.set_cpu_affinity()
    
    def _reset_metrics(self):
        self.metrics = {
            'total_items_processed': 0,
            'total_batches': 0,
            'total_processing_time': 0.0,
            'average_batch_time': 0.0,
            'memory_usage_peak_mb': 0.0,
            'errors': 0,
            'started_at': datetime.now()
        }
    
    def _monitor_memory(self):
        while True:
            try:
                memory_info = self.process_manager.get_memory_info()
                current_usage = memory_info.get('process_memory_mb', 0)
                
                if current_usage > self.metrics['memory_usage_peak_mb']:
                    self.metrics['memory_usage_peak_mb'] = current_usage
                
                # Trigger garbage collection if memory usage is high
                if current_usage > self.config.memory_limit_mb * 0.8:
                    logger.warning(f"High memory usage detected: {current_usage:.1f}MB")
                    gc.collect()
                
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                time.sleep(60)
    
    def _worker_initializer(self):
        # Initialize worker process with Windows optimizations
        self.process_manager.set_process_priority(self.config.process_priority)
        if self.config.cpu_affinity_enabled:
            self.process_manager.set_cpu_affinity()
    
    def create_batches(self, items: List[Any], batch_size: int = None) -> Iterator[List[Any]]:
        batch_size = batch_size or self.config.batch_size
        for i in range(0, len(items), batch_size):
            yield items[i:i + batch_size]
    
    def process_batch_sync(
        self,
        items: List[Any],
        processing_function: Callable,
        batch_size: int = None,
        use_multiprocessing: bool = None
    ) -> List[Any]:
        batch_size = batch_size or self.config.batch_size
        use_multiprocessing = use_multiprocessing if use_multiprocessing is not None else self.config.use_multiprocessing
        
        start_time = time.time()
        results = []
        batches = list(self.create_batches(items, batch_size))
        
        logger.info(f"Processing {len(items)} items in {len(batches)} batches using {'multiprocessing' if use_multiprocessing else 'threading'}")
        
        if use_multiprocessing and len(batches) > 1:
            # Use process pool for CPU-intensive tasks
            if not self.process_executor:
                self.process_executor = ProcessPoolExecutor(
                    max_workers=self.max_workers,
                    initializer=self._worker_initializer,
                    mp_context=mp.get_context('spawn')  # Windows-compatible
                )
            
            futures = []
            for batch in batches:
                future = self.process_executor.submit(processing_function, batch)
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    batch_result = future.result(timeout=300)  # 5 minute timeout
                    if isinstance(batch_result, list):
                        results.extend(batch_result)
                    else:
                        results.append(batch_result)
                except Exception as e:
                    logger.error(f"Batch processing error: {e}")
                    self.metrics['errors'] += 1
        
        else:
            # Use thread pool for I/O-intensive tasks or small batches
            futures = []
            for batch in batches:
                future = self.thread_executor.submit(processing_function, batch)
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    batch_result = future.result(timeout=300)
                    if isinstance(batch_result, list):
                        results.extend(batch_result)
                    else:
                        results.append(batch_result)
                except Exception as e:
                    logger.error(f"Batch processing error: {e}")
                    self.metrics['errors'] += 1
        
        # Update metrics
        processing_time = time.time() - start_time
        self.metrics['total_items_processed'] += len(items)
        self.metrics['total_batches'] += len(batches)
        self.metrics['total_processing_time'] += processing_time
        self.metrics['average_batch_time'] = self.metrics['total_processing_time'] / self.metrics['total_batches']
        
        logger.info(f"Completed processing {len(items)} items in {processing_time:.2f} seconds")
        return results
    
    async def process_batch_async(
        self,
        items: List[Any],
        processing_function: Callable,
        batch_size: int = None,
        max_concurrent_batches: int = None
    ) -> List[Any]:
        batch_size = batch_size or self.config.batch_size
        max_concurrent_batches = max_concurrent_batches or self.max_workers
        
        start_time = time.time()
        results = []
        batches = list(self.create_batches(items, batch_size))
        
        logger.info(f"Processing {len(items)} items in {len(batches)} batches asynchronously")
        
        # Semaphore to limit concurrent batch processing
        semaphore = asyncio.Semaphore(max_concurrent_batches)
        
        async def process_single_batch(batch):
            async with semaphore:
                try:
                    # Run in executor for CPU-bound tasks
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        self.thread_executor,
                        processing_function,
                        batch
                    )
                    return result
                except Exception as e:
                    logger.error(f"Async batch processing error: {e}")
                    self.metrics['errors'] += 1
                    return None
        
        # Process all batches concurrently
        tasks = [process_single_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results
        for batch_result in batch_results:
            if batch_result is not None and not isinstance(batch_result, Exception):
                if isinstance(batch_result, list):
                    results.extend(batch_result)
                else:
                    results.append(batch_result)
        
        # Update metrics
        processing_time = time.time() - start_time
        self.metrics['total_items_processed'] += len(items)
        self.metrics['total_batches'] += len(batches)
        self.metrics['total_processing_time'] += processing_time
        self.metrics['average_batch_time'] = self.metrics['total_processing_time'] / self.metrics['total_batches']
        
        logger.info(f"Completed async processing {len(items)} items in {processing_time:.2f} seconds")
        return results
    
    def process_embeddings_batch(
        self,
        texts: List[str],
        embedding_function: Callable[[List[str]], List[np.ndarray]],
        batch_size: int = None,
        use_memory_mapping: bool = None
    ) -> List[np.ndarray]:
        batch_size = batch_size or self.config.batch_size
        use_memory_mapping = use_memory_mapping if use_memory_mapping is not None else self.config.enable_memory_mapping
        
        if not texts:
            return []
        
        # Pre-allocate memory-mapped array if enabled
        embeddings_array = None
        if use_memory_mapping and len(texts) > 1000:  # Use memory mapping for large datasets
            try:
                # Estimate embedding dimension (assume 1536 for OpenAI embeddings)
                sample_embedding = embedding_function([texts[0]])[0]
                embedding_dim = len(sample_embedding)
                
                embeddings_array = WindowsMemoryMappedArray(
                    shape=(len(texts), embedding_dim),
                    dtype=np.float32
                )
                
                logger.info(f"Created memory-mapped array for {len(texts)} embeddings")
            except Exception as e:
                logger.warning(f"Failed to create memory-mapped array: {e}")
        
        def process_embedding_batch(batch_texts: List[str]) -> List[np.ndarray]:
            try:
                return embedding_function(batch_texts)
            except Exception as e:
                logger.error(f"Embedding batch processing error: {e}")
                return [np.zeros(1536, dtype=np.float32) for _ in batch_texts]  # Return zeros as fallback
        
        if embeddings_array is not None:
            # Process with memory mapping
            batches = list(self.create_batches(texts, batch_size))
            current_idx = 0
            
            for batch in batches:
                batch_embeddings = process_embedding_batch(batch)
                for embedding in batch_embeddings:
                    if current_idx < len(texts):
                        embeddings_array[current_idx] = embedding
                        current_idx += 1
            
            # Convert to list
            result = [embeddings_array[i] for i in range(len(texts))]
            embeddings_array.close()
            return result
        
        else:
            # Standard batch processing
            return self.process_batch_sync(
                texts,
                process_embedding_batch,
                batch_size,
                use_multiprocessing=False  # Embeddings are usually GPU-bound
            )
    
    def process_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        processing_function: Callable[[List[Dict]], List[Dict]],
        batch_size: int = None
    ) -> List[Dict[str, Any]]:
        batch_size = batch_size or self.config.batch_size
        
        def process_document_batch(batch_docs: List[Dict]) -> List[Dict]:
            try:
                return processing_function(batch_docs)
            except Exception as e:
                logger.error(f"Document batch processing error: {e}")
                return batch_docs  # Return original documents as fallback
        
        return self.process_batch_sync(
            documents,
            process_document_batch,
            batch_size,
            use_multiprocessing=True  # Document processing is CPU-intensive
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        runtime = (datetime.now() - self.metrics['started_at']).total_seconds()
        memory_info = self.process_manager.get_memory_info()
        
        return {
            **self.metrics,
            'runtime_seconds': runtime,
            'items_per_second': self.metrics['total_items_processed'] / runtime if runtime > 0 else 0,
            'current_memory_usage_mb': memory_info.get('process_memory_mb', 0),
            'system_memory_percent': memory_info.get('system_memory_percent', 0)
        }
    
    def cleanup(self):
        if self.thread_executor:
            self.thread_executor.shutdown(wait=True)
        
        if self.process_executor:
            self.process_executor.shutdown(wait=True)
        
        # Force garbage collection
        gc.collect()

# Global batch processor instance
batch_processor: Optional[WindowsBatchProcessor] = None

def initialize_batch_processor(config: BatchProcessingConfig = None) -> WindowsBatchProcessor:
    global batch_processor
    batch_processor = WindowsBatchProcessor(config)
    return batch_processor

def get_batch_processor() -> WindowsBatchProcessor:
    if batch_processor is None:
        initialize_batch_processor()
    return batch_processor

# Convenience functions
def process_embeddings_parallel(
    texts: List[str],
    embedding_function: Callable[[List[str]], List[np.ndarray]],
    batch_size: int = 100
) -> List[np.ndarray]:
    processor = get_batch_processor()
    return processor.process_embeddings_batch(texts, embedding_function, batch_size)

def process_documents_parallel(
    documents: List[Dict[str, Any]],
    processing_function: Callable[[List[Dict]], List[Dict]],
    batch_size: int = 50
) -> List[Dict[str, Any]]:
    processor = get_batch_processor()
    return processor.process_documents_batch(documents, processing_function, batch_size)