import os
import logging
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timedelta
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse
import re
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

logger = logging.getLogger(__name__)

@dataclass
class SecurityConfig:
    # CORS Configuration
    cors_allow_origins: List[str] = None
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = None
    cors_allow_headers: List[str] = None
    cors_expose_headers: List[str] = None
    cors_max_age: int = 86400
    
    # Security Headers
    enable_hsts: bool = True
    hsts_max_age: int = 31536000  # 1 year
    hsts_include_subdomains: bool = True
    enable_csp: bool = True
    csp_policy: str = None
    enable_x_frame_options: bool = True
    x_frame_options: str = "DENY"
    enable_x_content_type_options: bool = True
    enable_referrer_policy: bool = True
    referrer_policy: str = "strict-origin-when-cross-origin"
    enable_permissions_policy: bool = True
    
    # Trusted Hosts
    trusted_hosts: List[str] = None
    
    # JWT Configuration
    jwt_secret_key: str = None
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    
    # API Keys
    api_key_header: str = "X-API-Key"
    require_api_key: bool = False
    
    # Content Security
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    enable_gzip: bool = True

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers"""
    
    def __init__(self, app, config: SecurityConfig):
        super().__init__(app)
        self.config = config
    
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Add security headers
        if self.config.enable_hsts:
            hsts_value = f"max-age={self.config.hsts_max_age}"
            if self.config.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            response.headers["Strict-Transport-Security"] = hsts_value
        
        if self.config.enable_csp:
            csp_policy = self.config.csp_policy or self._get_default_csp()
            response.headers["Content-Security-Policy"] = csp_policy
        
        if self.config.enable_x_frame_options:
            response.headers["X-Frame-Options"] = self.config.x_frame_options
        
        if self.config.enable_x_content_type_options:
            response.headers["X-Content-Type-Options"] = "nosniff"
        
        if self.config.enable_referrer_policy:
            response.headers["Referrer-Policy"] = self.config.referrer_policy
        
        if self.config.enable_permissions_policy:
            permissions_policy = self._get_permissions_policy()
            response.headers["Permissions-Policy"] = permissions_policy
        
        # Additional security headers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["X-Download-Options"] = "noopen"
        response.headers["X-DNS-Prefetch-Control"] = "off"
        response.headers["Expect-CT"] = "max-age=86400, enforce"
        
        # Remove server header for security
        if "server" in response.headers:
            del response.headers["server"]
        
        # Add custom headers
        response.headers["X-MIDAS-Security"] = "enabled"
        response.headers["X-Content-Security-Version"] = "1.0"
        
        return response
    
    def _get_default_csp(self) -> str:
        """Get default Content Security Policy"""
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "media-src 'self'; "
            "object-src 'none'; "
            "child-src 'none'; "
            "worker-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "manifest-src 'self'"
        )
    
    def _get_permissions_policy(self) -> str:
        """Get Permissions Policy header"""
        return (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "fullscreen=(self), "
            "payment=()"
        )

class APIKeyValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for API key validation"""
    
    def __init__(self, app, config: SecurityConfig, valid_api_keys: List[str] = None):
        super().__init__(app)
        self.config = config
        self.valid_api_keys = set(valid_api_keys or [])
        self.exempt_paths = {"/docs", "/redoc", "/openapi.json", "/health", "/api/health"}
    
    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.config.require_api_key:
            return await call_next(request)
        
        # Skip API key validation for exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)
        
        # Check for API key
        api_key = request.headers.get(self.config.api_key_header)
        
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "API key required"}
            )
        
        if api_key not in self.valid_api_keys:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"}
            )
        
        # Add API key info to request state
        request.state.api_key = api_key
        
        return await call_next(request)

class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request size"""
    
    def __init__(self, app, max_size: int):
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        
        if content_length and int(content_length) > self.max_size:
            return JSONResponse(
                status_code=413,
                content={"error": "Request entity too large"}
            )
        
        return await call_next(request)

class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """Middleware for IP whitelisting"""
    
    def __init__(self, app, allowed_ips: List[str] = None, allowed_networks: List[str] = None):
        super().__init__(app)
        self.allowed_ips = set(allowed_ips or [])
        self.allowed_networks = allowed_networks or []
        
        # Parse network ranges
        self.parsed_networks = []
        for network in self.allowed_networks:
            try:
                import ipaddress
                self.parsed_networks.append(ipaddress.ip_network(network))
            except ValueError:
                logger.warning(f"Invalid network format: {network}")
    
    def _is_ip_allowed(self, ip: str) -> bool:
        """Check if IP is allowed"""
        if ip in self.allowed_ips:
            return True
        
        try:
            import ipaddress
            client_ip = ipaddress.ip_address(ip)
            
            for network in self.parsed_networks:
                if client_ip in network:
                    return True
        except ValueError:
            return False
        
        return False
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP from request"""
        # Check forwarded headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.allowed_ips and not self.allowed_networks:
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        
        if not self._is_ip_allowed(client_ip):
            logger.warning(f"IP not whitelisted: {client_ip}")
            return JSONResponse(
                status_code=403,
                content={"error": "Access denied"}
            )
        
        return await call_next(request)

class JWTTokenManager:
    """JWT token management"""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self.secret_key = config.jwt_secret_key or secrets.token_urlsafe(32)
        self.algorithm = config.jwt_algorithm
        self.expiry_hours = config.jwt_expiry_hours
    
    def generate_token(self, payload: Dict[str, Any]) -> str:
        """Generate JWT token"""
        # Add standard claims
        now = datetime.utcnow()
        payload.update({
            "iat": now,
            "exp": now + timedelta(hours=self.expiry_hours),
            "jti": secrets.token_urlsafe(16)  # Unique token ID
        })
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    def refresh_token(self, token: str) -> str:
        """Refresh JWT token"""
        payload = self.verify_token(token)
        
        # Remove timestamp claims
        payload.pop("iat", None)
        payload.pop("exp", None)
        payload.pop("jti", None)
        
        return self.generate_token(payload)

class WindowsAPISecurityManager:
    """Comprehensive API security management for Windows deployment"""
    
    def __init__(self, config: SecurityConfig = None):
        self.config = config or SecurityConfig()
        self.jwt_manager = JWTTokenManager(self.config)
        
        # Setup default values
        self._setup_defaults()
        
        # API key management
        self.api_keys = set()
        self._load_api_keys()
    
    def _setup_defaults(self):
        """Setup default configuration values"""
        if self.config.cors_allow_origins is None:
            self.config.cors_allow_origins = ["http://localhost:3000", "http://localhost:8501"]
        
        if self.config.cors_allow_methods is None:
            self.config.cors_allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        
        if self.config.cors_allow_headers is None:
            self.config.cors_allow_headers = [
                "Accept", "Accept-Language", "Content-Language", "Content-Type",
                "Authorization", "X-API-Key", "X-Request-ID", "X-Session-ID"
            ]
        
        if self.config.trusted_hosts is None:
            self.config.trusted_hosts = ["localhost", "127.0.0.1", "*.local"]
        
        if self.config.csp_policy is None:
            self.config.csp_policy = self._get_windows_csp_policy()
    
    def _get_windows_csp_policy(self) -> str:
        """Get CSP policy optimized for Windows deployment"""
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws://localhost:* wss://localhost:*; "
            "media-src 'self'; "
            "object-src 'none'; "
            "child-src 'none'; "
            "worker-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'"
        )
    
    def _load_api_keys(self):
        """Load API keys from configuration or environment"""
        # Load from environment variable
        env_keys = os.getenv("MIDAS_API_KEYS", "")
        if env_keys:
            self.api_keys.update(env_keys.split(","))
        
        # Generate default API key if none exist
        if not self.api_keys:
            default_key = secrets.token_urlsafe(32)
            self.api_keys.add(default_key)
            logger.info(f"Generated default API key: {default_key}")
    
    def configure_app(self, app: FastAPI):
        """Configure FastAPI app with security middleware"""
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.cors_allow_origins,
            allow_credentials=self.config.cors_allow_credentials,
            allow_methods=self.config.cors_allow_methods,
            allow_headers=self.config.cors_allow_headers,
            expose_headers=self.config.cors_expose_headers or [],
            max_age=self.config.cors_max_age
        )
        
        # Add trusted host middleware
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=self.config.trusted_hosts
        )
        
        # Add request size middleware
        app.add_middleware(
            RequestSizeMiddleware,
            max_size=self.config.max_request_size
        )
        
        # Add security headers middleware
        app.add_middleware(SecurityHeadersMiddleware, config=self.config)
        
        # Add API key validation middleware
        if self.config.require_api_key:
            app.add_middleware(
                APIKeyValidationMiddleware,
                config=self.config,
                valid_api_keys=list(self.api_keys)
            )
        
        # Add GZip middleware if enabled
        if self.config.enable_gzip:
            app.add_middleware(GZipMiddleware, minimum_size=1000)
        
        # Add custom error handlers
        self._add_error_handlers(app)
    
    def _add_error_handlers(self, app: FastAPI):
        """Add custom error handlers"""
        
        @app.exception_handler(413)
        async def request_too_large(request: Request, exc):
            return JSONResponse(
                status_code=413,
                content={"error": "Request entity too large"}
            )
        
        @app.exception_handler(429)
        async def rate_limit_exceeded(request: Request, exc):
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"}
            )
        
        @app.exception_handler(500)
        async def internal_server_error(request: Request, exc):
            logger.error(f"Internal server error: {exc}")
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error"}
            )
    
    def add_api_key(self, api_key: str):
        """Add new API key"""
        self.api_keys.add(api_key)
    
    def remove_api_key(self, api_key: str):
        """Remove API key"""
        self.api_keys.discard(api_key)
    
    def generate_api_key(self) -> str:
        """Generate new API key"""
        api_key = secrets.token_urlsafe(32)
        self.api_keys.add(api_key)
        return api_key
    
    def create_jwt_dependency(self):
        """Create JWT authentication dependency"""
        security = HTTPBearer()
        
        def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
            try:
                payload = self.jwt_manager.verify_token(credentials.credentials)
                return payload
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"JWT verification error: {e}")
                raise HTTPException(status_code=401, detail="Authentication failed")
        
        return verify_jwt
    
    def create_api_key_dependency(self):
        """Create API key authentication dependency"""
        def verify_api_key(request: Request):
            if not self.config.require_api_key:
                return True
            
            api_key = request.headers.get(self.config.api_key_header)
            if not api_key or api_key not in self.api_keys:
                raise HTTPException(status_code=401, detail="Invalid API key")
            
            return api_key
        
        return verify_api_key
    
    def validate_origin(self, origin: str) -> bool:
        """Validate request origin"""
        if not origin:
            return False
        
        # Parse origin
        try:
            parsed = urlparse(origin)
            host = parsed.netloc.lower()
        except:
            return False
        
        # Check against allowed origins
        for allowed in self.config.cors_allow_origins:
            if allowed == "*":
                return True
            
            # Handle wildcards
            if "*" in allowed:
                pattern = allowed.replace("*", ".*")
                if re.match(pattern, host):
                    return True
            elif allowed.lower() == host:
                return True
        
        return False
    
    def get_security_headers(self) -> Dict[str, str]:
        """Get all security headers as dictionary"""
        headers = {}
        
        if self.config.enable_hsts:
            hsts_value = f"max-age={self.config.hsts_max_age}"
            if self.config.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            headers["Strict-Transport-Security"] = hsts_value
        
        if self.config.enable_csp:
            headers["Content-Security-Policy"] = self.config.csp_policy
        
        if self.config.enable_x_frame_options:
            headers["X-Frame-Options"] = self.config.x_frame_options
        
        if self.config.enable_x_content_type_options:
            headers["X-Content-Type-Options"] = "nosniff"
        
        if self.config.enable_referrer_policy:
            headers["Referrer-Policy"] = self.config.referrer_policy
        
        headers.update({
            "X-XSS-Protection": "1; mode=block",
            "X-Download-Options": "noopen",
            "X-DNS-Prefetch-Control": "off",
            "X-MIDAS-Security": "enabled"
        })
        
        return headers
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get security configuration summary"""
        return {
            'cors_enabled': bool(self.config.cors_allow_origins),
            'cors_origins': self.config.cors_allow_origins,
            'hsts_enabled': self.config.enable_hsts,
            'csp_enabled': self.config.enable_csp,
            'api_keys_count': len(self.api_keys),
            'trusted_hosts': self.config.trusted_hosts,
            'max_request_size_mb': self.config.max_request_size / (1024 * 1024),
            'jwt_enabled': bool(self.config.jwt_secret_key),
            'rate_limiting': 'configured_separately',
            'generated_at': datetime.now().isoformat()
        }

# Global security manager instance
security_manager: Optional[WindowsAPISecurityManager] = None

def initialize_security_manager(config: SecurityConfig = None) -> WindowsAPISecurityManager:
    """Initialize global security manager"""
    global security_manager
    security_manager = WindowsAPISecurityManager(config)
    return security_manager

def get_security_manager() -> WindowsAPISecurityManager:
    """Get global security manager instance"""
    if security_manager is None:
        initialize_security_manager()
    return security_manager

def configure_app_security(app: FastAPI, config: SecurityConfig = None):
    """Configure FastAPI application with security settings"""
    manager = initialize_security_manager(config)
    manager.configure_app(app)
    return manager