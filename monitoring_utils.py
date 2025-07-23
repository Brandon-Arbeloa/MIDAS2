"""
MIDAS Monitoring Utilities
Enhanced error handling and process monitoring for Windows 11
"""

import os
import sys
import time
import json
import logging
import psutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import win32api
import win32con
import win32event
import win32process
import win32evtlog
import win32evtlogutil
import winerror
from contextlib import contextmanager

# Configure logging
log_dir = Path(__file__).parent / 'logs' / 'monitoring'
log_dir.mkdir(parents=True, exist_ok=True)

# Setup logger with both file and Windows Event Log handlers
logger = logging.getLogger('MIDAS.Monitoring')
logger.setLevel(logging.DEBUG)

# File handler
file_handler = logging.FileHandler(
    log_dir / f'monitoring_{datetime.now().strftime("%Y%m%d")}.log'
)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

class WindowsEventLogger:
    """Write to Windows Event Log"""
    
    def __init__(self, app_name: str = "MIDAS"):
        self.app_name = app_name
        self._register_event_source()
    
    def _register_event_source(self):
        """Register application with Windows Event Log"""
        try:
            # Try to register the event source
            win32evtlogutil.AddSourceToRegistry(
                self.app_name,
                msgDLL=sys.executable,
                eventLogType="Application"
            )
        except Exception as e:
            logger.warning(f"Could not register event source: {e}")
    
    def log_event(self, message: str, event_type: int = win32evtlog.EVENTLOG_INFORMATION_TYPE,
                  event_id: int = 1000):
        """Log an event to Windows Event Log"""
        try:
            win32evtlogutil.ReportEvent(
                self.app_name,
                event_id,
                eventType=event_type,
                strings=[message],
                data=None
            )
        except Exception as e:
            logger.error(f"Failed to write to Windows Event Log: {e}")
    
    def log_error(self, message: str):
        """Log error to Windows Event Log"""
        self.log_event(message, win32evtlog.EVENTLOG_ERROR_TYPE, 1001)
    
    def log_warning(self, message: str):
        """Log warning to Windows Event Log"""
        self.log_event(message, win32evtlog.EVENTLOG_WARNING_TYPE, 1002)
    
    def log_info(self, message: str):
        """Log info to Windows Event Log"""
        self.log_event(message, win32evtlog.EVENTLOG_INFORMATION_TYPE, 1000)

# Global Windows Event Logger
win_logger = WindowsEventLogger()

class ProcessMonitor:
    """Monitor and manage Windows processes"""
    
    def __init__(self):
        self.monitored_processes = {}
    
    def start_process(self, name: str, command: List[str], 
                     cwd: Optional[str] = None) -> Optional[int]:
        """Start a process and monitor it"""
        try:
            # Create process with Windows API for better control
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startup_info,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            self.monitored_processes[name] = {
                'pid': process.pid,
                'process': process,
                'command': command,
                'started_at': datetime.now(),
                'status': 'running'
            }
            
            logger.info(f"Started process '{name}' with PID {process.pid}")
            win_logger.log_info(f"MIDAS: Started {name} (PID: {process.pid})")
            
            return process.pid
            
        except Exception as e:
            logger.error(f"Failed to start process '{name}': {e}")
            win_logger.log_error(f"MIDAS: Failed to start {name}: {str(e)}")
            return None
    
    def stop_process(self, name: str, timeout: int = 10) -> bool:
        """Stop a monitored process gracefully"""
        if name not in self.monitored_processes:
            logger.warning(f"Process '{name}' not found in monitored processes")
            return False
        
        proc_info = self.monitored_processes[name]
        process = proc_info['process']
        
        try:
            # Try graceful termination first
            process.terminate()
            
            # Wait for process to terminate
            try:
                process.wait(timeout=timeout)
                logger.info(f"Process '{name}' terminated gracefully")
                win_logger.log_info(f"MIDAS: Stopped {name} gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful termination fails
                process.kill()
                logger.warning(f"Process '{name}' force killed after timeout")
                win_logger.log_warning(f"MIDAS: Force killed {name} after timeout")
            
            proc_info['status'] = 'stopped'
            proc_info['stopped_at'] = datetime.now()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop process '{name}': {e}")
            win_logger.log_error(f"MIDAS: Failed to stop {name}: {str(e)}")
            return False
    
    def check_process_health(self, name: str) -> Dict[str, Any]:
        """Check health of a monitored process"""
        if name not in self.monitored_processes:
            return {'status': 'not_found', 'error': 'Process not monitored'}
        
        proc_info = self.monitored_processes[name]
        pid = proc_info['pid']
        
        try:
            # Check if process exists
            proc = psutil.Process(pid)
            
            # Get process info
            with proc.oneshot():
                health = {
                    'status': 'running' if proc.is_running() else 'stopped',
                    'pid': pid,
                    'name': proc.name(),
                    'cpu_percent': proc.cpu_percent(interval=1),
                    'memory_percent': proc.memory_percent(),
                    'memory_info': proc.memory_info()._asdict(),
                    'num_threads': proc.num_threads(),
                    'create_time': datetime.fromtimestamp(proc.create_time()),
                    'uptime': (datetime.now() - datetime.fromtimestamp(proc.create_time())).total_seconds()
                }
                
                # Windows-specific info
                if sys.platform == 'win32':
                    health['num_handles'] = proc.num_handles()
                
            return health
            
        except psutil.NoSuchProcess:
            proc_info['status'] = 'stopped'
            return {'status': 'stopped', 'error': 'Process no longer exists'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def restart_process(self, name: str) -> bool:
        """Restart a monitored process"""
        if name not in self.monitored_processes:
            logger.error(f"Cannot restart unknown process '{name}'")
            return False
        
        proc_info = self.monitored_processes[name]
        
        # Stop the process
        self.stop_process(name)
        
        # Wait a bit
        time.sleep(2)
        
        # Start it again
        pid = self.start_process(
            name,
            proc_info['command'],
            cwd=proc_info.get('cwd')
        )
        
        return pid is not None
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all monitored processes"""
        status = {}
        for name in self.monitored_processes:
            status[name] = self.check_process_health(name)
        return status

class ServiceManager:
    """Manage Windows services"""
    
    @staticmethod
    def get_service_status(service_name: str) -> Dict[str, Any]:
        """Get detailed service status"""
        try:
            result = subprocess.run(
                ['sc', 'query', service_name],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode != 0:
                return {'status': 'not_found', 'error': 'Service not found'}
            
            # Parse output
            output = result.stdout
            status_info = {}
            
            if 'RUNNING' in output:
                status_info['state'] = 'running'
            elif 'STOPPED' in output:
                status_info['state'] = 'stopped'
            elif 'PAUSED' in output:
                status_info['state'] = 'paused'
            else:
                status_info['state'] = 'unknown'
            
            # Get additional info
            config_result = subprocess.run(
                ['sc', 'qc', service_name],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if config_result.returncode == 0:
                config_output = config_result.stdout
                
                # Extract start type
                if 'AUTO_START' in config_output:
                    status_info['start_type'] = 'automatic'
                elif 'DEMAND_START' in config_output:
                    status_info['start_type'] = 'manual'
                elif 'DISABLED' in config_output:
                    status_info['start_type'] = 'disabled'
                
                # Extract binary path
                for line in config_output.split('\n'):
                    if 'BINARY_PATH_NAME' in line:
                        status_info['binary_path'] = line.split(':', 1)[1].strip()
                        break
            
            return status_info
            
        except Exception as e:
            logger.error(f"Failed to get service status for '{service_name}': {e}")
            return {'status': 'error', 'error': str(e)}
    
    @staticmethod
    def start_service(service_name: str, timeout: int = 30) -> bool:
        """Start a Windows service"""
        try:
            # Check current status
            status = ServiceManager.get_service_status(service_name)
            if status.get('state') == 'running':
                logger.info(f"Service '{service_name}' is already running")
                return True
            
            # Start service
            result = subprocess.run(
                ['net', 'start', service_name],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully started service '{service_name}'")
                win_logger.log_info(f"MIDAS: Started service {service_name}")
                return True
            else:
                logger.error(f"Failed to start service '{service_name}': {result.stderr}")
                win_logger.log_error(f"MIDAS: Failed to start service {service_name}")
                return False
                
        except Exception as e:
            logger.error(f"Exception starting service '{service_name}': {e}")
            return False
    
    @staticmethod
    def stop_service(service_name: str, timeout: int = 30) -> bool:
        """Stop a Windows service"""
        try:
            # Check current status
            status = ServiceManager.get_service_status(service_name)
            if status.get('state') == 'stopped':
                logger.info(f"Service '{service_name}' is already stopped")
                return True
            
            # Stop service
            result = subprocess.run(
                ['net', 'stop', service_name],
                capture_output=True,
                text=True,
                shell=True
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully stopped service '{service_name}'")
                win_logger.log_info(f"MIDAS: Stopped service {service_name}")
                return True
            else:
                logger.error(f"Failed to stop service '{service_name}': {result.stderr}")
                win_logger.log_error(f"MIDAS: Failed to stop service {service_name}")
                return False
                
        except Exception as e:
            logger.error(f"Exception stopping service '{service_name}': {e}")
            return False
    
    @staticmethod
    def restart_service(service_name: str) -> bool:
        """Restart a Windows service"""
        logger.info(f"Restarting service '{service_name}'...")
        
        # Stop service
        if ServiceManager.stop_service(service_name):
            time.sleep(3)  # Wait for service to fully stop
            
            # Start service
            return ServiceManager.start_service(service_name)
        
        return False

class PerformanceMonitor:
    """Monitor system performance metrics"""
    
    def __init__(self):
        self.metrics_history = []
        self.max_history_size = 1000
    
    def collect_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics"""
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'percent': psutil.cpu_percent(interval=1),
                'per_cpu': psutil.cpu_percent(interval=1, percpu=True),
                'freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                'stats': psutil.cpu_stats()._asdict()
            },
            'memory': psutil.virtual_memory()._asdict(),
            'swap': psutil.swap_memory()._asdict(),
            'disk': {},
            'network': {},
            'processes': {
                'total': len(psutil.pids()),
                'running': len([p for p in psutil.process_iter() if p.status() == 'running'])
            }
        }
        
        # Disk usage for all partitions
        for partition in psutil.disk_partitions():
            if partition.fstype:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    metrics['disk'][partition.mountpoint] = usage._asdict()
                except PermissionError:
                    continue
        
        # Network I/O
        net_io = psutil.net_io_counters()
        metrics['network'] = net_io._asdict() if net_io else {}
        
        # Add to history
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history.pop(0)
        
        return metrics
    
    def get_metrics_summary(self, minutes: int = 5) -> Dict[str, Any]:
        """Get summary of metrics over time period"""
        if not self.metrics_history:
            return {}
        
        # Filter metrics for time period
        cutoff_time = datetime.now().timestamp() - (minutes * 60)
        recent_metrics = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m['timestamp']).timestamp() > cutoff_time
        ]
        
        if not recent_metrics:
            return {}
        
        # Calculate averages
        summary = {
            'period_minutes': minutes,
            'sample_count': len(recent_metrics),
            'cpu_avg': sum(m['cpu']['percent'] for m in recent_metrics) / len(recent_metrics),
            'cpu_max': max(m['cpu']['percent'] for m in recent_metrics),
            'memory_avg': sum(m['memory']['percent'] for m in recent_metrics) / len(recent_metrics),
            'memory_max': max(m['memory']['percent'] for m in recent_metrics)
        }
        
        return summary
    
    def check_thresholds(self, cpu_threshold: float = 80, 
                        memory_threshold: float = 85) -> List[Dict]:
        """Check if metrics exceed thresholds"""
        alerts = []
        current = self.collect_metrics()
        
        # CPU check
        if current['cpu']['percent'] > cpu_threshold:
            alert = {
                'type': 'cpu',
                'severity': 'warning' if current['cpu']['percent'] < 90 else 'critical',
                'message': f"CPU usage is {current['cpu']['percent']}%",
                'value': current['cpu']['percent'],
                'threshold': cpu_threshold
            }
            alerts.append(alert)
            win_logger.log_warning(alert['message'])
        
        # Memory check
        if current['memory']['percent'] > memory_threshold:
            alert = {
                'type': 'memory',
                'severity': 'warning' if current['memory']['percent'] < 95 else 'critical',
                'message': f"Memory usage is {current['memory']['percent']}%",
                'value': current['memory']['percent'],
                'threshold': memory_threshold
            }
            alerts.append(alert)
            win_logger.log_warning(alert['message'])
        
        # Disk check
        for mount, usage in current['disk'].items():
            if usage['percent'] > 90:
                alert = {
                    'type': 'disk',
                    'severity': 'warning' if usage['percent'] < 95 else 'critical',
                    'message': f"Disk usage on {mount} is {usage['percent']}%",
                    'value': usage['percent'],
                    'threshold': 90,
                    'mount': mount
                }
                alerts.append(alert)
                win_logger.log_warning(alert['message'])
        
        return alerts

@contextmanager
def monitor_operation(operation_name: str):
    """Context manager to monitor and log operations"""
    start_time = time.time()
    logger.info(f"Starting operation: {operation_name}")
    
    try:
        yield
        duration = time.time() - start_time
        logger.info(f"Completed operation: {operation_name} (duration: {duration:.2f}s)")
        win_logger.log_info(f"MIDAS: Completed {operation_name} in {duration:.2f}s")
        
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Failed operation: {operation_name} (duration: {duration:.2f}s) - Error: {e}")
        win_logger.log_error(f"MIDAS: Failed {operation_name} - {str(e)}")
        raise

# Global instances
process_monitor = ProcessMonitor()
performance_monitor = PerformanceMonitor()

def log_system_startup():
    """Log system startup to Windows Event Log"""
    win_logger.log_info("MIDAS Monitoring System Started")
    
    # Log system info
    system_info = {
        'platform': platform.platform(),
        'processor': platform.processor(),
        'python_version': sys.version,
        'psutil_version': psutil.__version__
    }
    
    logger.info(f"System info: {json.dumps(system_info, indent=2)}")

# Initialize on import
log_system_startup()