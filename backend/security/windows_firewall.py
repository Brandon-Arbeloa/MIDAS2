import os
import subprocess
import json
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import win32api
import win32security
import win32net
import winreg

logger = logging.getLogger(__name__)

class FirewallProfile(Enum):
    DOMAIN = "Domain"
    PRIVATE = "Private"
    PUBLIC = "Public"

class FirewallDirection(Enum):
    INBOUND = "Inbound"
    OUTBOUND = "Outbound"

class FirewallAction(Enum):
    ALLOW = "Allow"
    BLOCK = "Block"

@dataclass
class FirewallRule:
    name: str
    direction: FirewallDirection
    action: FirewallAction
    protocol: str = "TCP"
    local_port: Optional[str] = None
    remote_port: Optional[str] = None
    local_address: Optional[str] = None
    remote_address: Optional[str] = None
    program: Optional[str] = None
    service: Optional[str] = None
    profile: Optional[str] = "Any"
    enabled: bool = True
    description: str = ""

@dataclass
class NetworkSecurityConfig:
    enable_firewall: bool = True
    default_inbound_action: str = "Block"
    default_outbound_action: str = "Allow"
    enable_logging: bool = True
    log_dropped_packets: bool = True
    log_successful_connections: bool = False
    allowed_applications: List[str] = None
    blocked_applications: List[str] = None
    allowed_ports: List[int] = None
    blocked_ports: List[int] = None
    trusted_networks: List[str] = None
    suspicious_ip_ranges: List[str] = None

class WindowsFirewallManager:
    """Manage Windows Defender Firewall configuration"""
    
    def __init__(self):
        self.profiles = [FirewallProfile.DOMAIN, FirewallProfile.PRIVATE, FirewallProfile.PUBLIC]
        self._check_firewall_availability()
    
    def _check_firewall_availability(self):
        """Check if Windows Firewall is available and running"""
        try:
            result = self._run_netsh_command(['advfirewall', 'show', 'allprofiles', 'state'])
            self.firewall_available = result['success'] and "State" in result['output']
            
            if not self.firewall_available:
                logger.error("Windows Firewall not available or not running")
        except Exception as e:
            logger.error(f"Failed to check firewall availability: {e}")
            self.firewall_available = False
    
    def _run_netsh_command(self, command_args: List[str]) -> Dict[str, Any]:
        """Run netsh command and return result"""
        try:
            cmd = ['netsh'] + command_args
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                shell=True,
                timeout=30
            )
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout,
                'error': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _run_powershell_command(self, command: str) -> Dict[str, Any]:
        """Run PowerShell command and return result"""
        try:
            result = subprocess.run([
                'powershell', '-Command', command
            ], capture_output=True, text=True, shell=True, timeout=30)
            
            return {
                'success': result.returncode == 0,
                'output': result.stdout.strip(),
                'error': result.stderr.strip(),
                'returncode': result.returncode
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_firewall_status(self) -> Dict[str, Any]:
        """Get current firewall status for all profiles"""
        status = {}
        
        for profile in self.profiles:
            try:
                # Get firewall state
                result = self._run_netsh_command([
                    'advfirewall', 'show', profile.value.lower() + 'profile', 'state'
                ])
                
                if result['success']:
                    state_match = re.search(r'State\s+(\w+)', result['output'])
                    state = state_match.group(1) if state_match else 'Unknown'
                else:
                    state = 'Error'
                
                # Get inbound/outbound settings
                settings_result = self._run_netsh_command([
                    'advfirewall', 'show', profile.value.lower() + 'profile'
                ])
                
                inbound_action = 'Unknown'
                outbound_action = 'Unknown'
                
                if settings_result['success']:
                    inbound_match = re.search(r'Inbound connections:\s+(\w+)', settings_result['output'])
                    outbound_match = re.search(r'Outbound connections:\s+(\w+)', settings_result['output'])
                    
                    if inbound_match:
                        inbound_action = inbound_match.group(1)
                    if outbound_match:
                        outbound_action = outbound_match.group(1)
                
                status[profile.value] = {
                    'enabled': state == 'ON',
                    'state': state,
                    'inbound_action': inbound_action,
                    'outbound_action': outbound_action
                }
                
            except Exception as e:
                logger.error(f"Error getting {profile.value} profile status: {e}")
                status[profile.value] = {'error': str(e)}
        
        return status
    
    def enable_firewall(self, profiles: List[FirewallProfile] = None) -> Dict[str, bool]:
        """Enable Windows Firewall for specified profiles"""
        if profiles is None:
            profiles = self.profiles
        
        results = {}
        
        for profile in profiles:
            try:
                result = self._run_netsh_command([
                    'advfirewall', 'set', profile.value.lower() + 'profile', 'state', 'on'
                ])
                
                results[profile.value] = result['success']
                
                if result['success']:
                    logger.info(f"Enabled firewall for {profile.value} profile")
                else:
                    logger.error(f"Failed to enable firewall for {profile.value}: {result['error']}")
                    
            except Exception as e:
                logger.error(f"Error enabling firewall for {profile.value}: {e}")
                results[profile.value] = False
        
        return results
    
    def configure_default_actions(self, config: NetworkSecurityConfig) -> Dict[str, bool]:
        """Configure default inbound and outbound actions"""
        results = {}
        
        for profile in self.profiles:
            try:
                # Set inbound action
                inbound_result = self._run_netsh_command([
                    'advfirewall', 'set', profile.value.lower() + 'profile',
                    'firewallpolicy', f'{config.default_inbound_action.lower()},{config.default_outbound_action.lower()}'
                ])
                
                results[f"{profile.value}_configured"] = inbound_result['success']
                
                if inbound_result['success']:
                    logger.info(f"Configured {profile.value} profile: IN={config.default_inbound_action}, OUT={config.default_outbound_action}")
                else:
                    logger.error(f"Failed to configure {profile.value} profile: {inbound_result['error']}")
                    
            except Exception as e:
                logger.error(f"Error configuring {profile.value} profile: {e}")
                results[f"{profile.value}_configured"] = False
        
        return results
    
    def add_rule(self, rule: FirewallRule) -> bool:
        """Add a new firewall rule"""
        try:
            # Build netsh command
            cmd_args = [
                'advfirewall', 'firewall', 'add', 'rule',
                f'name={rule.name}',
                f'dir={rule.direction.value}',
                f'action={rule.action.value}',
                f'protocol={rule.protocol}',
                f'profile={rule.profile}',
                f'enable={"yes" if rule.enabled else "no"}'
            ]
            
            # Add optional parameters
            if rule.local_port:
                cmd_args.append(f'localport={rule.local_port}')
            if rule.remote_port:
                cmd_args.append(f'remoteport={rule.remote_port}')
            if rule.local_address:
                cmd_args.append(f'localip={rule.local_address}')
            if rule.remote_address:
                cmd_args.append(f'remoteip={rule.remote_address}')
            if rule.program:
                cmd_args.append(f'program={rule.program}')
            if rule.service:
                cmd_args.append(f'service={rule.service}')
            if rule.description:
                cmd_args.append(f'description={rule.description}')
            
            result = self._run_netsh_command(cmd_args)
            
            if result['success']:
                logger.info(f"Added firewall rule: {rule.name}")
                return True
            else:
                logger.error(f"Failed to add firewall rule {rule.name}: {result['error']}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding firewall rule {rule.name}: {e}")
            return False
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a firewall rule by name"""
        try:
            result = self._run_netsh_command([
                'advfirewall', 'firewall', 'delete', 'rule',
                f'name={rule_name}'
            ])
            
            if result['success']:
                logger.info(f"Removed firewall rule: {rule_name}")
                return True
            else:
                logger.error(f"Failed to remove firewall rule {rule_name}: {result['error']}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing firewall rule {rule_name}: {e}")
            return False
    
    def list_rules(self, direction: FirewallDirection = None) -> List[Dict[str, Any]]:
        """List all firewall rules"""
        try:
            cmd_args = ['advfirewall', 'firewall', 'show', 'rule', 'name=all']
            
            if direction:
                cmd_args.append(f'dir={direction.value}')
            
            result = self._run_netsh_command(cmd_args)
            
            if not result['success']:
                logger.error(f"Failed to list firewall rules: {result['error']}")
                return []
            
            # Parse the output to extract rule information
            rules = []
            current_rule = {}
            
            for line in result['output'].split('\n'):
                line = line.strip()
                if not line:
                    if current_rule:
                        rules.append(current_rule)
                        current_rule = {}
                    continue
                
                if ':' in line:
                    key, value = line.split(':', 1)
                    current_rule[key.strip()] = value.strip()
            
            if current_rule:
                rules.append(current_rule)
            
            return rules
            
        except Exception as e:
            logger.error(f"Error listing firewall rules: {e}")
            return []
    
    def enable_logging(self, log_path: str = None, max_size_kb: int = 4096) -> bool:
        """Enable firewall logging"""
        try:
            if not log_path:
                log_path = "C:\\Windows\\System32\\LogFiles\\Firewall\\pfirewall.log"
            
            # Enable logging for all profiles
            success_count = 0
            for profile in self.profiles:
                # Enable logging
                result1 = self._run_netsh_command([
                    'advfirewall', 'set', profile.value.lower() + 'profile',
                    'logging', 'allowedconnections', 'enable'
                ])
                
                result2 = self._run_netsh_command([
                    'advfirewall', 'set', profile.value.lower() + 'profile',
                    'logging', 'droppedconnections', 'enable'
                ])
                
                result3 = self._run_netsh_command([
                    'advfirewall', 'set', profile.value.lower() + 'profile',
                    'logging', 'filename', log_path
                ])
                
                result4 = self._run_netsh_command([
                    'advfirewall', 'set', profile.value.lower() + 'profile',
                    'logging', 'maxfilesize', str(max_size_kb)
                ])
                
                if all([r['success'] for r in [result1, result2, result3, result4]]):
                    success_count += 1
                    logger.info(f"Enabled logging for {profile.value} profile")
            
            return success_count == len(self.profiles)
            
        except Exception as e:
            logger.error(f"Error enabling firewall logging: {e}")
            return False
    
    def block_ip_address(self, ip_address: str, rule_name: str = None) -> bool:
        """Block specific IP address"""
        if not rule_name:
            rule_name = f"Block_{ip_address.replace('.', '_')}"
        
        rule = FirewallRule(
            name=rule_name,
            direction=FirewallDirection.INBOUND,
            action=FirewallAction.BLOCK,
            protocol="any",
            remote_address=ip_address,
            description=f"Block IP address {ip_address}"
        )
        
        return self.add_rule(rule)
    
    def allow_application(self, program_path: str, rule_name: str = None) -> bool:
        """Allow specific application through firewall"""
        if not rule_name:
            app_name = os.path.basename(program_path).replace('.exe', '')
            rule_name = f"Allow_{app_name}"
        
        # Create rules for both inbound and outbound
        inbound_rule = FirewallRule(
            name=f"{rule_name}_In",
            direction=FirewallDirection.INBOUND,
            action=FirewallAction.ALLOW,
            program=program_path,
            description=f"Allow inbound for {program_path}"
        )
        
        outbound_rule = FirewallRule(
            name=f"{rule_name}_Out",
            direction=FirewallDirection.OUTBOUND,
            action=FirewallAction.ALLOW,
            program=program_path,
            description=f"Allow outbound for {program_path}"
        )
        
        return self.add_rule(inbound_rule) and self.add_rule(outbound_rule)
    
    def allow_port(self, port: int, protocol: str = "TCP", rule_name: str = None) -> bool:
        """Allow specific port through firewall"""
        if not rule_name:
            rule_name = f"Allow_{protocol}_{port}"
        
        rule = FirewallRule(
            name=rule_name,
            direction=FirewallDirection.INBOUND,
            action=FirewallAction.ALLOW,
            protocol=protocol,
            local_port=str(port),
            description=f"Allow {protocol} port {port}"
        )
        
        return self.add_rule(rule)
    
    def reset_to_defaults(self) -> bool:
        """Reset firewall to default configuration"""
        try:
            result = self._run_netsh_command([
                'advfirewall', 'reset'
            ])
            
            if result['success']:
                logger.info("Firewall reset to defaults")
                return True
            else:
                logger.error(f"Failed to reset firewall: {result['error']}")
                return False
                
        except Exception as e:
            logger.error(f"Error resetting firewall: {e}")
            return False

class WindowsNetworkSecurity:
    """Comprehensive Windows network security management"""
    
    def __init__(self, config: NetworkSecurityConfig = None):
        self.config = config or NetworkSecurityConfig()
        self.firewall = WindowsFirewallManager()
        
        # Initialize default values
        self._setup_defaults()
    
    def _setup_defaults(self):
        """Setup default configuration values"""
        if self.config.allowed_applications is None:
            self.config.allowed_applications = []
        
        if self.config.blocked_applications is None:
            self.config.blocked_applications = []
        
        if self.config.allowed_ports is None:
            # Default ports for MIDAS
            self.config.allowed_ports = [8000, 8501, 5432, 6379]
        
        if self.config.blocked_ports is None:
            # Commonly attacked ports
            self.config.blocked_ports = [135, 139, 445, 1433, 3389]
        
        if self.config.trusted_networks is None:
            # Local networks
            self.config.trusted_networks = [
                "192.168.0.0/16",
                "10.0.0.0/8", 
                "172.16.0.0/12",
                "127.0.0.0/8"
            ]
        
        if self.config.suspicious_ip_ranges is None:
            # Known malicious IP ranges (simplified example)
            self.config.suspicious_ip_ranges = []
    
    def configure_basic_security(self) -> Dict[str, Any]:
        """Configure basic network security settings"""
        results = {
            'firewall_enabled': False,
            'default_actions_set': False,
            'logging_enabled': False,
            'midas_ports_allowed': False,
            'dangerous_ports_blocked': False
        }
        
        try:
            # Enable firewall
            if self.config.enable_firewall:
                enable_results = self.firewall.enable_firewall()
                results['firewall_enabled'] = all(enable_results.values())
            
            # Configure default actions
            action_results = self.firewall.configure_default_actions(self.config)
            results['default_actions_set'] = all(action_results.values())
            
            # Enable logging
            if self.config.enable_logging:
                results['logging_enabled'] = self.firewall.enable_logging()
            
            # Allow MIDAS application ports
            midas_ports_success = True
            for port in self.config.allowed_ports:
                success = self.firewall.allow_port(port, "TCP", f"MIDAS_TCP_{port}")
                if not success:
                    midas_ports_success = False
            results['midas_ports_allowed'] = midas_ports_success
            
            # Block dangerous ports
            dangerous_ports_success = True
            for port in self.config.blocked_ports:
                rule = FirewallRule(
                    name=f"Block_Dangerous_Port_{port}",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.BLOCK,
                    protocol="TCP",
                    local_port=str(port),
                    description=f"Block dangerous port {port}"
                )
                success = self.firewall.add_rule(rule)
                if not success:
                    dangerous_ports_success = False
            results['dangerous_ports_blocked'] = dangerous_ports_success
            
            logger.info("Basic network security configuration completed")
            
        except Exception as e:
            logger.error(f"Error configuring basic security: {e}")
            results['error'] = str(e)
        
        return results
    
    def configure_application_rules(self) -> Dict[str, Any]:
        """Configure firewall rules for applications"""
        results = {
            'allowed_apps': 0,
            'blocked_apps': 0,
            'errors': []
        }
        
        try:
            # Allow specified applications
            for app_path in self.config.allowed_applications:
                if self.firewall.allow_application(app_path):
                    results['allowed_apps'] += 1
                else:
                    results['errors'].append(f"Failed to allow {app_path}")
            
            # Block specified applications
            for app_path in self.config.blocked_applications:
                app_name = os.path.basename(app_path).replace('.exe', '')
                rule = FirewallRule(
                    name=f"Block_{app_name}",
                    direction=FirewallDirection.OUTBOUND,
                    action=FirewallAction.BLOCK,
                    program=app_path,
                    description=f"Block application {app_path}"
                )
                
                if self.firewall.add_rule(rule):
                    results['blocked_apps'] += 1
                else:
                    results['errors'].append(f"Failed to block {app_path}")
            
        except Exception as e:
            logger.error(f"Error configuring application rules: {e}")
            results['errors'].append(str(e))
        
        return results
    
    def block_suspicious_traffic(self) -> Dict[str, Any]:
        """Block suspicious IP ranges and patterns"""
        results = {
            'blocked_ips': 0,
            'rules_created': 0,
            'errors': []
        }
        
        try:
            # Block suspicious IP ranges
            for ip_range in self.config.suspicious_ip_ranges:
                rule_name = f"Block_Suspicious_{ip_range.replace('/', '_').replace('.', '_')}"
                
                if self.firewall.block_ip_address(ip_range, rule_name):
                    results['blocked_ips'] += 1
                    results['rules_created'] += 1
                else:
                    results['errors'].append(f"Failed to block IP range {ip_range}")
            
            # Create additional security rules
            security_rules = [
                # Block common attack vectors
                FirewallRule(
                    name="Block_NetBIOS_137",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.BLOCK,
                    protocol="UDP",
                    local_port="137",
                    description="Block NetBIOS Name Service"
                ),
                FirewallRule(
                    name="Block_NetBIOS_138",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.BLOCK,
                    protocol="UDP",
                    local_port="138",
                    description="Block NetBIOS Datagram Service"
                ),
                FirewallRule(
                    name="Block_SNMP",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.BLOCK,
                    protocol="UDP",
                    local_port="161",
                    description="Block SNMP"
                )
            ]
            
            for rule in security_rules:
                if self.firewall.add_rule(rule):
                    results['rules_created'] += 1
                else:
                    results['errors'].append(f"Failed to create rule {rule.name}")
            
        except Exception as e:
            logger.error(f"Error blocking suspicious traffic: {e}")
            results['errors'].append(str(e))
        
        return results
    
    def create_midas_security_profile(self) -> Dict[str, Any]:
        """Create comprehensive security profile for MIDAS"""
        results = {
            'basic_security': {},
            'application_rules': {},
            'suspicious_traffic': {},
            'custom_rules': 0
        }
        
        try:
            # Configure basic security
            results['basic_security'] = self.configure_basic_security()
            
            # Configure application rules
            results['application_rules'] = self.configure_application_rules()
            
            # Block suspicious traffic
            results['suspicious_traffic'] = self.block_suspicious_traffic()
            
            # Create MIDAS-specific rules
            midas_rules = [
                # Allow FastAPI
                FirewallRule(
                    name="MIDAS_FastAPI_8000",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.ALLOW,
                    protocol="TCP",
                    local_port="8000",
                    description="MIDAS FastAPI Server"
                ),
                # Allow Streamlit
                FirewallRule(
                    name="MIDAS_Streamlit_8501",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.ALLOW,
                    protocol="TCP",
                    local_port="8501",
                    description="MIDAS Streamlit Interface"
                ),
                # Allow PostgreSQL (local only)
                FirewallRule(
                    name="MIDAS_PostgreSQL_Local",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.ALLOW,
                    protocol="TCP",
                    local_port="5432",
                    remote_address="127.0.0.1",
                    description="MIDAS PostgreSQL (localhost only)"
                ),
                # Allow Redis (local only)
                FirewallRule(
                    name="MIDAS_Redis_Local",
                    direction=FirewallDirection.INBOUND,
                    action=FirewallAction.ALLOW,
                    protocol="TCP",
                    local_port="6379",
                    remote_address="127.0.0.1",
                    description="MIDAS Redis (localhost only)"
                )
            ]
            
            custom_rules_count = 0
            for rule in midas_rules:
                if self.firewall.add_rule(rule):
                    custom_rules_count += 1
            
            results['custom_rules'] = custom_rules_count
            
            logger.info("MIDAS security profile created successfully")
            
        except Exception as e:
            logger.error(f"Error creating MIDAS security profile: {e}")
            results['error'] = str(e)
        
        return results
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get current network security status"""
        try:
            status = {
                'timestamp': datetime.now().isoformat(),
                'firewall_status': self.firewall.get_firewall_status(),
                'firewall_available': self.firewall.firewall_available,
                'configuration': asdict(self.config),
                'active_rules_count': len(self.firewall.list_rules())
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting security status: {e}")
            return {'error': str(e)}
    
    def backup_firewall_rules(self, backup_path: str = None) -> Dict[str, Any]:
        """Backup current firewall configuration"""
        try:
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"firewall_backup_{timestamp}.json"
            
            # Get all rules
            rules = self.firewall.list_rules()
            
            # Get firewall status
            status = self.firewall.get_firewall_status()
            
            backup_data = {
                'timestamp': datetime.now().isoformat(),
                'firewall_status': status,
                'rules': rules,
                'config': asdict(self.config)
            }
            
            with open(backup_path, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)
            
            logger.info(f"Firewall configuration backed up to: {backup_path}")
            
            return {
                'success': True,
                'backup_path': backup_path,
                'rules_count': len(rules)
            }
            
        except Exception as e:
            logger.error(f"Error backing up firewall rules: {e}")
            return {'success': False, 'error': str(e)}

# Global network security instance
network_security_instance: Optional[WindowsNetworkSecurity] = None

def initialize_network_security(config: NetworkSecurityConfig = None) -> WindowsNetworkSecurity:
    """Initialize global network security"""
    global network_security_instance
    network_security_instance = WindowsNetworkSecurity(config)
    return network_security_instance

def get_network_security() -> WindowsNetworkSecurity:
    """Get global network security instance"""
    if network_security_instance is None:
        initialize_network_security()
    return network_security_instance