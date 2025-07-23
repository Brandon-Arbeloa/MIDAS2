import os
import time
import json
import logging
import threading
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import psutil
import wmi
import win32pdh
import win32pdhutil
from prometheus_client import start_http_server, Gauge, Counter, Histogram, CollectorRegistry
from prometheus_client.exposition import generate_latest
import requests

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    name: str
    value: float
    unit: str
    timestamp: datetime
    labels: Dict[str, str] = None

class WindowsPerformanceCounters:
    def __init__(self):
        self.wmi_conn = wmi.WMI()
        self.pdh_queries = {}
        self._initialize_counters()
    
    def _initialize_counters(self):
        """Initialize Windows Performance Counters"""
        try:
            # CPU Counters
            self.pdh_queries['cpu_usage'] = win32pdh.OpenQuery()
            cpu_counter = win32pdh.AddEnglishCounter(
                self.pdh_queries['cpu_usage'], 
                r"\Processor Information(_Total)\% Processor Time"
            )
            self.pdh_queries['cpu_counter'] = cpu_counter
            
            # Memory Counters
            self.pdh_queries['memory_usage'] = win32pdh.OpenQuery()
            memory_counter = win32pdh.AddEnglishCounter(
                self.pdh_queries['memory_usage'],
                r"\Memory\Available MBytes"
            )
            self.pdh_queries['memory_counter'] = memory_counter
            
            # Disk I/O Counters
            self.pdh_queries['disk_io'] = win32pdh.OpenQuery()
            disk_read_counter = win32pdh.AddEnglishCounter(
                self.pdh_queries['disk_io'],
                r"\PhysicalDisk(_Total)\Disk Read Bytes/sec"
            )
            disk_write_counter = win32pdh.AddEnglishCounter(
                self.pdh_queries['disk_io'],
                r"\PhysicalDisk(_Total)\Disk Write Bytes/sec"
            )
            self.pdh_queries['disk_read_counter'] = disk_read_counter
            self.pdh_queries['disk_write_counter'] = disk_write_counter
            
            # Network Counters
            network_interfaces = win32pdhutil.EnumObjectItems(None, None, "Network Interface", win32pdh.PERF_DETAIL_WIZARD)[0]
            active_interface = None
            
            for interface in network_interfaces:
                if "Loopback" not in interface and "Isatap" not in interface:
                    active_interface = interface
                    break
            
            if active_interface:
                self.pdh_queries['network_io'] = win32pdh.OpenQuery()
                network_in_counter = win32pdh.AddEnglishCounter(
                    self.pdh_queries['network_io'],
                    f"\\Network Interface({active_interface})\\Bytes Received/sec"
                )
                network_out_counter = win32pdh.AddEnglishCounter(
                    self.pdh_queries['network_io'],
                    f"\\Network Interface({active_interface})\\Bytes Sent/sec"
                )
                self.pdh_queries['network_in_counter'] = network_in_counter
                self.pdh_queries['network_out_counter'] = network_out_counter
            
            logger.info("Initialized Windows Performance Counters")
            
        except Exception as e:
            logger.error(f"Failed to initialize performance counters: {e}")
    
    def get_cpu_metrics(self) -> Dict[str, float]:
        try:
            win32pdh.CollectQueryData(self.pdh_queries['cpu_usage'])
            time.sleep(0.1)  # Small delay for accurate reading
            win32pdh.CollectQueryData(self.pdh_queries['cpu_usage'])
            
            cpu_usage = win32pdh.GetFormattedCounterValue(
                self.pdh_queries['cpu_counter'],
                win32pdh.PDH_FMT_DOUBLE
            )[1]
            
            # Additional CPU metrics using psutil
            cpu_per_core = psutil.cpu_percent(percpu=True)
            cpu_freq = psutil.cpu_freq()
            
            return {
                'cpu_usage_percent': cpu_usage,
                'cpu_cores_count': psutil.cpu_count(logical=False),
                'cpu_threads_count': psutil.cpu_count(logical=True),
                'cpu_frequency_mhz': cpu_freq.current if cpu_freq else 0,
                'cpu_per_core': cpu_per_core,
                'load_average_1min': psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0
            }
        except Exception as e:
            logger.error(f"Failed to get CPU metrics: {e}")
            return {}
    
    def get_memory_metrics(self) -> Dict[str, float]:
        try:
            win32pdh.CollectQueryData(self.pdh_queries['memory_usage'])
            available_memory = win32pdh.GetFormattedCounterValue(
                self.pdh_queries['memory_counter'],
                win32pdh.PDH_FMT_DOUBLE
            )[1]
            
            # Additional memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                'memory_total_gb': memory.total / (1024**3),
                'memory_available_gb': available_memory / 1024,  # Convert MB to GB
                'memory_used_gb': (memory.total - memory.available) / (1024**3),
                'memory_usage_percent': memory.percent,
                'memory_cached_gb': getattr(memory, 'cached', 0) / (1024**3),
                'memory_buffers_gb': getattr(memory, 'buffers', 0) / (1024**3),
                'swap_total_gb': swap.total / (1024**3),
                'swap_used_gb': swap.used / (1024**3),
                'swap_usage_percent': swap.percent
            }
        except Exception as e:
            logger.error(f"Failed to get memory metrics: {e}")
            return {}
    
    def get_disk_metrics(self) -> Dict[str, Any]:
        try:
            win32pdh.CollectQueryData(self.pdh_queries['disk_io'])
            time.sleep(0.1)
            win32pdh.CollectQueryData(self.pdh_queries['disk_io'])
            
            disk_read_bytes = win32pdh.GetFormattedCounterValue(
                self.pdh_queries['disk_read_counter'],
                win32pdh.PDH_FMT_DOUBLE
            )[1]
            
            disk_write_bytes = win32pdh.GetFormattedCounterValue(
                self.pdh_queries['disk_write_counter'],
                win32pdh.PDH_FMT_DOUBLE
            )[1]
            
            # Disk usage information
            disk_usage = psutil.disk_usage('C:')
            disk_io = psutil.disk_io_counters()
            
            metrics = {
                'disk_read_bytes_per_sec': disk_read_bytes,
                'disk_write_bytes_per_sec': disk_write_bytes,
                'disk_total_gb': disk_usage.total / (1024**3),
                'disk_used_gb': disk_usage.used / (1024**3),
                'disk_free_gb': disk_usage.free / (1024**3),
                'disk_usage_percent': (disk_usage.used / disk_usage.total) * 100,
            }
            
            if disk_io:
                metrics.update({
                    'disk_read_count': disk_io.read_count,
                    'disk_write_count': disk_io.write_count,
                    'disk_read_time_ms': disk_io.read_time,
                    'disk_write_time_ms': disk_io.write_time
                })
            
            return metrics
        except Exception as e:
            logger.error(f"Failed to get disk metrics: {e}")
            return {}
    
    def get_network_metrics(self) -> Dict[str, float]:
        try:
            if 'network_io' not in self.pdh_queries:
                return {}
            
            win32pdh.CollectQueryData(self.pdh_queries['network_io'])
            time.sleep(0.1)
            win32pdh.CollectQueryData(self.pdh_queries['network_io'])
            
            network_in_bytes = win32pdh.GetFormattedCounterValue(
                self.pdh_queries['network_in_counter'],
                win32pdh.PDH_FMT_DOUBLE
            )[1]
            
            network_out_bytes = win32pdh.GetFormattedCounterValue(
                self.pdh_queries['network_out_counter'],
                win32pdh.PDH_FMT_DOUBLE
            )[1]
            
            # Additional network metrics
            net_io = psutil.net_io_counters()
            
            metrics = {
                'network_bytes_received_per_sec': network_in_bytes,
                'network_bytes_sent_per_sec': network_out_bytes,
            }
            
            if net_io:
                metrics.update({
                    'network_packets_sent': net_io.packets_sent,
                    'network_packets_received': net_io.packets_recv,
                    'network_errors_in': net_io.errin,
                    'network_errors_out': net_io.errout,
                    'network_drops_in': net_io.dropin,
                    'network_drops_out': net_io.dropout
                })
            
            return metrics
        except Exception as e:
            logger.error(f"Failed to get network metrics: {e}")
            return {}

class MIDASApplicationMonitor:
    def __init__(self):
        self.process_monitors = {}
        self._initialize_application_monitoring()
    
    def _initialize_application_monitoring(self):
        """Initialize monitoring for MIDAS application components"""
        self.component_processes = {
            'postgres': 'postgres.exe',
            'redis': 'redis-server.exe',
            'ollama': 'ollama.exe',
            'qdrant': 'qdrant.exe',
            'python': 'python.exe'  # For FastAPI/Streamlit
        }
    
    def get_application_metrics(self) -> Dict[str, Dict]:
        metrics = {}
        
        for component, process_name in self.component_processes.items():
            try:
                processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'num_threads']):
                    if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                        processes.append(proc)
                
                if processes:
                    # Aggregate metrics for all processes of this component
                    total_cpu = sum(proc.cpu_percent() for proc in processes)
                    total_memory = sum(proc.memory_info().rss for proc in processes)
                    total_threads = sum(proc.num_threads() for proc in processes)
                    
                    metrics[component] = {
                        'process_count': len(processes),
                        'cpu_percent': total_cpu,
                        'memory_mb': total_memory / (1024**2),
                        'threads': total_threads,
                        'status': 'running',
                        'pids': [proc.pid for proc in processes]
                    }
                else:
                    metrics[component] = {
                        'process_count': 0,
                        'status': 'stopped'
                    }
                    
            except Exception as e:
                logger.error(f"Failed to get metrics for {component}: {e}")
                metrics[component] = {'status': 'error', 'error': str(e)}
        
        return metrics
    
    def get_docker_metrics(self) -> Dict[str, Any]:
        """Get Docker container metrics if running in Docker"""
        try:
            result = subprocess.run(
                ['docker', 'stats', '--no-stream', '--format', 'json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                containers = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        container_data = json.loads(line)
                        containers.append(container_data)
                
                return {'containers': containers, 'status': 'running'}
            else:
                return {'status': 'not_running', 'error': result.stderr}
                
        except subprocess.TimeoutExpired:
            return {'status': 'timeout'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

class PrometheusExporter:
    def __init__(self, port: int = 8090):
        self.port = port
        self.registry = CollectorRegistry()
        
        # System metrics
        self.cpu_usage = Gauge('windows_cpu_usage_percent', 'CPU usage percentage', registry=self.registry)
        self.memory_usage = Gauge('windows_memory_usage_percent', 'Memory usage percentage', registry=self.registry)
        self.memory_available = Gauge('windows_memory_available_gb', 'Available memory in GB', registry=self.registry)
        self.disk_usage = Gauge('windows_disk_usage_percent', 'Disk usage percentage', registry=self.registry)
        self.disk_io_read = Gauge('windows_disk_read_bytes_per_sec', 'Disk read bytes per second', registry=self.registry)
        self.disk_io_write = Gauge('windows_disk_write_bytes_per_sec', 'Disk write bytes per second', registry=self.registry)
        self.network_in = Gauge('windows_network_bytes_received_per_sec', 'Network bytes received per second', registry=self.registry)
        self.network_out = Gauge('windows_network_bytes_sent_per_sec', 'Network bytes sent per second', registry=self.registry)
        
        # Application metrics
        self.app_cpu_usage = Gauge('midas_app_cpu_percent', 'Application CPU usage', ['component'], registry=self.registry)
        self.app_memory_usage = Gauge('midas_app_memory_mb', 'Application memory usage in MB', ['component'], registry=self.registry)
        self.app_process_count = Gauge('midas_app_process_count', 'Number of processes', ['component'], registry=self.registry)
        
        # Performance counters
        self.query_duration = Histogram('midas_query_duration_seconds', 'Query duration in seconds', ['query_type'], registry=self.registry)
        self.embedding_generation = Histogram('midas_embedding_generation_seconds', 'Embedding generation time', registry=self.registry)
        self.cache_hits = Counter('midas_cache_hits_total', 'Cache hits', ['cache_type'], registry=self.registry)
        self.cache_misses = Counter('midas_cache_misses_total', 'Cache misses', ['cache_type'], registry=self.registry)
    
    def update_system_metrics(self, metrics: Dict[str, Any]):
        """Update Prometheus metrics with system data"""
        cpu_metrics = metrics.get('cpu', {})
        memory_metrics = metrics.get('memory', {})
        disk_metrics = metrics.get('disk', {})
        network_metrics = metrics.get('network', {})
        
        if cpu_metrics:
            self.cpu_usage.set(cpu_metrics.get('cpu_usage_percent', 0))
        
        if memory_metrics:
            self.memory_usage.set(memory_metrics.get('memory_usage_percent', 0))
            self.memory_available.set(memory_metrics.get('memory_available_gb', 0))
        
        if disk_metrics:
            self.disk_usage.set(disk_metrics.get('disk_usage_percent', 0))
            self.disk_io_read.set(disk_metrics.get('disk_read_bytes_per_sec', 0))
            self.disk_io_write.set(disk_metrics.get('disk_write_bytes_per_sec', 0))
        
        if network_metrics:
            self.network_in.set(network_metrics.get('network_bytes_received_per_sec', 0))
            self.network_out.set(network_metrics.get('network_bytes_sent_per_sec', 0))
    
    def update_application_metrics(self, app_metrics: Dict[str, Dict]):
        """Update Prometheus metrics with application data"""
        for component, metrics in app_metrics.items():
            if metrics.get('status') == 'running':
                self.app_cpu_usage.labels(component=component).set(metrics.get('cpu_percent', 0))
                self.app_memory_usage.labels(component=component).set(metrics.get('memory_mb', 0))
                self.app_process_count.labels(component=component).set(metrics.get('process_count', 0))
    
    def start_server(self):
        """Start the Prometheus HTTP server"""
        try:
            start_http_server(self.port, registry=self.registry)
            logger.info(f"Prometheus exporter started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus exporter: {e}")
    
    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format"""
        return generate_latest(self.registry).decode('utf-8')

class WindowsPerformanceMonitor:
    def __init__(
        self,
        monitoring_interval: int = 30,
        prometheus_port: int = 8090,
        enable_prometheus: bool = True,
        log_file: Optional[str] = None
    ):
        self.monitoring_interval = monitoring_interval
        self.enable_prometheus = enable_prometheus
        
        # Initialize components
        self.perf_counters = WindowsPerformanceCounters()
        self.app_monitor = MIDASApplicationMonitor()
        
        if enable_prometheus:
            self.prometheus_exporter = PrometheusExporter(prometheus_port)
            self.prometheus_exporter.start_server()
        
        # Metrics storage
        self.metrics_history = []
        self.max_history_size = 1000
        
        # Logging
        if log_file:
            self.setup_file_logging(log_file)
        
        # Monitoring thread
        self._monitoring_active = False
        self._monitoring_thread = None
    
    def setup_file_logging(self, log_file: str):
        """Setup file logging for metrics"""
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
    
    def start_monitoring(self):
        """Start continuous monitoring"""
        if not self._monitoring_active:
            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="performance_monitor"
            )
            self._monitoring_thread.start()
            logger.info("Started Windows performance monitoring")
    
    def stop_monitoring(self):
        """Stop continuous monitoring"""
        self._monitoring_active = False
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)
        logger.info("Stopped performance monitoring")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self._monitoring_active:
            try:
                metrics = self.collect_all_metrics()
                self._store_metrics(metrics)
                
                if self.enable_prometheus:
                    self._update_prometheus_metrics(metrics)
                
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(60)  # Wait before retrying
    
    def collect_all_metrics(self) -> Dict[str, Any]:
        """Collect all system and application metrics"""
        timestamp = datetime.now()
        
        metrics = {
            'timestamp': timestamp.isoformat(),
            'system': {
                'cpu': self.perf_counters.get_cpu_metrics(),
                'memory': self.perf_counters.get_memory_metrics(),
                'disk': self.perf_counters.get_disk_metrics(),
                'network': self.perf_counters.get_network_metrics()
            },
            'applications': self.app_monitor.get_application_metrics(),
            'docker': self.app_monitor.get_docker_metrics()
        }
        
        return metrics
    
    def _store_metrics(self, metrics: Dict[str, Any]):
        """Store metrics in history"""
        self.metrics_history.append(metrics)
        
        # Limit history size
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history = self.metrics_history[-self.max_history_size:]
    
    def _update_prometheus_metrics(self, metrics: Dict[str, Any]):
        """Update Prometheus exporter with new metrics"""
        try:
            self.prometheus_exporter.update_system_metrics(metrics['system'])
            self.prometheus_exporter.update_application_metrics(metrics['applications'])
        except Exception as e:
            logger.error(f"Failed to update Prometheus metrics: {e}")
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        return self.collect_all_metrics()
    
    def get_metrics_summary(self, hours: int = 1) -> Dict[str, Any]:
        """Get summary of metrics for the specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_metrics = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m['timestamp']) > cutoff_time
        ]
        
        if not recent_metrics:
            return {}
        
        # Calculate averages
        cpu_values = []
        memory_values = []
        disk_values = []
        
        for metric in recent_metrics:
            system = metric.get('system', {})
            cpu_values.append(system.get('cpu', {}).get('cpu_usage_percent', 0))
            memory_values.append(system.get('memory', {}).get('memory_usage_percent', 0))
            disk_values.append(system.get('disk', {}).get('disk_usage_percent', 0))
        
        return {
            'period_hours': hours,
            'samples_count': len(recent_metrics),
            'averages': {
                'cpu_usage_percent': sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                'memory_usage_percent': sum(memory_values) / len(memory_values) if memory_values else 0,
                'disk_usage_percent': sum(disk_values) / len(disk_values) if disk_values else 0
            },
            'maximums': {
                'cpu_usage_percent': max(cpu_values) if cpu_values else 0,
                'memory_usage_percent': max(memory_values) if memory_values else 0,
                'disk_usage_percent': max(disk_values) if disk_values else 0
            }
        }
    
    def export_metrics_to_file(self, file_path: str, hours: int = 24):
        """Export metrics to JSON file"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        export_metrics = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m['timestamp']) > cutoff_time
        ]
        
        export_data = {
            'export_time': datetime.now().isoformat(),
            'period_hours': hours,
            'metrics_count': len(export_metrics),
            'metrics': export_metrics
        }
        
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        logger.info(f"Exported {len(export_metrics)} metrics to {file_path}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status"""
        current_metrics = self.get_current_metrics()
        system = current_metrics.get('system', {})
        apps = current_metrics.get('applications', {})
        
        # Determine health based on thresholds
        health_issues = []
        
        # CPU health
        cpu_usage = system.get('cpu', {}).get('cpu_usage_percent', 0)
        if cpu_usage > 90:
            health_issues.append(f"High CPU usage: {cpu_usage:.1f}%")
        
        # Memory health
        memory_usage = system.get('memory', {}).get('memory_usage_percent', 0)
        if memory_usage > 90:
            health_issues.append(f"High memory usage: {memory_usage:.1f}%")
        
        # Disk health
        disk_usage = system.get('disk', {}).get('disk_usage_percent', 0)
        if disk_usage > 90:
            health_issues.append(f"High disk usage: {disk_usage:.1f}%")
        
        # Application health
        critical_apps = ['postgres', 'redis', 'ollama', 'qdrant']
        for app in critical_apps:
            if apps.get(app, {}).get('status') != 'running':
                health_issues.append(f"{app} is not running")
        
        return {
            'status': 'healthy' if not health_issues else 'warning' if len(health_issues) < 3 else 'critical',
            'issues': health_issues,
            'checked_at': datetime.now().isoformat(),
            'uptime_seconds': time.time() - (self.metrics_history[0]['timestamp'] if self.metrics_history else time.time())
        }

# Global monitor instance
performance_monitor: Optional[WindowsPerformanceMonitor] = None

def initialize_performance_monitor(
    monitoring_interval: int = 30,
    prometheus_port: int = 8090,
    enable_prometheus: bool = True
) -> WindowsPerformanceMonitor:
    global performance_monitor
    performance_monitor = WindowsPerformanceMonitor(
        monitoring_interval=monitoring_interval,
        prometheus_port=prometheus_port,
        enable_prometheus=enable_prometheus
    )
    performance_monitor.start_monitoring()
    return performance_monitor

def get_performance_monitor() -> WindowsPerformanceMonitor:
    if performance_monitor is None:
        raise RuntimeError("Performance monitor not initialized")
    return performance_monitor