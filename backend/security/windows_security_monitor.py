import os
import json
import time
import logging
import threading
import smtplib
import subprocess
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from pathlib import Path
import win32api
import win32con
import win32security
import win32netcon
import win32evtlog
import win32evtlogutil
import win32service
import win32serviceutil
import win32file
import wmi
import psutil

logger = logging.getLogger(__name__)

@dataclass
class SecurityAlert:
    alert_id: str
    alert_type: str
    severity: str  # low, medium, high, critical
    title: str
    description: str
    timestamp: datetime
    source: str
    details: Dict[str, Any]
    resolved: bool = False
    resolution_timestamp: Optional[datetime] = None
    resolution_notes: str = ""

@dataclass
class MonitoringConfig:
    check_interval: int = 60  # seconds
    enable_email_alerts: bool = False
    email_smtp_server: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_recipients: List[str] = None
    enable_windows_notifications: bool = True
    enable_event_log: bool = True
    alert_thresholds: Dict[str, int] = None
    monitored_processes: List[str] = None
    monitored_services: List[str] = None
    monitored_ports: List[int] = None

class WindowsSystemMonitor:
    """Monitor Windows system security metrics"""
    
    def __init__(self):
        self.wmi_conn = None
        self.performance_counters = {}
        self._initialize_wmi()
    
    def _initialize_wmi(self):
        """Initialize WMI connection"""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            self.wmi_conn = wmi.WMI()
            logger.info("WMI connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize WMI: {e}")
    
    def get_system_performance(self) -> Dict[str, Any]:
        """Get current system performance metrics"""
        try:
            return {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'network_connections': len(psutil.net_connections()),
                'process_count': len(psutil.pids()),
                'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting system performance: {e}")
            return {}
    
    def get_security_events(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get Windows security events from the last N hours"""
        events = []
        
        try:
            # Open Security event log
            server = None
            logtype = "Security"
            hand = win32evtlog.OpenEventLog(server, logtype)
            
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            
            while True:
                event_records = win32evtlog.ReadEventLog(hand, flags, 0)
                if not event_records:
                    break
                
                for event in event_records:
                    event_time = datetime.fromtimestamp(int(event.TimeGenerated))
                    
                    if event_time < start_time:
                        break
                    
                    if event_time >= start_time:
                        events.append({
                            'event_id': event.EventID,
                            'event_type': event.EventType,
                            'time_generated': event_time.isoformat(),
                            'source_name': event.SourceName,
                            'computer_name': event.ComputerName,
                            'event_category': event.EventCategory,
                            'strings': event.StringInserts
                        })
            
            win32evtlog.CloseEventLog(hand)
            
        except Exception as e:
            logger.error(f"Error reading security events: {e}")
        
        return events
    
    def check_failed_logins(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Check for failed login attempts"""
        failed_logins = []
        
        try:
            security_events = self.get_security_events(hours)
            
            for event in security_events:
                # Event ID 4625 = Account failed to log on
                if event.get('event_id') == 4625:
                    failed_logins.append(event)
        
        except Exception as e:
            logger.error(f"Error checking failed logins: {e}")
        
        return failed_logins
    
    def check_service_status(self, service_names: List[str]) -> Dict[str, str]:
        """Check status of critical services"""
        service_status = {}
        
        for service_name in service_names:
            try:
                # Get service status
                status = win32serviceutil.QueryServiceStatus(service_name)
                
                if status[1] == win32service.SERVICE_RUNNING:
                    service_status[service_name] = "running"
                elif status[1] == win32service.SERVICE_STOPPED:
                    service_status[service_name] = "stopped"
                else:
                    service_status[service_name] = "unknown"
                    
            except Exception as e:
                logger.error(f"Error checking service {service_name}: {e}")
                service_status[service_name] = "error"
        
        return service_status
    
    def check_disk_space(self, threshold_percent: int = 90) -> Dict[str, Any]:
        """Check disk space usage"""
        disk_alerts = {}
        
        try:
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    percent_used = (usage.used / usage.total) * 100
                    
                    if percent_used > threshold_percent:
                        disk_alerts[partition.device] = {
                            'percent_used': round(percent_used, 2),
                            'total_gb': round(usage.total / (1024**3), 2),
                            'used_gb': round(usage.used / (1024**3), 2),
                            'free_gb': round(usage.free / (1024**3), 2)
                        }
                        
                except PermissionError:
                    continue
                    
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")
        
        return disk_alerts
    
    def check_network_connections(self, suspicious_ports: List[int] = None) -> Dict[str, Any]:
        """Check for suspicious network connections"""
        if suspicious_ports is None:
            suspicious_ports = [1433, 3389, 5432, 6379, 27017]  # Common database/remote ports
        
        suspicious_connections = []
        connection_summary = {}
        
        try:
            connections = psutil.net_connections(kind='inet')
            
            # Count connections by state
            for conn in connections:
                state = conn.status
                if state not in connection_summary:
                    connection_summary[state] = 0
                connection_summary[state] += 1
                
                # Check for suspicious ports
                if conn.laddr and conn.laddr.port in suspicious_ports:
                    suspicious_connections.append({
                        'local_addr': f"{conn.laddr.ip}:{conn.laddr.port}",
                        'remote_addr': f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A",
                        'status': conn.status,
                        'pid': conn.pid
                    })
            
        except Exception as e:
            logger.error(f"Error checking network connections: {e}")
        
        return {
            'summary': connection_summary,
            'suspicious_connections': suspicious_connections
        }

class WindowsSecurityAlertManager:
    """Manage security alerts and notifications"""
    
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.alerts = []
        self.alert_history = []
        self.max_alerts = 1000
        self._setup_email()
    
    def _setup_email(self):
        """Setup email configuration"""
        self.email_configured = (
            self.config.enable_email_alerts and
            self.config.email_smtp_server and
            self.config.email_username and
            self.config.email_recipients
        )
        
        if not self.email_configured and self.config.enable_email_alerts:
            logger.warning("Email alerts enabled but not properly configured")
    
    def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        source: str,
        details: Dict[str, Any] = None
    ) -> SecurityAlert:
        """Create a new security alert"""
        
        alert = SecurityAlert(
            alert_id=f"{alert_type}_{int(time.time())}",
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            timestamp=datetime.now(),
            source=source,
            details=details or {}
        )
        
        # Add to alerts list
        self.alerts.append(alert)
        
        # Rotate alerts if too many
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts//2:]
        
        # Send notifications
        self._send_alert_notifications(alert)
        
        logger.info(f"Created {severity} alert: {title}")
        return alert
    
    def resolve_alert(self, alert_id: str, resolution_notes: str = ""):
        """Resolve an alert"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolution_timestamp = datetime.now()
                alert.resolution_notes = resolution_notes
                
                # Move to history
                self.alert_history.append(alert)
                self.alerts.remove(alert)
                
                logger.info(f"Resolved alert: {alert_id}")
                return True
        
        return False
    
    def _send_alert_notifications(self, alert: SecurityAlert):
        """Send alert notifications"""
        
        # Send Windows notification
        if self.config.enable_windows_notifications:
            self._send_windows_notification(alert)
        
        # Send email notification
        if self.email_configured and alert.severity in ['high', 'critical']:
            self._send_email_notification(alert)
        
        # Log to Windows Event Log
        if self.config.enable_event_log:
            self._log_to_event_log(alert)
    
    def _send_windows_notification(self, alert: SecurityAlert):
        """Send Windows toast notification"""
        try:
            import win10toast
            toaster = win10toast.ToastNotifier()
            
            toaster.show_toast(
                f"MIDAS Security Alert - {alert.severity.upper()}",
                alert.description[:100],
                duration=10,
                threaded=True
            )
        except ImportError:
            # Fallback to message box
            try:
                import win32gui
                win32gui.MessageBox(
                    0,
                    f"{alert.title}\n\n{alert.description}",
                    f"MIDAS Security Alert - {alert.severity.upper()}",
                    0x40  # MB_ICONINFORMATION
                )
            except Exception as e:
                logger.error(f"Failed to show notification: {e}")
    
    def _send_email_notification(self, alert: SecurityAlert):
        """Send email alert notification"""
        try:
            msg = MimeMultipart()
            msg['From'] = self.config.email_username
            msg['To'] = ', '.join(self.config.email_recipients)
            msg['Subject'] = f"MIDAS Security Alert - {alert.severity.upper()}: {alert.title}"
            
            body = f"""
            MIDAS Security Alert
            
            Alert Type: {alert.alert_type}
            Severity: {alert.severity.upper()}
            Title: {alert.title}
            Description: {alert.description}
            Source: {alert.source}
            Timestamp: {alert.timestamp}
            
            Details:
            {json.dumps(alert.details, indent=2)}
            
            Alert ID: {alert.alert_id}
            """
            
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(self.config.email_smtp_server, self.config.email_smtp_port)
            server.starttls()
            server.login(self.config.email_username, self.config.email_password)
            
            text = msg.as_string()
            server.sendmail(self.config.email_username, self.config.email_recipients, text)
            server.quit()
            
            logger.info(f"Email alert sent for {alert.alert_id}")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    def _log_to_event_log(self, alert: SecurityAlert):
        """Log alert to Windows Event Log"""
        try:
            # Determine event type
            if alert.severity == 'critical':
                event_type = win32evtlog.EVENTLOG_ERROR_TYPE
            elif alert.severity == 'high':
                event_type = win32evtlog.EVENTLOG_ERROR_TYPE
            elif alert.severity == 'medium':
                event_type = win32evtlog.EVENTLOG_WARNING_TYPE
            else:
                event_type = win32evtlog.EVENTLOG_INFORMATION_TYPE
            
            message = f"{alert.title}\n{alert.description}\nSource: {alert.source}"
            
            win32evtlogutil.ReportEvent(
                "MIDAS_Security_Monitor",
                2000,  # Event ID
                eventType=event_type,
                strings=[message]
            )
            
        except Exception as e:
            logger.error(f"Failed to log to Event Log: {e}")
    
    def get_active_alerts(self, severity_filter: str = None) -> List[SecurityAlert]:
        """Get active alerts, optionally filtered by severity"""
        if severity_filter:
            return [alert for alert in self.alerts if alert.severity == severity_filter]
        return self.alerts.copy()
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics"""
        active_alerts = len(self.alerts)
        resolved_alerts = len(self.alert_history)
        
        severity_counts = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        for alert in self.alerts:
            severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1
        
        return {
            'active_alerts': active_alerts,
            'resolved_alerts': resolved_alerts,
            'severity_distribution': severity_counts,
            'latest_alert': self.alerts[-1].timestamp.isoformat() if self.alerts else None
        }

class WindowsSecurityMonitor:
    """Comprehensive Windows security monitoring system"""
    
    def __init__(self, config: MonitoringConfig = None):
        self.config = config or MonitoringConfig()
        self.system_monitor = WindowsSystemMonitor()
        self.alert_manager = WindowsSecurityAlertManager(self.config)
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Setup default thresholds
        if self.config.alert_thresholds is None:
            self.config.alert_thresholds = {
                'cpu_threshold': 90,
                'memory_threshold': 90,
                'disk_threshold': 90,
                'failed_login_threshold': 5,
                'connection_threshold': 1000
            }
        
        # Setup default monitored services
        if self.config.monitored_services is None:
            self.config.monitored_services = [
                'WinDefend',  # Windows Defender
                'EventLog',   # Event Log
                'Winmgmt',    # WMI
                'LanmanServer', # Server
                'Workstation'   # Workstation
            ]
    
    def start_monitoring(self):
        """Start continuous security monitoring"""
        if self.monitoring_active:
            logger.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        logger.info("Security monitoring started")
    
    def stop_monitoring(self):
        """Stop security monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logger.info("Security monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Perform all security checks
                self._check_system_performance()
                self._check_failed_logins()
                self._check_service_status()
                self._check_disk_space()
                self._check_network_connections()
                
                # Sleep until next check
                time.sleep(self.config.check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.config.check_interval)
    
    def _check_system_performance(self):
        """Check system performance metrics"""
        try:
            performance = self.system_monitor.get_system_performance()
            
            # Check CPU usage
            if performance.get('cpu_percent', 0) > self.config.alert_thresholds['cpu_threshold']:
                self.alert_manager.create_alert(
                    alert_type='system_performance',
                    severity='medium',
                    title='High CPU Usage',
                    description=f"CPU usage at {performance['cpu_percent']}%",
                    source='system_monitor',
                    details=performance
                )
            
            # Check memory usage
            if performance.get('memory_percent', 0) > self.config.alert_thresholds['memory_threshold']:
                self.alert_manager.create_alert(
                    alert_type='system_performance',
                    severity='medium',
                    title='High Memory Usage',
                    description=f"Memory usage at {performance['memory_percent']}%",
                    source='system_monitor',
                    details=performance
                )
            
        except Exception as e:
            logger.error(f"Error checking system performance: {e}")
    
    def _check_failed_logins(self):
        """Check for excessive failed login attempts"""
        try:
            failed_logins = self.system_monitor.check_failed_logins(1)  # Last hour
            
            if len(failed_logins) > self.config.alert_thresholds['failed_login_threshold']:
                self.alert_manager.create_alert(
                    alert_type='authentication',
                    severity='high',
                    title='Multiple Failed Logins',
                    description=f"{len(failed_logins)} failed login attempts in the last hour",
                    source='security_events',
                    details={'failed_logins': failed_logins}
                )
        
        except Exception as e:
            logger.error(f"Error checking failed logins: {e}")
    
    def _check_service_status(self):
        """Check status of critical services"""
        try:
            service_status = self.system_monitor.check_service_status(self.config.monitored_services)
            
            for service_name, status in service_status.items():
                if status != 'running':
                    self.alert_manager.create_alert(
                        alert_type='service_status',
                        severity='high' if service_name in ['WinDefend', 'EventLog'] else 'medium',
                        title=f'Service Not Running: {service_name}',
                        description=f"Critical service {service_name} is {status}",
                        source='service_monitor',
                        details={'service': service_name, 'status': status}
                    )
        
        except Exception as e:
            logger.error(f"Error checking service status: {e}")
    
    def _check_disk_space(self):
        """Check disk space usage"""
        try:
            disk_alerts = self.system_monitor.check_disk_space(self.config.alert_thresholds['disk_threshold'])
            
            for device, usage_info in disk_alerts.items():
                self.alert_manager.create_alert(
                    alert_type='disk_space',
                    severity='medium',
                    title=f'Low Disk Space: {device}',
                    description=f"Disk {device} is {usage_info['percent_used']}% full",
                    source='disk_monitor',
                    details=usage_info
                )
        
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")
    
    def _check_network_connections(self):
        """Check network connections"""
        try:
            network_info = self.system_monitor.check_network_connections(self.config.monitored_ports)
            
            # Check for too many connections
            total_connections = sum(network_info['summary'].values())
            if total_connections > self.config.alert_thresholds['connection_threshold']:
                self.alert_manager.create_alert(
                    alert_type='network_activity',
                    severity='medium',
                    title='High Network Activity',
                    description=f"{total_connections} active network connections",
                    source='network_monitor',
                    details=network_info
                )
            
            # Alert on suspicious connections
            if network_info['suspicious_connections']:
                self.alert_manager.create_alert(
                    alert_type='network_security',
                    severity='high',
                    title='Suspicious Network Connections',
                    description=f"Found {len(network_info['suspicious_connections'])} connections on monitored ports",
                    source='network_monitor',
                    details=network_info
                )
        
        except Exception as e:
            logger.error(f"Error checking network connections: {e}")
    
    def run_security_scan(self) -> Dict[str, Any]:
        """Run a comprehensive security scan"""
        scan_results = {
            'timestamp': datetime.now().isoformat(),
            'scan_duration': 0,
            'findings': []
        }
        
        start_time = time.time()
        
        try:
            # System performance
            performance = self.system_monitor.get_system_performance()
            scan_results['system_performance'] = performance
            
            # Security events
            security_events = self.system_monitor.get_security_events(24)  # Last 24 hours
            scan_results['security_events_24h'] = len(security_events)
            
            # Failed logins
            failed_logins = self.system_monitor.check_failed_logins(24)
            scan_results['failed_logins_24h'] = len(failed_logins)
            
            # Service status
            service_status = self.system_monitor.check_service_status(self.config.monitored_services)
            scan_results['service_status'] = service_status
            
            # Network connections
            network_info = self.system_monitor.check_network_connections(self.config.monitored_ports)
            scan_results['network_connections'] = network_info
            
            # Disk space
            disk_alerts = self.system_monitor.check_disk_space(80)  # Lower threshold for scan
            scan_results['disk_usage'] = disk_alerts
            
        except Exception as e:
            logger.error(f"Error during security scan: {e}")
            scan_results['error'] = str(e)
        
        scan_results['scan_duration'] = round(time.time() - start_time, 2)
        return scan_results
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        return {
            'monitoring_active': self.monitoring_active,
            'check_interval': self.config.check_interval,
            'monitored_services': self.config.monitored_services,
            'monitored_ports': self.config.monitored_ports,
            'alert_summary': self.alert_manager.get_alert_summary(),
            'email_configured': self.alert_manager.email_configured,
            'system_info': self.system_monitor.get_system_performance()
        }

# Global security monitor instance
security_monitor_instance: Optional[WindowsSecurityMonitor] = None

def initialize_security_monitor(config: MonitoringConfig = None) -> WindowsSecurityMonitor:
    """Initialize global security monitor"""
    global security_monitor_instance
    security_monitor_instance = WindowsSecurityMonitor(config)
    return security_monitor_instance

def get_security_monitor() -> WindowsSecurityMonitor:
    """Get global security monitor instance"""
    if security_monitor_instance is None:
        initialize_security_monitor()
    return security_monitor_instance