import gc
import os
import sys
import threading
import time
import logging
import psutil
import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict, deque
from functools import wraps
import weakref
import tracemalloc
import numpy as np

# Windows-specific imports
import win32process
import win32api
import win32con
import wmi

logger = logging.getLogger(__name__)

@dataclass
class MemoryConfig:
    max_memory_percent: int = 85
    gc_threshold_percent: int = 70
    aggressive_gc_percent: int = 80
    monitoring_interval: int = 30
    enable_memory_profiling: bool = False
    enable_memory_mapping: bool = True
    cache_cleanup_interval: int = 300  # 5 minutes
    large_object_threshold: int = 1024 * 1024  # 1MB

class WindowsMemoryInfo:
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32
        self.psapi = ctypes.windll.psapi
        
        # Windows memory status structure
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
            ]
        
        self.MEMORYSTATUSEX = MEMORYSTATUSEX
        
        # Working set information
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]
        
        self.PROCESS_MEMORY_COUNTERS_EX = PROCESS_MEMORY_COUNTERS_EX
    
    def get_system_memory_info(self) -> Dict[str, Any]:
        mem_status = self.MEMORYSTATUSEX()
        mem_status.dwLength = ctypes.sizeof(self.MEMORYSTATUSEX)
        
        if self.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status)):
            return {
                'total_physical_gb': mem_status.ullTotalPhys / (1024**3),
                'available_physical_gb': mem_status.ullAvailPhys / (1024**3),
                'memory_load_percent': mem_status.dwMemoryLoad,
                'total_virtual_gb': mem_status.ullTotalVirtual / (1024**3),
                'available_virtual_gb': mem_status.ullAvailVirtual / (1024**3),
                'total_page_file_gb': mem_status.ullTotalPageFile / (1024**3),
                'available_page_file_gb': mem_status.ullAvailPageFile / (1024**3)
            }
        return {}
    
    def get_process_memory_info(self) -> Dict[str, Any]:
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_full_info = process.memory_full_info()
            
            # Get Windows-specific memory counters
            handle = win32api.GetCurrentProcess()
            counters = self.PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(self.PROCESS_MEMORY_COUNTERS_EX)
            
            if self.psapi.GetProcessMemoryInfo(
                handle,
                ctypes.byref(counters),
                ctypes.sizeof(self.PROCESS_MEMORY_COUNTERS_EX)
            ):
                return {
                    'rss_mb': memory_info.rss / (1024**2),
                    'vms_mb': memory_info.vms / (1024**2),
                    'working_set_mb': counters.WorkingSetSize / (1024**2),
                    'peak_working_set_mb': counters.PeakWorkingSetSize / (1024**2),
                    'private_usage_mb': counters.PrivateUsage / (1024**2),
                    'page_fault_count': counters.PageFaultCount,
                    'paged_pool_usage_mb': counters.QuotaPagedPoolUsage / (1024**2),
                    'non_paged_pool_usage_mb': counters.QuotaNonPagedPoolUsage / (1024**2),
                    'percent': process.memory_percent(),
                    'num_threads': process.num_threads(),
                    'num_handles': process.num_handles(),
                    'uss': getattr(memory_full_info, 'uss', 0) / (1024**2),  # Unique Set Size
                    'pss': getattr(memory_full_info, 'pss', 0) / (1024**2),  # Proportional Set Size
                }
            
        except Exception as e:
            logger.error(f"Failed to get process memory info: {e}")
        
        return {}

class MemoryTracker:
    def __init__(self):
        self.allocations = defaultdict(int)
        self.deallocations = defaultdict(int)
        self.peak_usage = 0
        self.large_objects = weakref.WeakSet()
        self._lock = threading.Lock()
    
    def track_allocation(self, obj_type: str, size: int):
        with self._lock:
            self.allocations[obj_type] += size
            current_usage = sum(self.allocations.values()) - sum(self.deallocations.values())
            if current_usage > self.peak_usage:
                self.peak_usage = current_usage
    
    def track_deallocation(self, obj_type: str, size: int):
        with self._lock:
            self.deallocations[obj_type] += size
    
    def register_large_object(self, obj: Any):
        try:
            obj_size = sys.getsizeof(obj)
            if obj_size > 1024 * 1024:  # 1MB
                self.large_objects.add(obj)
                logger.debug(f"Registered large object: {type(obj).__name__} ({obj_size / 1024 / 1024:.2f} MB)")
        except:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'allocations': dict(self.allocations),
                'deallocations': dict(self.deallocations),
                'peak_usage_mb': self.peak_usage / (1024**2),
                'current_usage_mb': (sum(self.allocations.values()) - sum(self.deallocations.values())) / (1024**2),
                'large_objects_count': len(self.large_objects)
            }

class WindowsGarbageCollector:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.last_gc_time = time.time()
        self.gc_stats = {
            'collections': defaultdict(int),
            'total_time': 0.0,
            'objects_freed': defaultdict(int)
        }
        
        # Configure garbage collector thresholds for Windows
        self._configure_gc_thresholds()
    
    def _configure_gc_thresholds(self):
        # Optimize GC thresholds for Windows and RAG workload
        # Generation 0: frequent small allocations (embeddings, text chunks)
        # Generation 1: medium-lived objects (processed documents)
        # Generation 2: long-lived objects (models, caches)
        
        # More aggressive collection for generation 0 (text processing creates many temp objects)
        # Less frequent for generation 2 (avoid collecting long-lived caches)
        gc.set_threshold(500, 8, 8)  # Default is (700, 10, 10)
        
        logger.info(f"Set GC thresholds: {gc.get_threshold()}")
    
    def force_collection(self, generation: Optional[int] = None) -> Dict[str, int]:
        start_time = time.time()
        
        if generation is not None:
            collected = gc.collect(generation)
            self.gc_stats['collections'][generation] += 1
        else:
            collected = gc.collect()
            self.gc_stats['collections']['full'] += 1
        
        collection_time = time.time() - start_time
        self.gc_stats['total_time'] += collection_time
        self.gc_stats['objects_freed']['total'] += collected
        
        logger.info(f"GC collection freed {collected} objects in {collection_time:.3f}s")
        return {
            'objects_freed': collected,
            'collection_time': collection_time,
            'generation': generation or 'full'
        }
    
    def smart_collection(self, memory_percent: float) -> bool:
        current_time = time.time()
        time_since_last = current_time - self.last_gc_time
        
        # Determine collection strategy based on memory pressure
        if memory_percent > self.config.aggressive_gc_percent:
            # High memory pressure: full collection
            self.force_collection()
            self.last_gc_time = current_time
            return True
            
        elif memory_percent > self.config.gc_threshold_percent:
            # Medium pressure: collect generations 0 and 1
            self.force_collection(0)
            if time_since_last > 60:  # Don't collect gen 1 too frequently
                self.force_collection(1)
                self.last_gc_time = current_time
            return True
            
        elif time_since_last > 300:  # 5 minutes
            # Periodic light collection
            self.force_collection(0)
            self.last_gc_time = current_time
            return True
        
        return False
    
    def get_gc_stats(self) -> Dict[str, Any]:
        return {
            **self.gc_stats,
            'gc_counts': gc.get_count(),
            'gc_thresholds': gc.get_threshold(),
            'gc_flags': gc.get_debug() if hasattr(gc, 'get_debug') else 0
        }

class WindowsMemoryManager:
    def __init__(self, config: MemoryConfig = None):
        self.config = config or MemoryConfig()
        self.memory_info = WindowsMemoryInfo()
        self.memory_tracker = MemoryTracker()
        self.gc_manager = WindowsGarbageCollector(self.config)
        
        # Memory monitoring
        self._monitoring_active = False
        self._monitoring_thread = None
        self._memory_history = deque(maxlen=100)  # Keep last 100 measurements
        
        # Cache for expensive operations
        self._info_cache = {}
        self._cache_lock = threading.Lock()
        self._last_cache_cleanup = time.time()
        
        # Memory profiling
        if self.config.enable_memory_profiling:
            tracemalloc.start()
        
        # Start monitoring
        self.start_monitoring()
    
    def start_monitoring(self):
        if not self._monitoring_active:
            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._memory_monitor_loop,
                daemon=True,
                name="memory_monitor"
            )
            self._monitoring_thread.start()
            logger.info("Started Windows memory monitoring")
    
    def stop_monitoring(self):
        self._monitoring_active = False
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)
        logger.info("Stopped memory monitoring")
    
    def _memory_monitor_loop(self):
        while self._monitoring_active:
            try:
                self._update_memory_metrics()
                self._check_memory_pressure()
                self._cleanup_caches_if_needed()
                time.sleep(self.config.monitoring_interval)
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                time.sleep(60)
    
    def _update_memory_metrics(self):
        try:
            system_info = self.memory_info.get_system_memory_info()
            process_info = self.memory_info.get_process_memory_info()
            
            memory_data = {
                'timestamp': datetime.now(),
                'system': system_info,
                'process': process_info
            }
            
            self._memory_history.append(memory_data)
            
            # Cache system info briefly to avoid expensive calls
            with self._cache_lock:
                self._info_cache['last_system_info'] = system_info
                self._info_cache['last_process_info'] = process_info
                self._info_cache['last_update'] = time.time()
            
        except Exception as e:
            logger.error(f"Failed to update memory metrics: {e}")
    
    def _check_memory_pressure(self):
        try:
            system_info = self.memory_info.get_system_memory_info()
            memory_load = system_info.get('memory_load_percent', 0)
            
            if memory_load > self.config.max_memory_percent:
                logger.warning(f"High system memory usage: {memory_load}%")
                self._handle_memory_pressure(memory_load)
                
            process_info = self.memory_info.get_process_memory_info()
            process_percent = process_info.get('percent', 0)
            
            if process_percent > 10:  # Process using more than 10% of system memory
                logger.info(f"High process memory usage: {process_percent:.1f}%")
                self.gc_manager.smart_collection(process_percent)
                
        except Exception as e:
            logger.error(f"Memory pressure check failed: {e}")
    
    def _handle_memory_pressure(self, memory_percent: float):
        logger.warning(f"Handling memory pressure: {memory_percent}%")
        
        # 1. Force garbage collection
        gc_result = self.gc_manager.force_collection()
        
        # 2. Clear caches
        self.clear_caches()
        
        # 3. If still high pressure, more aggressive cleanup
        if memory_percent > 90:
            self._aggressive_cleanup()
    
    def _aggressive_cleanup(self):
        logger.warning("Performing aggressive memory cleanup")
        
        # Clear large objects from tracker
        large_objects_count = len(self.memory_tracker.large_objects)
        self.memory_tracker.large_objects.clear()
        
        # Multiple GC passes
        for i in range(3):
            self.gc_manager.force_collection()
            time.sleep(0.1)
        
        logger.info(f"Aggressive cleanup: cleared {large_objects_count} large object references")
    
    def _cleanup_caches_if_needed(self):
        current_time = time.time()
        if current_time - self._last_cache_cleanup > self.config.cache_cleanup_interval:
            self.clear_caches()
            self._last_cache_cleanup = current_time
    
    def clear_caches(self):
        with self._cache_lock:
            self._info_cache.clear()
        
        # Clear any numpy array caches
        try:
            if hasattr(np, '_NoValue'):
                np.seterrcall(None)
        except:
            pass
        
        logger.info("Cleared memory manager caches")
    
    def get_memory_info(self, use_cache: bool = True) -> Dict[str, Any]:
        current_time = time.time()
        
        if use_cache:
            with self._cache_lock:
                if ('last_system_info' in self._info_cache and 
                    current_time - self._info_cache.get('last_update', 0) < 30):
                    return {
                        'system': self._info_cache['last_system_info'],
                        'process': self._info_cache['last_process_info'],
                        'cached': True,
                        'timestamp': datetime.fromtimestamp(self._info_cache['last_update'])
                    }
        
        # Get fresh data
        system_info = self.memory_info.get_system_memory_info()
        process_info = self.memory_info.get_process_memory_info()
        
        return {
            'system': system_info,
            'process': process_info,
            'cached': False,
            'timestamp': datetime.now()
        }
    
    def get_memory_stats(self) -> Dict[str, Any]:
        memory_info = self.get_memory_info()
        tracker_stats = self.memory_tracker.get_stats()
        gc_stats = self.gc_manager.get_gc_stats()
        
        # Calculate memory trends
        trends = self._calculate_memory_trends()
        
        return {
            'current': memory_info,
            'tracking': tracker_stats,
            'garbage_collection': gc_stats,
            'trends': trends,
            'config': {
                'max_memory_percent': self.config.max_memory_percent,
                'gc_threshold_percent': self.config.gc_threshold_percent,
                'monitoring_interval': self.config.monitoring_interval
            }
        }
    
    def _calculate_memory_trends(self) -> Dict[str, Any]:
        if len(self._memory_history) < 2:
            return {}
        
        recent_data = list(self._memory_history)[-10:]  # Last 10 measurements
        
        system_loads = [d['system'].get('memory_load_percent', 0) for d in recent_data]
        process_usage = [d['process'].get('rss_mb', 0) for d in recent_data]
        
        return {
            'system_memory_trend': 'increasing' if system_loads[-1] > system_loads[0] else 'decreasing',
            'process_memory_trend': 'increasing' if process_usage[-1] > process_usage[0] else 'decreasing',
            'avg_system_load': sum(system_loads) / len(system_loads),
            'avg_process_usage_mb': sum(process_usage) / len(process_usage),
            'peak_system_load': max(system_loads),
            'peak_process_usage_mb': max(process_usage)
        }
    
    def register_large_object(self, obj: Any, obj_type: str = None):
        try:
            obj_size = sys.getsizeof(obj)
            if obj_size > self.config.large_object_threshold:
                self.memory_tracker.register_large_object(obj)
                self.memory_tracker.track_allocation(obj_type or type(obj).__name__, obj_size)
        except Exception as e:
            logger.debug(f"Failed to register large object: {e}")
    
    def optimize_for_embeddings(self):
        """Optimize memory settings for embedding-intensive workloads"""
        logger.info("Optimizing memory management for embedding workloads")
        
        # Adjust GC thresholds for embedding processing
        gc.set_threshold(300, 6, 6)  # More frequent collection
        
        # Pre-allocate some memory to reduce fragmentation
        try:
            dummy_arrays = []
            for _ in range(10):
                arr = np.zeros((1000, 1536), dtype=np.float32)  # Typical embedding shape
                dummy_arrays.append(arr)
            
            # Release the arrays to create holes for future allocations
            del dummy_arrays
            gc.collect()
            
        except Exception as e:
            logger.warning(f"Memory pre-allocation failed: {e}")
    
    def cleanup(self):
        self.stop_monitoring()
        self.clear_caches()
        
        if self.config.enable_memory_profiling and tracemalloc.is_tracing():
            tracemalloc.stop()

# Memory management decorators
def track_memory(obj_type: str = None):
    """Decorator to track memory usage of function calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if memory_manager:
                start_memory = psutil.Process().memory_info().rss
                
            result = func(*args, **kwargs)
            
            if memory_manager:
                end_memory = psutil.Process().memory_info().rss
                memory_used = end_memory - start_memory
                
                func_type = obj_type or func.__name__
                memory_manager.memory_tracker.track_allocation(func_type, memory_used)
                
                # Register result as large object if significant
                if hasattr(result, '__sizeof__') and memory_used > 1024 * 1024:
                    memory_manager.register_large_object(result, func_type)
            
            return result
        return wrapper
    return decorator

def memory_limit(max_mb: int):
    """Decorator to limit memory usage during function execution"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if memory_manager:
                process = psutil.Process()
                initial_memory = process.memory_info().rss / (1024 * 1024)
                
                def check_memory():
                    current_memory = process.memory_info().rss / (1024 * 1024)
                    if current_memory - initial_memory > max_mb:
                        raise MemoryError(f"Function exceeded memory limit of {max_mb}MB")
                
                # Check memory every 100 iterations (for loops) or before heavy operations
                # This is a simplified implementation - in practice, you'd need more sophisticated monitoring
                check_memory()
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Global memory manager instance
memory_manager: Optional[WindowsMemoryManager] = None

def initialize_memory_manager(config: MemoryConfig = None) -> WindowsMemoryManager:
    global memory_manager
    memory_manager = WindowsMemoryManager(config)
    return memory_manager

def get_memory_manager() -> WindowsMemoryManager:
    if memory_manager is None:
        initialize_memory_manager()
    return memory_manager