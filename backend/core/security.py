"""
Security utilities for JWT authentication and Windows integration
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status

from backend.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(
    data: Dict[str, Any], 
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        if to_encode.get("type") == "refresh":
            expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": to_encode.get("type", "access")
    })
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a refresh token"""
    data_copy = data.copy()
    data_copy["type"] = "refresh"
    return create_access_token(data_copy)

def get_windows_user_info() -> Optional[Dict[str, str]]:
    """Get Windows user information"""
    if os.name != 'nt':
        return None
    
    try:
        from win32api import GetUserName
        from win32security import GetUserNameEx, NameDisplay, NameSamCompatible
        
        return {
            "username": GetUserName(),
            "display_name": GetUserNameEx(NameDisplay),
            "domain_user": GetUserNameEx(NameSamCompatible)
        }
    except ImportError:
        return {
            "username": os.getenv("USERNAME", "unknown"),
            "display_name": os.getenv("USERDNSDOMAIN", ""),
            "domain_user": f"{os.getenv('USERDOMAIN', '')}/{os.getenv('USERNAME', '')}"
        }
    except Exception:
        return None