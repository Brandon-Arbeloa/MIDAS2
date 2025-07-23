import redis
import time
import logging
import json
import hashlib
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from functools import wraps
import asyncio
import socket
from ipaddress import ip_address, ip_network
import win32api
import win32security
import win32netcon

logger = logging.getLogger(__name__)

@dataclass
class RateLimitConfig:
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_limit: int = 10
    whitelist_ips: List[str] = None
    blacklist_ips: List[str] = None
    enable_progressive_delay: bool = True
    block_duration_minutes: int = 15

@dataclass
class RateLimitResult:
    allowed: bool
    remaining_requests: int
    reset_time: int
    retry_after: Optional[int] = None
    blocked_until: Optional[datetime] = None
    violation_count: int = 0

class WindowsNetworkAnalyzer:
    """Analyzes Windows network information for rate limiting"""
    
    def __init__(self):
        self.local_networks = []
        self._initialize_local_networks()
    
    def _initialize_local_networks(self):
        """Initialize local network ranges"""
        try:
            # Get local network interfaces
            import psutil
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        try:
                            network = ip_network(f"{addr.address}/{addr.netmask}", strict=False)
                            self.local_networks.append(network)
                        except:
                            pass
        except Exception as e:
            logger.warning(f"Failed to analyze local networks: {e}")
            
        # Add common private networks
        default_networks = [
            ip_network('192.168.0.0/16'),
            ip_network('10.0.0.0/8'),
            ip_network('172.16.0.0/12'),
            ip_network('127.0.0.0/8')
        ]
        self.local_networks.extend(default_networks)
    
    def is_local_request(self, client_ip: str) -> bool:
        """Check if request is from local network"""
        try:
            client_addr = ip_address(client_ip)
            return any(client_addr in network for network in self.local_networks)
        except:
            return False
    
    def get_client_info(self, request) -> Dict[str, str]:
        """Extract client information from request"""
        client_ip = self._get_client_ip(request)
        user_agent = getattr(request.headers, 'get', lambda x: '')('User-Agent', '')
        
        return {
            'ip': client_ip,
            'user_agent': user_agent,
            'is_local': self.is_local_request(client_ip),
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_client_ip(self, request) -> str:
        """Get real client IP considering proxies"""
        # Check for forwarded headers first
        forwarded_headers = [
            'X-Forwarded-For',
            'X-Real-IP',
            'X-Client-IP',
            'CF-Connecting-IP'
        ]
        
        for header in forwarded_headers:
            if hasattr(request.headers, 'get'):
                ip = request.headers.get(header)
                if ip:
                    # Take first IP if comma-separated
                    return ip.split(',')[0].strip()
        
        # Fallback to direct client IP
        return getattr(request, 'client', {}).get('host', '127.0.0.1')

class WindowsRedisRateLimiter:
    """Redis-based rate limiter optimized for Windows deployment"""
    
    def __init__(
        self,
        redis_client: redis.Redis,
        config: RateLimitConfig = None,
        enable_windows_logging: bool = True
    ):
        self.redis = redis_client
        self.config = config or RateLimitConfig()
        self.network_analyzer = WindowsNetworkAnalyzer()
        self.enable_windows_logging = enable_windows_logging
        
        # Windows Event Log integration
        if enable_windows_logging:
            self._setup_windows_logging()
        
        # Rate limit keys
        self.RATE_LIMIT_PREFIX = "midas:rate_limit:"
        self.VIOLATION_PREFIX = "midas:violations:"
        self.BLOCK_PREFIX = "midas:blocked:"
        
        # Initialize IP whitelist/blacklist
        self._initialize_ip_lists()
    
    def _setup_windows_logging(self):
        """Setup Windows Event Log integration"""
        try:
            import win32evtlog
            import win32evtlogutil
            
            self.event_log_source = "MIDAS_Security"
            
            # Register event source if not exists
            try:
                win32evtlogutil.AddSourceToRegistry(
                    self.event_log_source,
                    "Application",
                    "C:\\Windows\\System32\\EventLog.dll"
                )
            except Exception:
                pass  # Source might already exist
                
        except ImportError:
            logger.warning("Windows Event Log integration not available")
            self.enable_windows_logging = False
    
    def _log_to_windows_event(self, event_type: int, message: str, event_id: int = 1000):
        """Log security events to Windows Event Log"""
        if not self.enable_windows_logging:
            return
            
        try:
            import win32evtlog
            import win32evtlogutil
            
            win32evtlogutil.ReportEvent(
                self.event_log_source,
                event_id,
                eventType=event_type,
                strings=[message]
            )
        except Exception as e:
            logger.error(f"Failed to log to Windows Event Log: {e}")
    
    def _initialize_ip_lists(self):
        """Initialize IP whitelist and blacklist from Redis"""
        try:
            # Load whitelist
            whitelist_key = f"{self.RATE_LIMIT_PREFIX}whitelist"
            whitelist = self.redis.smembers(whitelist_key)
            if whitelist:
                self.config.whitelist_ips = [ip.decode() for ip in whitelist]
            elif self.config.whitelist_ips is None:
                self.config.whitelist_ips = []
            
            # Load blacklist
            blacklist_key = f"{self.RATE_LIMIT_PREFIX}blacklist"
            blacklist = self.redis.smembers(blacklist_key)
            if blacklist:
                self.config.blacklist_ips = [ip.decode() for ip in blacklist]
            elif self.config.blacklist_ips is None:
                self.config.blacklist_ips = []
                
        except Exception as e:
            logger.error(f"Failed to initialize IP lists: {e}")
            self.config.whitelist_ips = self.config.whitelist_ips or []
            self.config.blacklist_ips = self.config.blacklist_ips or []
    
    def _get_rate_limit_key(self, identifier: str, window: str) -> str:
        """Generate rate limit key"""
        return f"{self.RATE_LIMIT_PREFIX}{window}:{identifier}"
    
    def _get_violation_key(self, identifier: str) -> str:
        """Generate violation tracking key"""
        return f"{self.VIOLATION_PREFIX}{identifier}"
    
    def _get_block_key(self, identifier: str) -> str:
        """Generate block key"""
        return f"{self.BLOCK_PREFIX}{identifier}"
    
    def is_blocked(self, identifier: str) -> Tuple[bool, Optional[datetime]]:
        """Check if identifier is currently blocked"""
        block_key = self._get_block_key(identifier)
        
        try:
            block_data = self.redis.get(block_key)
            if block_data:
                block_info = json.loads(block_data.decode())
                blocked_until = datetime.fromisoformat(block_info['blocked_until'])
                
                if datetime.now() < blocked_until:
                    return True, blocked_until
                else:
                    # Block expired, remove it
                    self.redis.delete(block_key)
                    return False, None
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking block status: {e}")
            return False, None
    
    def add_violation(self, identifier: str, violation_type: str = "rate_limit"):
        """Add a violation record"""
        violation_key = self._get_violation_key(identifier)
        
        try:
            violation_data = {
                'timestamp': datetime.now().isoformat(),
                'type': violation_type,
                'identifier': identifier
            }
            
            # Use list to track violations
            self.redis.lpush(violation_key, json.dumps(violation_data))
            self.redis.expire(violation_key, 86400)  # Keep for 24 hours
            
            # Count violations in last hour
            violation_count = self._count_recent_violations(identifier, hours=1)
            
            # Auto-block after threshold violations
            if violation_count >= 5:  # 5 violations in an hour
                self._block_identifier(identifier, "repeated_violations")
            
            # Log to Windows Event Log
            self._log_to_windows_event(
                2,  # Warning
                f"Rate limit violation from {identifier}: {violation_type}",
                1001
            )
            
        except Exception as e:
            logger.error(f"Error recording violation: {e}")
    
    def _count_recent_violations(self, identifier: str, hours: int = 1) -> int:
        """Count violations in recent time period"""
        violation_key = self._get_violation_key(identifier)
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        try:
            violations = self.redis.lrange(violation_key, 0, -1)
            count = 0
            
            for violation in violations:
                violation_data = json.loads(violation.decode())
                violation_time = datetime.fromisoformat(violation_data['timestamp'])
                
                if violation_time > cutoff_time:
                    count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"Error counting violations: {e}")
            return 0
    
    def _block_identifier(self, identifier: str, reason: str):
        """Block an identifier for configured duration"""
        block_key = self._get_block_key(identifier)
        blocked_until = datetime.now() + timedelta(minutes=self.config.block_duration_minutes)
        
        block_data = {
            'identifier': identifier,
            'reason': reason,
            'blocked_at': datetime.now().isoformat(),
            'blocked_until': blocked_until.isoformat()
        }
        
        try:
            self.redis.set(
                block_key,
                json.dumps(block_data),
                ex=self.config.block_duration_minutes * 60
            )
            
            # Log to Windows Event Log
            self._log_to_windows_event(
                1,  # Error
                f"Blocked {identifier} until {blocked_until} for {reason}",
                1002
            )
            
        except Exception as e:
            logger.error(f"Error blocking identifier: {e}")
    
    def check_rate_limit(self, request, identifier: str = None) -> RateLimitResult:
        """Check rate limit for request"""
        client_info = self.network_analyzer.get_client_info(request)
        client_ip = client_info['ip']
        
        # Use IP as identifier if none provided
        if identifier is None:
            identifier = client_ip
        
        # Check if IP is blacklisted
        if client_ip in self.config.blacklist_ips:
            self.add_violation(identifier, "blacklisted_ip")
            return RateLimitResult(
                allowed=False,
                remaining_requests=0,
                reset_time=int(time.time()) + 3600,
                retry_after=3600
            )
        
        # Check if IP is whitelisted (bypass rate limiting)
        if client_ip in self.config.whitelist_ips:
            return RateLimitResult(
                allowed=True,
                remaining_requests=999999,
                reset_time=int(time.time()) + 60
            )
        
        # Check if currently blocked
        is_blocked, blocked_until = self.is_blocked(identifier)
        if is_blocked:
            retry_after = int((blocked_until - datetime.now()).total_seconds())
            return RateLimitResult(
                allowed=False,
                remaining_requests=0,
                reset_time=int(blocked_until.timestamp()),
                retry_after=retry_after,
                blocked_until=blocked_until
            )
        
        # Check rate limits
        current_time = int(time.time())
        
        # Check different time windows
        limits = [
            ('minute', 60, self.config.requests_per_minute),
            ('hour', 3600, self.config.requests_per_hour),
            ('day', 86400, self.config.requests_per_day)
        ]
        
        for window_name, window_seconds, limit in limits:
            window_start = current_time - window_seconds
            key = self._get_rate_limit_key(identifier, f"{window_name}:{window_start // window_seconds}")
            
            try:
                current_count = self.redis.incr(key)
                if current_count == 1:
                    self.redis.expire(key, window_seconds)
                
                if current_count > limit:
                    self.add_violation(identifier, f"{window_name}_limit_exceeded")
                    
                    # Progressive delay
                    if self.config.enable_progressive_delay:
                        delay_key = f"{self.RATE_LIMIT_PREFIX}delay:{identifier}"
                        delay_count = self.redis.incr(delay_key)
                        self.redis.expire(delay_key, 300)  # 5 minutes
                        
                        retry_after = min(delay_count * 2, 300)  # Max 5 minutes
                    else:
                        retry_after = window_seconds - (current_time % window_seconds)
                    
                    return RateLimitResult(
                        allowed=False,
                        remaining_requests=0,
                        reset_time=current_time + retry_after,
                        retry_after=retry_after,
                        violation_count=current_count - limit
                    )
                
                remaining = limit - current_count
                reset_time = window_start + window_seconds
                
                return RateLimitResult(
                    allowed=True,
                    remaining_requests=remaining,
                    reset_time=reset_time
                )
                
            except Exception as e:
                logger.error(f"Rate limit check failed for {window_name}: {e}")
                # Allow request if Redis fails (fail open for availability)
                return RateLimitResult(
                    allowed=True,
                    remaining_requests=limit,
                    reset_time=current_time + window_seconds
                )
        
        # Default allow
        return RateLimitResult(
            allowed=True,
            remaining_requests=self.config.requests_per_minute,
            reset_time=current_time + 60
        )
    
    def add_to_whitelist(self, ip: str, permanent: bool = False):
        """Add IP to whitelist"""
        whitelist_key = f"{self.RATE_LIMIT_PREFIX}whitelist"
        
        try:
            self.redis.sadd(whitelist_key, ip)
            if not permanent:
                self.redis.expire(whitelist_key, 86400)  # 24 hours
            
            # Update local config
            if ip not in self.config.whitelist_ips:
                self.config.whitelist_ips.append(ip)
            
            # Log to Windows Event Log
            self._log_to_windows_event(
                4,  # Information
                f"Added {ip} to whitelist ({'permanent' if permanent else 'temporary'})",
                1003
            )
            
        except Exception as e:
            logger.error(f"Error adding to whitelist: {e}")
    
    def add_to_blacklist(self, ip: str, reason: str = "manual", permanent: bool = False):
        """Add IP to blacklist"""
        blacklist_key = f"{self.RATE_LIMIT_PREFIX}blacklist"
        
        try:
            self.redis.sadd(blacklist_key, ip)
            if not permanent:
                self.redis.expire(blacklist_key, 86400)  # 24 hours
            
            # Update local config
            if ip not in self.config.blacklist_ips:
                self.config.blacklist_ips.append(ip)
            
            # Log to Windows Event Log
            self._log_to_windows_event(
                1,  # Error
                f"Added {ip} to blacklist for {reason} ({'permanent' if permanent else 'temporary'})",
                1004
            )
            
        except Exception as e:
            logger.error(f"Error adding to blacklist: {e}")
    
    def remove_from_blacklist(self, ip: str):
        """Remove IP from blacklist"""
        blacklist_key = f"{self.RATE_LIMIT_PREFIX}blacklist"
        
        try:
            self.redis.srem(blacklist_key, ip)
            
            # Update local config
            if ip in self.config.blacklist_ips:
                self.config.blacklist_ips.remove(ip)
            
            # Remove any active blocks
            block_key = self._get_block_key(ip)
            self.redis.delete(block_key)
            
            # Log to Windows Event Log
            self._log_to_windows_event(
                4,  # Information
                f"Removed {ip} from blacklist",
                1005
            )
            
        except Exception as e:
            logger.error(f"Error removing from blacklist: {e}")
    
    def get_stats(self) -> Dict[str, any]:
        """Get rate limiting statistics"""
        try:
            # Count active blocks
            block_keys = self.redis.keys(f"{self.BLOCK_PREFIX}*")
            active_blocks = len(block_keys)
            
            # Count violations in last hour
            violation_keys = self.redis.keys(f"{self.VIOLATION_PREFIX}*")
            recent_violations = 0
            
            for key in violation_keys:
                violations = self.redis.lrange(key, 0, -1)
                cutoff_time = datetime.now() - timedelta(hours=1)
                
                for violation in violations:
                    try:
                        violation_data = json.loads(violation.decode())
                        violation_time = datetime.fromisoformat(violation_data['timestamp'])
                        if violation_time > cutoff_time:
                            recent_violations += 1
                    except:
                        continue
            
            return {
                'config': asdict(self.config),
                'stats': {
                    'active_blocks': active_blocks,
                    'recent_violations_1h': recent_violations,
                    'whitelist_count': len(self.config.whitelist_ips),
                    'blacklist_count': len(self.config.blacklist_ips),
                    'local_networks': len(self.network_analyzer.local_networks)
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'error': str(e)}

# Rate limiting decorators
def rate_limit(
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
    per_ip: bool = True,
    per_user: bool = False,
    custom_identifier_func: Optional[callable] = None
):
    """Rate limiting decorator"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(request, *args, **kwargs):
            # Get rate limiter instance
            rate_limiter = getattr(request.app.state, 'rate_limiter', None)
            if not rate_limiter:
                logger.warning("Rate limiter not configured")
                return await func(request, *args, **kwargs)
            
            # Determine identifier
            if custom_identifier_func:
                identifier = custom_identifier_func(request)
            elif per_user and hasattr(request.state, 'user'):
                identifier = f"user:{request.state.user.id}"
            elif per_ip:
                client_info = rate_limiter.network_analyzer.get_client_info(request)
                identifier = client_info['ip']
            else:
                identifier = "global"
            
            # Check rate limit
            result = rate_limiter.check_rate_limit(request, identifier)
            
            if not result.allowed:
                from fastapi import HTTPException
                
                headers = {
                    'X-RateLimit-Limit': str(requests_per_minute),
                    'X-RateLimit-Remaining': str(result.remaining_requests),
                    'X-RateLimit-Reset': str(result.reset_time)
                }
                
                if result.retry_after:
                    headers['Retry-After'] = str(result.retry_after)
                
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers=headers
                )
            
            # Add rate limit headers to response
            response = await func(request, *args, **kwargs)
            
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(requests_per_minute)
                response.headers['X-RateLimit-Remaining'] = str(result.remaining_requests)
                response.headers['X-RateLimit-Reset'] = str(result.reset_time)
            
            return response
        
        @wraps(func)
        def sync_wrapper(request, *args, **kwargs):
            # Sync version for non-async functions
            return asyncio.run(async_wrapper(request, *args, **kwargs))
        
        # Return appropriate wrapper based on function type
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

# Global rate limiter instance
rate_limiter_instance: Optional[WindowsRedisRateLimiter] = None

def initialize_rate_limiter(redis_client: redis.Redis, config: RateLimitConfig = None) -> WindowsRedisRateLimiter:
    """Initialize global rate limiter"""
    global rate_limiter_instance
    rate_limiter_instance = WindowsRedisRateLimiter(redis_client, config)
    return rate_limiter_instance

def get_rate_limiter() -> WindowsRedisRateLimiter:
    """Get global rate limiter instance"""
    if rate_limiter_instance is None:
        raise RuntimeError("Rate limiter not initialized")
    return rate_limiter_instance