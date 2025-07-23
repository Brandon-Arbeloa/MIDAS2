"""
MIDAS User Profile System with Chart Saving Functionality
Complete user profile management with chart persistence, sharing, and Windows integration
"""

import os
import sqlite3
import json
import uuid
import shutil
import subprocess
import winreg
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
import threading
from contextlib import contextmanager
import base64
import zipfile
import tempfile

import plotly.graph_objects as go
import plotly.io as pio
from PIL import Image
import pandas as pd

# Windows-specific imports
try:
    import win32net
    import win32netcon
    import win32api
    import win32con
    WINDOWS_NETWORK_AVAILABLE = True
except ImportError:
    WINDOWS_NETWORK_AVAILABLE = False

class WindowsRegistryManager:
    """Manages Windows Registry settings for MIDAS"""
    
    def __init__(self):
        self.registry_path = r"SOFTWARE\MIDAS"
        self.user_settings_path = r"SOFTWARE\MIDAS\UserSettings"
    
    def set_registry_value(self, key_path: str, value_name: str, value: Any, value_type: int = winreg.REG_SZ):
        """Set Windows Registry value"""
        try:
            key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, value_name, 0, value_type, value)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False
    
    def get_registry_value(self, key_path: str, value_name: str, default_value: Any = None):
        """Get Windows Registry value"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, value_name)
            winreg.CloseKey(key)
            return value
        except Exception:
            return default_value
    
    def save_user_settings(self, user_id: int, settings: Dict):
        """Save user settings to Windows Registry"""
        user_key_path = f"{self.user_settings_path}\\User_{user_id}"
        
        for key, value in settings.items():
            if isinstance(value, (dict, list)):
                self.set_registry_value(user_key_path, key, json.dumps(value))
            elif isinstance(value, bool):
                self.set_registry_value(user_key_path, key, int(value), winreg.REG_DWORD)
            elif isinstance(value, int):
                self.set_registry_value(user_key_path, key, value, winreg.REG_DWORD)
            else:
                self.set_registry_value(user_key_path, key, str(value))
    
    def load_user_settings(self, user_id: int) -> Dict:
        """Load user settings from Windows Registry"""
        settings = {}
        user_key_path = f"{self.user_settings_path}\\User_{user_id}"
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_key_path, 0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    value_name, value_data, value_type = winreg.EnumValue(key, i)
                    
                    if value_type == winreg.REG_DWORD:
                        settings[value_name] = bool(value_data) if value_name.startswith('is_') else value_data
                    elif value_type == winreg.REG_SZ:
                        try:
                            # Try to parse as JSON
                            settings[value_name] = json.loads(value_data)
                        except json.JSONDecodeError:
                            settings[value_name] = value_data
                    
                    i += 1
                except OSError:
                    break
            
            winreg.CloseKey(key)
        except Exception:
            pass
        
        return settings

class ChartPersistenceManager:
    """Manages chart persistence with Windows-friendly file handling"""
    
    def __init__(self, base_path: Optional[Path] = None):
        if base_path is None:
            # Use Windows Documents folder
            documents_path = Path.home() / "Documents"
            self.base_path = documents_path / "MIDAS" / "SavedCharts"
        else:
            self.base_path = base_path
        
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create user-specific directories
        self.shared_path = self.base_path / "Shared"
        self.templates_path = self.base_path / "Templates"
        
        self.shared_path.mkdir(exist_ok=True)
        self.templates_path.mkdir(exist_ok=True)
    
    def get_user_chart_directory(self, user_id: int) -> Path:
        """Get user-specific chart directory"""
        user_dir = self.base_path / f"User_{user_id}"
        user_dir.mkdir(exist_ok=True)
        return user_dir
    
    def save_chart_files(self, user_id: int, chart_id: str, chart_fig: go.Figure, 
                        metadata: Dict) -> Dict[str, str]:
        """Save chart in multiple formats"""
        user_dir = self.get_user_chart_directory(user_id)
        chart_dir = user_dir / chart_id
        chart_dir.mkdir(exist_ok=True)
        
        file_paths = {}
        
        try:
            # Save as JSON (Plotly format)
            json_path = chart_dir / f"{chart_id}.json"
            chart_fig.write_json(str(json_path))
            file_paths['json'] = str(json_path)
            
            # Save as HTML (interactive)
            html_path = chart_dir / f"{chart_id}.html"
            chart_fig.write_html(str(html_path))
            file_paths['html'] = str(html_path)
            
            # Save as PNG (static image)
            png_path = chart_dir / f"{chart_id}.png"
            chart_fig.write_image(str(png_path), width=1200, height=800, scale=2)
            file_paths['png'] = str(png_path)
            
            # Save metadata
            metadata_path = chart_dir / f"{chart_id}_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            file_paths['metadata'] = str(metadata_path)
            
            return file_paths
            
        except Exception as e:
            # Cleanup on failure
            if chart_dir.exists():
                shutil.rmtree(chart_dir)
            raise Exception(f"Failed to save chart files: {str(e)}")
    
    def load_chart_figure(self, user_id: int, chart_id: str) -> Optional[go.Figure]:
        """Load chart figure from JSON file"""
        try:
            user_dir = self.get_user_chart_directory(user_id)
            json_path = user_dir / chart_id / f"{chart_id}.json"
            
            if json_path.exists():
                return pio.read_json(str(json_path))
            return None
        except Exception:
            return None
    
    def delete_chart_files(self, user_id: int, chart_id: str) -> bool:
        """Delete all files for a chart"""
        try:
            user_dir = self.get_user_chart_directory(user_id)
            chart_dir = user_dir / chart_id
            
            if chart_dir.exists():
                shutil.rmtree(chart_dir)
                return True
            return False
        except Exception:
            return False
    
    def export_chart_to_format(self, user_id: int, chart_id: str, 
                              export_format: str, export_path: Path) -> bool:
        """Export chart to specified format"""
        try:
            chart_fig = self.load_chart_figure(user_id, chart_id)
            if not chart_fig:
                return False
            
            if export_format.lower() == 'png':
                chart_fig.write_image(str(export_path), width=1200, height=800, scale=2)
            elif export_format.lower() == 'pdf':
                chart_fig.write_image(str(export_path), format='pdf', width=1200, height=800)
            elif export_format.lower() == 'html':
                chart_fig.write_html(str(export_path))
            elif export_format.lower() == 'svg':
                chart_fig.write_image(str(export_path), format='svg', width=1200, height=800)
            else:
                return False
            
            return True
        except Exception:
            return False
    
    def create_chart_package(self, user_id: int, chart_ids: List[str], 
                           package_path: Path) -> bool:
        """Create a ZIP package with multiple charts"""
        try:
            with zipfile.ZipFile(package_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for chart_id in chart_ids:
                    user_dir = self.get_user_chart_directory(user_id)
                    chart_dir = user_dir / chart_id
                    
                    if chart_dir.exists():
                        for file_path in chart_dir.iterdir():
                            if file_path.is_file():
                                arcname = f"{chart_id}/{file_path.name}"
                                zipf.write(file_path, arcname)
            
            return True
        except Exception:
            return False

class UserProfileDatabase:
    """Extended database for user profiles and chart management"""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            appdata = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / "MIDAS"
            appdata.mkdir(parents=True, exist_ok=True)
            db_path = appdata / "midas_profiles.db"
        
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with Windows file locking"""
        with self._lock:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
    
    def _init_database(self):
        """Initialize extended database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Saved charts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS saved_charts (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    chart_type TEXT NOT NULL,
                    chart_config TEXT NOT NULL,
                    dataset_info TEXT,
                    file_paths TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_public BOOLEAN DEFAULT FALSE,
                    is_template BOOLEAN DEFAULT FALSE,
                    tags TEXT,
                    version INTEGER DEFAULT 1,
                    parent_chart_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (parent_chart_id) REFERENCES saved_charts (id)
                )
            ''')
            
            # Chart versions table (for edit history)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chart_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chart_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    chart_config TEXT NOT NULL,
                    change_description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER NOT NULL,
                    FOREIGN KEY (chart_id) REFERENCES saved_charts (id),
                    FOREIGN KEY (created_by) REFERENCES users (id),
                    UNIQUE(chart_id, version_number)
                )
            ''')
            
            # Chart shares table (for local network sharing)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chart_shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chart_id TEXT NOT NULL,
                    shared_by INTEGER NOT NULL,
                    shared_with INTEGER,
                    share_type TEXT DEFAULT 'user',
                    network_path TEXT,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP,
                    FOREIGN KEY (chart_id) REFERENCES saved_charts (id),
                    FOREIGN KEY (shared_by) REFERENCES users (id),
                    FOREIGN KEY (shared_with) REFERENCES users (id)
                )
            ''')
            
            # User sessions table (enhanced)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            # User dashboard layouts
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_dashboards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    layout_config TEXT NOT NULL,
                    chart_ids TEXT,
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            
            conn.commit()
    
    def save_chart(self, user_id: int, title: str, chart_type: str, 
                  chart_config: Dict, dataset_info: Dict, description: str = None,
                  tags: List[str] = None, is_public: bool = False,
                  is_template: bool = False) -> str:
        """Save a chart to the database"""
        chart_id = str(uuid.uuid4())
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO saved_charts 
                (id, user_id, title, description, chart_type, chart_config, 
                 dataset_info, is_public, is_template, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                chart_id, user_id, title, description, chart_type,
                json.dumps(chart_config), json.dumps(dataset_info),
                is_public, is_template, json.dumps(tags or [])
            ))
            conn.commit()
        
        return chart_id
    
    def get_user_charts(self, user_id: int, include_public: bool = True,
                       chart_type: str = None, tags: List[str] = None) -> List[Dict]:
        """Get charts for a user"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT * FROM saved_charts 
                WHERE (user_id = ? OR (is_public = TRUE AND ? = TRUE))
            '''
            params = [user_id, include_public]
            
            if chart_type:
                query += ' AND chart_type = ?'
                params.append(chart_type)
            
            if tags:
                # Simple tag filtering (can be improved with full-text search)
                tag_conditions = []
                for tag in tags:
                    tag_conditions.append('tags LIKE ?')
                    params.append(f'%{tag}%')
                
                if tag_conditions:
                    query += ' AND (' + ' OR '.join(tag_conditions) + ')'
            
            query += ' ORDER BY updated_at DESC'
            
            cursor.execute(query, params)
            charts = []
            
            for row in cursor.fetchall():
                chart_data = {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'title': row['title'],
                    'description': row['description'],
                    'chart_type': row['chart_type'],
                    'chart_config': json.loads(row['chart_config']),
                    'dataset_info': json.loads(row['dataset_info']) if row['dataset_info'] else {},
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'is_public': bool(row['is_public']),
                    'is_template': bool(row['is_template']),
                    'tags': json.loads(row['tags']) if row['tags'] else [],
                    'version': row['version'],
                    'parent_chart_id': row['parent_chart_id']
                }
                charts.append(chart_data)
            
            return charts
    
    def get_chart_by_id(self, chart_id: str, user_id: int = None) -> Optional[Dict]:
        """Get a specific chart by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT * FROM saved_charts 
                WHERE id = ? AND (user_id = ? OR is_public = TRUE OR ? IS NULL)
            '''
            cursor.execute(query, (chart_id, user_id, user_id))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'title': row['title'],
                    'description': row['description'],
                    'chart_type': row['chart_type'],
                    'chart_config': json.loads(row['chart_config']),
                    'dataset_info': json.loads(row['dataset_info']) if row['dataset_info'] else {},
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'is_public': bool(row['is_public']),
                    'is_template': bool(row['is_template']),
                    'tags': json.loads(row['tags']) if row['tags'] else [],
                    'version': row['version'],
                    'parent_chart_id': row['parent_chart_id']
                }
            return None
    
    def update_chart(self, chart_id: str, user_id: int, updates: Dict, 
                    change_description: str = None) -> bool:
        """Update a chart and create version history"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user owns the chart
            cursor.execute('SELECT * FROM saved_charts WHERE id = ? AND user_id = ?', 
                         (chart_id, user_id))
            chart = cursor.fetchone()
            
            if not chart:
                return False
            
            # Create version history entry
            cursor.execute('''
                INSERT INTO chart_versions 
                (chart_id, version_number, chart_config, change_description, created_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                chart_id, chart['version'], chart['chart_config'],
                change_description, user_id
            ))
            
            # Update the main chart
            update_fields = []
            update_values = []
            
            for field, value in updates.items():
                if field in ['title', 'description', 'chart_type', 'is_public', 'is_template']:
                    update_fields.append(f'{field} = ?')
                    update_values.append(value)
                elif field in ['chart_config', 'dataset_info', 'tags']:
                    update_fields.append(f'{field} = ?')
                    update_values.append(json.dumps(value))
            
            if update_fields:
                update_fields.append('updated_at = CURRENT_TIMESTAMP')
                update_fields.append('version = version + 1')
                
                query = f'UPDATE saved_charts SET {", ".join(update_fields)} WHERE id = ?'
                update_values.append(chart_id)
                
                cursor.execute(query, update_values)
                conn.commit()
                return True
        
        return False
    
    def delete_chart(self, chart_id: str, user_id: int) -> bool:
        """Delete a chart (soft delete)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE saved_charts SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (chart_id, user_id))
            
            if cursor.rowcount > 0:
                # Actually delete the chart and its versions
                cursor.execute('DELETE FROM chart_versions WHERE chart_id = ?', (chart_id,))
                cursor.execute('DELETE FROM chart_shares WHERE chart_id = ?', (chart_id,))
                cursor.execute('DELETE FROM saved_charts WHERE id = ?', (chart_id,))
                conn.commit()
                return True
        
        return False
    
    def share_chart(self, chart_id: str, shared_by: int, shared_with: int = None,
                   share_type: str = 'user', expires_days: int = 30) -> Optional[str]:
        """Share a chart with another user or publicly"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if chart exists and user can share it
            cursor.execute('''
                SELECT * FROM saved_charts 
                WHERE id = ? AND (user_id = ? OR is_public = TRUE)
            ''', (chart_id, shared_by))
            
            if not cursor.fetchone():
                return None
            
            expires_at = datetime.now() + timedelta(days=expires_days)
            
            cursor.execute('''
                INSERT INTO chart_shares 
                (chart_id, shared_by, shared_with, share_type, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (chart_id, shared_by, shared_with, share_type, expires_at.isoformat()))
            
            conn.commit()
            return f"share_{cursor.lastrowid}"
    
    def get_chart_versions(self, chart_id: str, user_id: int) -> List[Dict]:
        """Get version history for a chart"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if user can access the chart
            cursor.execute('''
                SELECT 1 FROM saved_charts 
                WHERE id = ? AND (user_id = ? OR is_public = TRUE)
            ''', (chart_id, user_id))
            
            if not cursor.fetchone():
                return []
            
            cursor.execute('''
                SELECT cv.*, u.username 
                FROM chart_versions cv
                JOIN users u ON cv.created_by = u.id
                WHERE cv.chart_id = ?
                ORDER BY cv.version_number DESC
            ''', (chart_id,))
            
            versions = []
            for row in cursor.fetchall():
                versions.append({
                    'version_number': row['version_number'],
                    'chart_config': json.loads(row['chart_config']),
                    'change_description': row['change_description'],
                    'created_at': row['created_at'],
                    'created_by': row['username']
                })
            
            return versions
    
    def save_user_dashboard(self, user_id: int, name: str, layout_config: Dict,
                          chart_ids: List[str], is_default: bool = False) -> int:
        """Save user dashboard layout"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # If this is set as default, unset other defaults
            if is_default:
                cursor.execute('''
                    UPDATE user_dashboards SET is_default = FALSE WHERE user_id = ?
                ''', (user_id,))
            
            cursor.execute('''
                INSERT INTO user_dashboards 
                (user_id, name, layout_config, chart_ids, is_default)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                user_id, name, json.dumps(layout_config),
                json.dumps(chart_ids), is_default
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_user_dashboards(self, user_id: int) -> List[Dict]:
        """Get user's saved dashboards"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_dashboards 
                WHERE user_id = ? 
                ORDER BY is_default DESC, updated_at DESC
            ''', (user_id,))
            
            dashboards = []
            for row in cursor.fetchall():
                dashboards.append({
                    'id': row['id'],
                    'name': row['name'],
                    'layout_config': json.loads(row['layout_config']),
                    'chart_ids': json.loads(row['chart_ids']),
                    'is_default': bool(row['is_default']),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                })
            
            return dashboards

class WindowsApplicationIntegration:
    """Integration with Windows default applications"""
    
    @staticmethod
    def open_with_default_app(file_path: Path) -> bool:
        """Open file with Windows default application"""
        try:
            os.startfile(str(file_path))
            return True
        except Exception:
            return False
    
    @staticmethod
    def open_in_excel(file_path: Path) -> bool:
        """Open file in Microsoft Excel if available"""
        try:
            subprocess.run(['excel', str(file_path)], check=True)
            return True
        except Exception:
            return WindowsApplicationIntegration.open_with_default_app(file_path)
    
    @staticmethod
    def open_in_powerpoint(file_path: Path) -> bool:
        """Open file in Microsoft PowerPoint if available"""
        try:
            subprocess.run(['powerpnt', str(file_path)], check=True)
            return True
        except Exception:
            return WindowsApplicationIntegration.open_with_default_app(file_path)
    
    @staticmethod
    def send_to_onenote(content: str, title: str = "MIDAS Chart") -> bool:
        """Send content to Microsoft OneNote if available"""
        try:
            # This would require OneNote API integration
            # For now, just create an HTML file and open it
            temp_file = Path(tempfile.gettempdir()) / f"{title}.html"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(f"<html><head><title>{title}</title></head><body>{content}</body></html>")
            
            return WindowsApplicationIntegration.open_with_default_app(temp_file)
        except Exception:
            return False

class NetworkChartSharing:
    """Windows network-based chart sharing"""
    
    def __init__(self):
        self.network_available = WINDOWS_NETWORK_AVAILABLE
        self.share_base_path = Path(r"\\localhost\MIDAS_Charts") if self.network_available else None
    
    def setup_network_share(self, share_path: Path, share_name: str = "MIDAS_Charts") -> bool:
        """Setup Windows network share for chart sharing"""
        if not self.network_available:
            return False
        
        try:
            # Create the directory if it doesn't exist
            share_path.mkdir(parents=True, exist_ok=True)
            
            # Create network share (requires admin privileges)
            share_info = {
                'netname': share_name,
                'type': win32netcon.STYPE_DISKTREE,
                'remark': 'MIDAS Chart Sharing',
                'permissions': win32netcon.ACCESS_ALL,
                'max_uses': -1,
                'current_uses': 0,
                'path': str(share_path),
                'passwd': None
            }
            
            win32net.NetShareAdd(None, 2, share_info)
            return True
            
        except Exception:
            return False
    
    def share_chart_to_network(self, chart_id: str, user_id: int, 
                             chart_data: Dict, file_paths: Dict) -> Optional[str]:
        """Share chart to network location"""
        if not self.network_available or not self.share_base_path:
            return None
        
        try:
            # Create network share directory
            network_chart_dir = self.share_base_path / f"User_{user_id}" / chart_id
            network_chart_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy chart files to network location
            for file_type, file_path in file_paths.items():
                if Path(file_path).exists():
                    destination = network_chart_dir / Path(file_path).name
                    shutil.copy2(file_path, destination)
            
            # Create share metadata
            share_metadata = {
                'chart_id': chart_id,
                'user_id': user_id,
                'shared_at': datetime.now().isoformat(),
                'chart_data': chart_data
            }
            
            metadata_file = network_chart_dir / "share_info.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(share_metadata, f, indent=2, ensure_ascii=False)
            
            return str(network_chart_dir)
            
        except Exception:
            return None
    
    def get_network_shared_charts(self) -> List[Dict]:
        """Get charts shared on network"""
        if not self.network_available or not self.share_base_path or not self.share_base_path.exists():
            return []
        
        shared_charts = []
        
        try:
            for user_dir in self.share_base_path.iterdir():
                if user_dir.is_dir() and user_dir.name.startswith("User_"):
                    for chart_dir in user_dir.iterdir():
                        if chart_dir.is_dir():
                            metadata_file = chart_dir / "share_info.json"
                            if metadata_file.exists():
                                try:
                                    with open(metadata_file, 'r', encoding='utf-8') as f:
                                        metadata = json.load(f)
                                    metadata['network_path'] = str(chart_dir)
                                    shared_charts.append(metadata)
                                except Exception:
                                    continue
        except Exception:
            pass
        
        return shared_charts

# Export main classes
__all__ = [
    'UserProfileDatabase',
    'ChartPersistenceManager', 
    'WindowsRegistryManager',
    'WindowsApplicationIntegration',
    'NetworkChartSharing'
]