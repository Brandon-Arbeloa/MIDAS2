"""
MIDAS Windows Authentication System
Local-only user authentication using Windows-native storage and security features
"""

import os
import sqlite3
import hashlib
import secrets
import json
import yaml
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import threading
from contextlib import contextmanager
import logging

try:
    import win32crypt
    import win32api
    import win32con
    WINDOWS_CRYPTO_AVAILABLE = True
except ImportError:
    WINDOWS_CRYPTO_AVAILABLE = False
    import cryptography.fernet as fernet
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64

import bcrypt

class WindowsCryptoManager:
    """Handles encryption using Windows DPAPI or fallback cryptography"""
    
    def __init__(self):
        self.use_dpapi = WINDOWS_CRYPTO_AVAILABLE
        if not self.use_dpapi:
            self._setup_fallback_crypto()
    
    def _setup_fallback_crypto(self):
        """Setup fallback encryption when DPAPI is not available"""
        # Generate or load encryption key
        key_file = self._get_windows_appdata_path() / "midas_encryption.key"
        
        if key_file.exists():
            with open(key_file, 'rb') as f:
                self.key = f.read()
        else:
            # Generate new key
            password = os.environ.get('USERNAME', 'midas_user').encode()
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            self.key = base64.urlsafe_b64encode(kdf.derive(password))
            
            # Save key securely
            key_file.parent.mkdir(parents=True, exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(salt + self.key)
    
    def encrypt_data(self, data: str) -> bytes:
        """Encrypt sensitive data using Windows DPAPI or fallback"""
        if self.use_dpapi:
            try:
                encrypted = win32crypt.CryptProtectData(
                    data.encode('utf-8'),
                    "MIDAS User Data",
                    None,
                    None,
                    None,
                    0
                )
                return encrypted
            except Exception:
                self.use_dpapi = False
                self._setup_fallback_crypto()
        
        # Fallback encryption
        f = fernet.Fernet(self.key)
        return f.encrypt(data.encode('utf-8'))
    
    def decrypt_data(self, encrypted_data: bytes) -> str:
        """Decrypt sensitive data"""
        if self.use_dpapi:
            try:
                decrypted = win32crypt.CryptUnprotectData(encrypted_data, None, None, None, 0)
                return decrypted[1].decode('utf-8')
            except Exception:
                self.use_dpapi = False
                self._setup_fallback_crypto()
        
        # Fallback decryption
        f = fernet.Fernet(self.key)
        return f.decrypt(encrypted_data).decode('utf-8')
    
    @staticmethod
    def _get_windows_appdata_path() -> Path:
        """Get Windows AppData path for MIDAS"""
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        return Path(appdata) / "MIDAS"

class WindowsSessionManager:
    """Manages user sessions using Windows temp directories"""
    
    def __init__(self):
        self.session_dir = Path(tempfile.gettempdir()) / "MIDAS_Sessions"
        self.session_dir.mkdir(exist_ok=True)
        self.session_timeout = timedelta(hours=8)  # 8 hour session timeout
        self._cleanup_expired_sessions()
    
    def create_session(self, username: str, user_data: Dict) -> str:
        """Create a new user session"""
        session_id = secrets.token_hex(32)
        session_data = {
            'username': username,
            'user_data': user_data,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + self.session_timeout).isoformat(),
            'last_activity': datetime.now().isoformat()
        }
        
        session_file = self.session_dir / f"{session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(session_data, f)
        
        return session_id
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Validate and refresh session"""
        if not session_id:
            return None
        
        session_file = self.session_dir / f"{session_id}.json"
        if not session_file.exists():
            return None
        
        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            expires_at = datetime.fromisoformat(session_data['expires_at'])
            if datetime.now() > expires_at:
                self.destroy_session(session_id)
                return None
            
            # Update last activity
            session_data['last_activity'] = datetime.now().isoformat()
            with open(session_file, 'w') as f:
                json.dump(session_data, f)
            
            return session_data
            
        except Exception:
            return None
    
    def destroy_session(self, session_id: str):
        """Destroy user session"""
        session_file = self.session_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
    
    def _cleanup_expired_sessions(self):
        """Clean up expired session files"""
        try:
            for session_file in self.session_dir.glob("*.json"):
                try:
                    with open(session_file, 'r') as f:
                        session_data = json.load(f)
                    
                    expires_at = datetime.fromisoformat(session_data['expires_at'])
                    if datetime.now() > expires_at:
                        session_file.unlink()
                except Exception:
                    # Remove corrupted session files
                    session_file.unlink()
        except Exception:
            pass

class WindowsUserDatabase:
    """SQLite database for user management with Windows file locking"""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            appdata = WindowsCryptoManager._get_windows_appdata_path()
            appdata.mkdir(parents=True, exist_ok=True)
            db_path = appdata / "midas_users.db"
        
        self.db_path = db_path
        self.crypto_manager = WindowsCryptoManager()
        self._lock = threading.Lock()
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with Windows file locking"""
        with self._lock:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,  # 30 second timeout
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    failed_login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    encrypted_data BLOB
                )
            ''')
            
            # User preferences table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    preference_key TEXT NOT NULL,
                    preference_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, preference_key)
                )
            ''')
            
            # Password reset tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            conn.commit()
            
            # Create default admin user if no users exist
            cursor.execute('SELECT COUNT(*) as count FROM users')
            user_count = cursor.fetchone()['count']
            
            if user_count == 0:
                self._create_default_admin()
    
    def _create_default_admin(self):
        """Create default admin user"""
        default_password = "admin123"  # Should be changed on first login
        password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt())
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', ("admin", "admin@localhost", password_hash.decode('utf-8'), "admin"))
            conn.commit()
    
    def create_user(self, username: str, password: str, email: str = None, role: str = "user") -> bool:
        """Create a new user"""
        try:
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, role)
                    VALUES (?, ?, ?, ?)
                ''', (username, email, password_hash.decode('utf-8'), role))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False  # Username already exists
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user data"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM users WHERE username = ? AND is_active = TRUE
            ''', (username,))
            user = cursor.fetchone()
            
            if not user:
                return None
            
            # Check if account is locked
            if user['locked_until']:
                locked_until = datetime.fromisoformat(user['locked_until'])
                if datetime.now() < locked_until:
                    return None
            
            # Verify password
            if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                # Reset failed attempts and update last login
                cursor.execute('''
                    UPDATE users 
                    SET failed_login_attempts = 0, locked_until = NULL, last_login = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (user['id'],))
                conn.commit()
                
                return {
                    'id': user['id'],
                    'username': user['username'],
                    'email': user['email'],
                    'role': user['role'],
                    'created_at': user['created_at'],
                    'last_login': user['last_login']
                }
            else:
                # Increment failed attempts
                failed_attempts = user['failed_login_attempts'] + 1
                locked_until = None
                
                if failed_attempts >= 5:  # Lock after 5 failed attempts
                    locked_until = (datetime.now() + timedelta(minutes=30)).isoformat()
                
                cursor.execute('''
                    UPDATE users 
                    SET failed_login_attempts = ?, locked_until = ?
                    WHERE id = ?
                ''', (failed_attempts, locked_until, user['id']))
                conn.commit()
                
                return None
    
    def get_user_preferences(self, user_id: int) -> Dict:
        """Get user preferences"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT preference_key, preference_value 
                FROM user_preferences 
                WHERE user_id = ?
            ''', (user_id,))
            
            preferences = {}
            for row in cursor.fetchall():
                try:
                    # Try to parse as JSON
                    preferences[row['preference_key']] = json.loads(row['preference_value'])
                except json.JSONDecodeError:
                    # Store as string if not JSON
                    preferences[row['preference_key']] = row['preference_value']
            
            return preferences
    
    def set_user_preference(self, user_id: int, key: str, value: Any):
        """Set user preference"""
        value_str = json.dumps(value) if not isinstance(value, str) else value
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_preferences 
                (user_id, preference_key, preference_value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, key, value_str))
            conn.commit()
    
    def change_password(self, user_id: int, new_password: str) -> bool:
        """Change user password"""
        try:
            password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET password_hash = ?, failed_login_attempts = 0, locked_until = NULL
                    WHERE id = ?
                ''', (password_hash.decode('utf-8'), user_id))
                conn.commit()
                return True
        except Exception:
            return False
    
    def create_password_reset_token(self, username: str) -> Optional[str]:
        """Create password reset token"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            
            if not user:
                return None
            
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
            
            cursor.execute('''
                INSERT INTO password_reset_tokens (user_id, token, expires_at)
                VALUES (?, ?, ?)
            ''', (user['id'], token, expires_at))
            conn.commit()
            
            return token
    
    def reset_password_with_token(self, token: str, new_password: str) -> bool:
        """Reset password using token"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT prt.user_id, prt.expires_at, prt.used
                FROM password_reset_tokens prt
                WHERE prt.token = ?
            ''', (token,))
            
            reset_request = cursor.fetchone()
            if not reset_request or reset_request['used']:
                return False
            
            expires_at = datetime.fromisoformat(reset_request['expires_at'])
            if datetime.now() > expires_at:
                return False
            
            # Change password
            if self.change_password(reset_request['user_id'], new_password):
                # Mark token as used
                cursor.execute('''
                    UPDATE password_reset_tokens SET used = TRUE WHERE token = ?
                ''', (token,))
                conn.commit()
                return True
            
            return False

class WindowsAuthenticationSystem:
    """Main authentication system integrating all components"""
    
    def __init__(self):
        self.user_db = WindowsUserDatabase()
        self.session_manager = WindowsSessionManager()
        self.config_path = self._get_config_path()
        self._create_streamlit_config()
    
    def _get_config_path(self) -> Path:
        """Get configuration file path"""
        appdata = WindowsCryptoManager._get_windows_appdata_path()
        return appdata / "streamlit_auth_config.yaml"
    
    def _create_streamlit_config(self):
        """Create streamlit-authenticator compatible config"""
        # This creates a minimal config for streamlit-authenticator integration
        config = {
            'credentials': {
                'usernames': {}
            },
            'cookie': {
                'name': 'midas_auth_cookie',
                'key': secrets.token_hex(16),
                'expiry_days': 7
            },
            'preauthorized': {
                'emails': []
            }
        }
        
        # Update with current users from database
        self._update_streamlit_config(config)
    
    def _update_streamlit_config(self, config: Dict):
        """Update config with current users from database"""
        with self.user_db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, password_hash, email FROM users WHERE is_active = TRUE')
            users = cursor.fetchall()
            
            for user in users:
                config['credentials']['usernames'][user['username']] = {
                    'email': user['email'] or '',
                    'name': user['username'],
                    'password': user['password_hash']
                }
        
        # Save config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f)
    
    def register_user(self, username: str, password: str, email: str = None) -> Tuple[bool, str]:
        """Register a new user"""
        if len(password) < 6:
            return False, "Password must be at least 6 characters long"
        
        if self.user_db.create_user(username, password, email):
            # Update streamlit config
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            self._update_streamlit_config(config)
            return True, "User registered successfully"
        else:
            return False, "Username already exists"
    
    def login_user(self, username: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Login user and create session"""
        user_data = self.user_db.authenticate_user(username, password)
        if user_data:
            session_id = self.session_manager.create_session(username, user_data)
            return True, session_id, user_data
        else:
            return False, None, None
    
    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Validate user session"""
        return self.session_manager.validate_session(session_id)
    
    def logout_user(self, session_id: str):
        """Logout user and destroy session"""
        self.session_manager.destroy_session(session_id)
    
    def get_streamlit_config(self) -> Dict:
        """Get streamlit-authenticator config"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

# Export main classes
__all__ = [
    'WindowsAuthenticationSystem',
    'WindowsUserDatabase',
    'WindowsSessionManager',
    'WindowsCryptoManager'
]