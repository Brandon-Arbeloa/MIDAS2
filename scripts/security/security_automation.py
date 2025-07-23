#!/usr/bin/env python3
"""
MIDAS Security Automation
Comprehensive security automation and incident response for Windows 11 deployment
"""

import os
import sys
import json
import logging
import subprocess
import threading
import time
import smtplib
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import hashlib
import psutil
import win32api
import win32security
import win32evtlog
import win32evtlogutil
import win32service
import win32serviceutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('C:/MIDAS/logs/security_automation.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@dataclass
class SecurityConfig:
    """Security automation configuration"""
    monitoring_interval: int = 60
    enable_email_alerts: bool = False
    email_smtp_server: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_recipients: List[str] = None
    slack_webhook_url: str = ""
    max_cpu_threshold: int = 90
    max_memory_threshold: int = 90
    max_failed_logins: int = 5
    quarantine_directory: str = "C:/MIDAS/quarantine"
    backup_directory: str = "C:/MIDAS/security_backups"
    log_directory: str = "C:/MIDAS/logs"
    enable_auto_response: bool = True
    powershell_script_path: str = "C:/Users/Rolando Fender/MIDAS/scripts/security/incident_response.ps1"

class SecurityAutomation:
    """Main security automation system"""
    
    def __init__(self, config: SecurityConfig = None):
        self.config = config or SecurityConfig()
        self.monitoring_active = False
        self.monitoring_thread = None
        self.incident_counter = 0
        
        # Initialize directories
        self._ensure_directories()
        
        # Email configuration
        self.email_configured = self._check_email_config()
        
        # Slack configuration
        self.slack_configured = bool(self.config.slack_webhook_url)
        
        # PowerShell script availability
        self.powershell_available = self._check_powershell_script()
        
        logger.info("Security automation system initialized")
    
    def _ensure_directories(self):
        """Ensure required directories exist"""
        directories = [
            self.config.quarantine_directory,
            self.config.backup_directory,
            self.config.log_directory
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    def _check_email_config(self) -> bool:
        """Check if email configuration is valid"""
        return (
            self.config.enable_email_alerts and
            self.config.email_smtp_server and
            self.config.email_username and
            self.config.email_password and
            self.config.email_recipients
        )
    
    def _check_powershell_script(self) -> bool:
        """Check if PowerShell script is available"""
        return Path(self.config.powershell_script_path).exists()
    
    def send_alert(self, subject: str, body: str, severity: str = "Medium"):
        """Send security alert via multiple channels"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_message = f"[{timestamp}] [{severity}] {subject}\n\n{body}"
        
        logger.warning(f"SECURITY ALERT [{severity}]: {subject}")
        
        # Email alert
        if self.email_configured:
            self._send_email_alert(subject, alert_message, severity)
        
        # Slack alert
        if self.slack_configured:
            self._send_slack_alert(subject, alert_message, severity)
        
        # Windows Event Log
        self._log_to_windows_event(subject, alert_message, severity)
        
        # Windows notification (if available)
        self._send_windows_notification(subject, body[:100])
    
    def _send_email_alert(self, subject: str, body: str, severity: str):
        """Send email alert"""
        try:
            msg = MimeMultipart()
            msg['From'] = self.config.email_username
            msg['To'] = ', '.join(self.config.email_recipients)
            msg['Subject'] = f"[MIDAS Security Alert - {severity}] {subject}"
            
            email_body = f"""
MIDAS Security Alert

Severity: {severity}
Host: {os.environ.get('COMPUTERNAME', 'Unknown')}
User: {os.environ.get('USERNAME', 'Unknown')}

{body}

This is an automated alert from the MIDAS security system.
            """.strip()
            
            msg.attach(MimeText(email_body, 'plain'))
            
            server = smtplib.SMTP(self.config.email_smtp_server, self.config.email_smtp_port)
            server.starttls()
            server.login(self.config.email_username, self.config.email_password)
            server.sendmail(self.config.email_username, self.config.email_recipients, msg.as_string())
            server.quit()
            
            logger.info("Email alert sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    def _send_slack_alert(self, subject: str, body: str, severity: str):
        """Send Slack alert"""
        try:
            color_map = {
                "Critical": "danger",
                "High": "warning",
                "Medium": "good",
                "Low": "good"
            }
            
            payload = {
                "text": ":warning: MIDAS Security Alert",
                "attachments": [
                    {
                        "color": color_map.get(severity, "good"),
                        "fields": [
                            {"title": "Severity", "value": severity, "short": True},
                            {"title": "Host", "value": os.environ.get('COMPUTERNAME', 'Unknown'), "short": True},
                            {"title": "Subject", "value": subject, "short": False},
                            {"title": "Details", "value": body[:500], "short": False}
                        ],
                        "footer": "MIDAS Security",
                        "ts": int(time.time())
                    }
                ]
            }
            
            response = requests.post(self.config.slack_webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info("Slack alert sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
    
    def _log_to_windows_event(self, subject: str, body: str, severity: str):
        """Log alert to Windows Event Log"""
        try:
            source = "MIDAS_Security"
            
            # Register event source if it doesn't exist
            try:
                win32evtlogutil.AddSourceToRegistry(
                    source,
                    "Application",
                    "C:\\Windows\\System32\\EventLog.dll"
                )
            except:
                pass  # Source might already exist
            
            # Determine event type
            event_type_map = {
                "Critical": win32evtlog.EVENTLOG_ERROR_TYPE,
                "High": win32evtlog.EVENTLOG_ERROR_TYPE,
                "Medium": win32evtlog.EVENTLOG_WARNING_TYPE,
                "Low": win32evtlog.EVENTLOG_INFORMATION_TYPE
            }
            
            event_type = event_type_map.get(severity, win32evtlog.EVENTLOG_INFORMATION_TYPE)
            
            win32evtlogutil.ReportEvent(
                source,
                1000,
                eventType=event_type,
                strings=[f"{subject}\n{body}"]
            )
            
        except Exception as e:
            logger.error(f"Failed to log to Windows Event Log: {e}")
    
    def _send_windows_notification(self, title: str, message: str):
        """Send Windows toast notification"""
        try:
            # Try using win10toast if available
            try:
                import win10toast
                toaster = win10toast.ToastNotifier()
                toaster.show_toast(
                    f"MIDAS Security Alert",
                    message,
                    duration=10,
                    threaded=True
                )
            except ImportError:
                # Fallback to PowerShell notification
                ps_command = f'''
                Add-Type -AssemblyName System.Windows.Forms
                [System.Windows.Forms.MessageBox]::Show("{message}", "MIDAS Security Alert", "OK", "Warning")
                '''
                subprocess.run(['powershell', '-Command', ps_command], 
                             capture_output=True, timeout=10)
                
        except Exception as e:
            logger.debug(f"Windows notification failed: {e}")
    
    def monitor_system_performance(self) -> Dict[str, Any]:
        """Monitor system performance metrics"""
        try:
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Get disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Get network connections
            connections = len(psutil.net_connections())
            
            # Get running processes count
            process_count = len(psutil.pids())
            
            performance = {
                'timestamp': datetime.now().isoformat(),
                'cpu_percent': cpu_percent,
                'memory_percent': memory_percent,
                'disk_percent': disk_percent,
                'network_connections': connections,
                'process_count': process_count
            }
            
            # Check thresholds
            alerts = []
            
            if cpu_percent > self.config.max_cpu_threshold:
                alerts.append(f"High CPU usage: {cpu_percent:.1f}%")
            
            if memory_percent > self.config.max_memory_threshold:
                alerts.append(f"High memory usage: {memory_percent:.1f}%")
            
            if disk_percent > 90:  # Fixed threshold for disk
                alerts.append(f"High disk usage: {disk_percent:.1f}%")
            
            if alerts:
                alert_body = "System performance alerts:\n\n" + "\n".join(alerts)
                self.send_alert("System Performance Alert", alert_body, "Medium")
            
            return performance
            
        except Exception as e:
            logger.error(f"Failed to monitor system performance: {e}")
            return {}
    
    def check_failed_logins(self) -> List[Dict[str, Any]]:
        """Check for failed login attempts in Windows Security log"""
        failed_logins = []
        
        try:
            # Open Security event log
            server = None
            logtype = "Security"
            hand = win32evtlog.OpenEventLog(server, logtype)
            
            # Look for events from the last hour
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
            
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            
            event_count = 0
            while event_count < 100:  # Limit to prevent excessive processing
                try:
                    event_records = win32evtlog.ReadEventLog(hand, flags, 0)
                    if not event_records:
                        break
                    
                    for event in event_records:
                        event_time = datetime.fromtimestamp(int(event.TimeGenerated))
                        
                        if event_time < start_time:
                            break
                        
                        # Event ID 4625 = Account failed to log on
                        if event.EventID == 4625:
                            failed_logins.append({
                                'timestamp': event_time.isoformat(),
                                'event_id': event.EventID,
                                'computer': event.ComputerName,
                                'source': event.SourceName
                            })
                        
                        event_count += 1
                        
                except Exception:
                    break
            
            win32evtlog.CloseEventLog(hand)
            
            # Check threshold
            if len(failed_logins) > self.config.max_failed_logins:
                alert_body = f"Excessive failed login attempts detected: {len(failed_logins)} failures in the last hour"
                self.send_alert("Failed Login Alert", alert_body, "High")
            
        except Exception as e:
            logger.error(f"Failed to check login events: {e}")
        
        return failed_logins
    
    def check_suspicious_processes(self) -> List[Dict[str, Any]]:
        """Check for suspicious processes"""
        suspicious_processes = []
        
        try:
            # Define suspicious process characteristics
            suspicious_names = [
                'cmd.exe', 'powershell.exe', 'wscript.exe', 'cscript.exe',
                'mshta.exe', 'regsvr32.exe', 'rundll32.exe'
            ]
            
            for process in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'create_time']):
                try:
                    pinfo = process.info
                    
                    # Check for suspicious process names with high resource usage
                    if (pinfo['name'].lower() in suspicious_names and 
                        pinfo['cpu_percent'] > 50):
                        
                        suspicious_processes.append({
                            'pid': pinfo['pid'],
                            'name': pinfo['name'],
                            'cpu_percent': pinfo['cpu_percent'],
                            'memory_percent': pinfo['memory_percent'],
                            'create_time': datetime.fromtimestamp(pinfo['create_time']).isoformat()
                        })
                
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if suspicious_processes:
                alert_body = f"Suspicious processes detected:\n\n"
                for proc in suspicious_processes:
                    alert_body += f"- {proc['name']} (PID: {proc['pid']}) - CPU: {proc['cpu_percent']:.1f}%\n"
                
                self.send_alert("Suspicious Processes Detected", alert_body, "High")
                
                # Auto-response: terminate if enabled
                if self.config.enable_auto_response:
                    for proc in suspicious_processes:
                        self.terminate_process(proc['pid'], f"Auto-termination: suspicious process {proc['name']}")
        
        except Exception as e:
            logger.error(f"Failed to check suspicious processes: {e}")
        
        return suspicious_processes
    
    def terminate_process(self, pid: int, reason: str = "Security threat") -> bool:
        """Terminate a suspicious process"""
        try:
            process = psutil.Process(pid)
            process_name = process.name()
            
            logger.warning(f"Terminating process: {process_name} (PID: {pid}) - {reason}")
            
            # Try graceful termination first
            process.terminate()
            
            # Wait for termination
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                # Force kill if graceful termination fails
                process.kill()
                process.wait(timeout=5)
            
            alert_body = f"Process terminated:\nName: {process_name}\nPID: {pid}\nReason: {reason}"
            self.send_alert("Process Terminated", alert_body, "Medium")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to terminate process {pid}: {e}")
            return False
    
    def quarantine_file(self, file_path: str, reason: str = "Suspicious file detected") -> bool:
        """Quarantine a suspicious file"""
        try:
            source_path = Path(file_path)
            if not source_path.exists():
                logger.warning(f"File not found for quarantine: {file_path}")
                return False
            
            # Create quarantine filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            quarantine_filename = f"{timestamp}_{source_path.name}"
            quarantine_path = Path(self.config.quarantine_directory) / quarantine_filename
            
            # Move file to quarantine
            source_path.rename(quarantine_path)
            
            # Create metadata file
            metadata = {
                'original_path': str(source_path),
                'quarantine_time': datetime.now().isoformat(),
                'reason': reason,
                'file_hash': self._calculate_file_hash(quarantine_path)
            }
            
            metadata_path = quarantine_path.with_suffix(quarantine_path.suffix + '.metadata')
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            alert_body = f"File quarantined:\nOriginal: {file_path}\nQuarantine: {quarantine_path}\nReason: {reason}"
            self.send_alert("File Quarantined", alert_body, "Medium")
            
            logger.info(f"File quarantined: {file_path} -> {quarantine_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to quarantine file {file_path}: {e}")
            return False
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""
    
    def run_powershell_incident_response(self, incident_type: str, details: Dict[str, Any] = None) -> bool:
        """Run PowerShell incident response script"""
        if not self.powershell_available:
            logger.error("PowerShell incident response script not available")
            return False
        
        try:
            # Prepare PowerShell command
            details_json = json.dumps(details or {}).replace('"', '\\"')
            
            ps_command = f'''
            Import-Module "{self.config.powershell_script_path}" -Force
            $details = '{details_json}' | ConvertFrom-Json
            Start-IncidentResponse -IncidentType "{incident_type}" -IncidentDetails $details
            '''
            
            # Execute PowerShell script
            result = subprocess.run([
                'powershell', '-ExecutionPolicy', 'Bypass', '-Command', ps_command
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info(f"PowerShell incident response completed: {incident_type}")
                return True
            else:
                logger.error(f"PowerShell incident response failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to run PowerShell incident response: {e}")
            return False
    
    def automated_response(self, threat_type: str, details: Dict[str, Any]):
        """Execute automated response based on threat type"""
        if not self.config.enable_auto_response:
            logger.info(f"Auto-response disabled for threat: {threat_type}")
            return
        
        logger.info(f"Executing automated response for threat: {threat_type}")
        
        try:
            if threat_type == "suspicious_process":
                if 'pid' in details:
                    self.terminate_process(details['pid'], "Automated response to suspicious process")
                
                # Run PowerShell incident response
                self.run_powershell_incident_response("SuspiciousProcess", details)
            
            elif threat_type == "suspicious_file":
                if 'file_path' in details:
                    self.quarantine_file(details['file_path'], "Automated response to suspicious file")
                
                # Run PowerShell incident response
                self.run_powershell_incident_response("MalwareDetected", details)
            
            elif threat_type == "failed_logins":
                # Run PowerShell incident response for authentication threats
                self.run_powershell_incident_response("SuspiciousNetwork", details)
            
            elif threat_type == "performance_issue":
                # Log performance issue and collect system info
                self.run_powershell_incident_response("SecurityBreach", {**details, "Severity": "Medium"})
            
            else:
                logger.warning(f"No automated response defined for threat type: {threat_type}")
                
        except Exception as e:
            logger.error(f"Automated response failed for {threat_type}: {e}")
    
    def monitoring_loop(self):
        """Main monitoring loop"""
        logger.info("Starting security monitoring loop")
        
        while self.monitoring_active:
            try:
                # Monitor system performance
                performance = self.monitor_system_performance()
                
                # Check for failed logins
                failed_logins = self.check_failed_logins()
                if len(failed_logins) > self.config.max_failed_logins:
                    self.automated_response("failed_logins", {"count": len(failed_logins), "events": failed_logins})
                
                # Check for suspicious processes
                suspicious_processes = self.check_suspicious_processes()
                if suspicious_processes:
                    for proc in suspicious_processes:
                        self.automated_response("suspicious_process", proc)
                
                # Check system performance thresholds
                if performance:
                    if (performance.get('cpu_percent', 0) > self.config.max_cpu_threshold or
                        performance.get('memory_percent', 0) > self.config.max_memory_threshold):
                        self.automated_response("performance_issue", performance)
                
                # Sleep until next check
                time.sleep(self.config.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.config.monitoring_interval)
        
        logger.info("Security monitoring loop stopped")
    
    def start_monitoring(self):
        """Start continuous security monitoring"""
        if self.monitoring_active:
            logger.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        logger.info("Security monitoring started")
    
    def stop_monitoring(self):
        """Stop security monitoring"""
        if not self.monitoring_active:
            logger.warning("Monitoring not active")
            return
        
        self.monitoring_active = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=10)
        
        logger.info("Security monitoring stopped")
    
    def manual_security_scan(self) -> Dict[str, Any]:
        """Perform manual comprehensive security scan"""
        logger.info("Starting manual security scan")
        
        try:
            scan_results = {
                'timestamp': datetime.now().isoformat(),
                'performance': self.monitor_system_performance(),
                'failed_logins': self.check_failed_logins(),
                'suspicious_processes': self.check_suspicious_processes(),
                'incidents': []
            }
            
            # Run PowerShell security check
            if self.powershell_available:
                ps_result = self.run_powershell_incident_response("SecurityBreach", {"Severity": "Medium"})
                scan_results['powershell_scan'] = ps_result
            
            # Generate summary
            issues = []
            if scan_results['failed_logins']:
                issues.append(f"{len(scan_results['failed_logins'])} failed login attempts")
            
            if scan_results['suspicious_processes']:
                issues.append(f"{len(scan_results['suspicious_processes'])} suspicious processes")
            
            if issues:
                summary = f"Security scan completed with issues: {', '.join(issues)}"
                self.send_alert("Security Scan Results", summary, "Medium")
            else:
                logger.info("Security scan completed - no issues detected")
            
            # Save scan results
            results_file = Path(self.config.log_directory) / f"security_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, 'w') as f:
                json.dump(scan_results, f, indent=2, default=str)
            
            return scan_results
            
        except Exception as e:
            logger.error(f"Manual security scan failed: {e}")
            return {'error': str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current security automation status"""
        return {
            'monitoring_active': self.monitoring_active,
            'monitoring_interval': self.config.monitoring_interval,
            'email_configured': self.email_configured,
            'slack_configured': self.slack_configured,
            'powershell_available': self.powershell_available,
            'auto_response_enabled': self.config.enable_auto_response,
            'incident_count': self.incident_counter,
            'directories': {
                'quarantine': self.config.quarantine_directory,
                'backup': self.config.backup_directory,
                'logs': self.config.log_directory
            }
        }

def main():
    """Main function for command-line execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MIDAS Security Automation")
    parser.add_argument('--start', action='store_true', help='Start monitoring')
    parser.add_argument('--stop', action='store_true', help='Stop monitoring')
    parser.add_argument('--scan', action='store_true', help='Run manual security scan')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--config', type=str, help='Configuration file path')
    
    args = parser.parse_args()
    
    # Load configuration
    config = SecurityConfig()
    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
    
    # Initialize security automation
    security = SecurityAutomation(config)
    
    try:
        if args.start:
            security.start_monitoring()
            print("Security monitoring started. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        
        elif args.stop:
            security.stop_monitoring()
            print("Security monitoring stopped.")
        
        elif args.scan:
            print("Running security scan...")
            results = security.manual_security_scan()
            print(f"Scan completed. Results saved to logs directory.")
        
        elif args.status:
            status = security.get_status()
            print(json.dumps(status, indent=2))
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\nShutting down...")
        security.stop_monitoring()
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()