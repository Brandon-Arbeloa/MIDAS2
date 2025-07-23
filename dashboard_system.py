"""
MIDAS Advanced Dashboard System
Manages dashboard layouts, configurations, and persistence on Windows
"""

import json
import os
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import uuid
import logging

# Windows-specific imports
import win32api
import win32con
import ctypes
from ctypes import wintypes

logger = logging.getLogger(__name__)

@dataclass
class ChartConfig:
    """Configuration for a single chart"""
    id: str
    type: str  # line, bar, scatter, pie, heatmap, etc.
    title: str
    data_source: Dict[str, Any]
    position: Dict[str, int]  # row, col, width, height
    options: Dict[str, Any]
    filters: List[Dict[str, Any]]

@dataclass
class DashboardConfig:
    """Complete dashboard configuration"""
    id: str
    name: str
    description: str
    layout: Dict[str, Any]
    charts: List[ChartConfig]
    theme: str
    filters: List[Dict[str, Any]]
    refresh_interval: Optional[int]
    created_at: str
    updated_at: str
    version: int
    author: str

class WindowsDisplayManager:
    """Manages Windows display settings and DPI awareness"""
    
    def __init__(self):
        self._set_dpi_awareness()
        self.monitors = self._get_monitor_info()
    
    def _set_dpi_awareness(self):
        """Set DPI awareness for Windows"""
        try:
            # Windows 10 version 1703+
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        except:
            try:
                # Windows 8.1+
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
            except:
                # Windows Vista+
                ctypes.windll.user32.SetProcessDPIAware()
    
    def _get_monitor_info(self) -> List[Dict[str, Any]]:
        """Get information about all monitors"""
        monitors = []
        
        def monitor_enum_proc(hMonitor, hdcMonitor, lprcMonitor, dwData):
            """Callback for monitor enumeration"""
            # Define MONITORINFOEX structure
            class MONITORINFOEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                    ("szDevice", wintypes.WCHAR * 32)
                ]
            
            info = MONITORINFOEX()
            info.cbSize = ctypes.sizeof(info)
            if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
                monitor_data = {
                    'name': info.szDevice,
                    'primary': bool(info.dwFlags & 1),  # MONITORINFOF_PRIMARY
                    'x': info.rcMonitor.left,
                    'y': info.rcMonitor.top,
                    'width': info.rcMonitor.right - info.rcMonitor.left,
                    'height': info.rcMonitor.bottom - info.rcMonitor.top,
                    'work_x': info.rcWork.left,
                    'work_y': info.rcWork.top,
                    'work_width': info.rcWork.right - info.rcWork.left,
                    'work_height': info.rcWork.bottom - info.rcWork.top
                }
                
                # Get DPI
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                ctypes.windll.shcore.GetDpiForMonitor(
                    hMonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
                )
                monitor_data['dpi_x'] = dpi_x.value
                monitor_data['dpi_y'] = dpi_y.value
                monitor_data['scale_factor'] = dpi_x.value / 96.0
                
                monitors.append(monitor_data)
            return True
        
        # Enumerate monitors
        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.POINTER(wintypes.RECT),
            ctypes.c_ulong
        )
        
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MonitorEnumProc(monitor_enum_proc), 0
        )
        
        return monitors
    
    def get_primary_monitor(self) -> Optional[Dict[str, Any]]:
        """Get primary monitor info"""
        for monitor in self.monitors:
            if monitor['primary']:
                return monitor
        return self.monitors[0] if self.monitors else None
    
    def get_total_desktop_size(self) -> Tuple[int, int]:
        """Get total size of all monitors combined"""
        if not self.monitors:
            return (1920, 1080)  # Default
        
        min_x = min(m['x'] for m in self.monitors)
        min_y = min(m['y'] for m in self.monitors)
        max_x = max(m['x'] + m['width'] for m in self.monitors)
        max_y = max(m['y'] + m['height'] for m in self.monitors)
        
        return (max_x - min_x, max_y - min_y)

class DashboardStorage:
    """Handles dashboard persistence in Windows AppData and SQLite"""
    
    def __init__(self):
        # Get Windows AppData directory
        self.app_data_dir = Path(os.environ['APPDATA']) / 'MIDAS' / 'Dashboards'
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Database path
        self.db_path = self.app_data_dir / 'dashboards.db'
        
        # Templates directory
        self.templates_dir = self.app_data_dir / 'templates'
        self.templates_dir.mkdir(exist_ok=True)
        
        # Themes directory
        self.themes_dir = self.app_data_dir / 'themes'
        self.themes_dir.mkdir(exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Initialize default templates and themes
        self._init_defaults()
    
    def _init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Dashboards table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboards (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                config TEXT NOT NULL,
                theme TEXT,
                author TEXT,
                created_at TEXT,
                updated_at TEXT,
                version INTEGER DEFAULT 1,
                is_template BOOLEAN DEFAULT 0
            )
        """)
        
        # Dashboard versions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dashboard_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                config TEXT NOT NULL,
                created_at TEXT,
                author TEXT,
                change_description TEXT,
                FOREIGN KEY (dashboard_id) REFERENCES dashboards(id)
            )
        """)
        
        # Shared dashboards table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shared_dashboards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dashboard_id TEXT NOT NULL,
                shared_path TEXT NOT NULL,
                shared_by TEXT,
                shared_at TEXT,
                expires_at TEXT,
                access_count INTEGER DEFAULT 0,
                FOREIGN KEY (dashboard_id) REFERENCES dashboards(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def _init_defaults(self):
        """Initialize default templates and themes"""
        # Default themes
        default_themes = {
            'light': {
                'name': 'Light',
                'background': '#FFFFFF',
                'text': '#000000',
                'primary': '#1976D2',
                'secondary': '#DC004E',
                'success': '#4CAF50',
                'warning': '#FF9800',
                'error': '#F44336',
                'grid': '#E0E0E0'
            },
            'dark': {
                'name': 'Dark',
                'background': '#121212',
                'text': '#FFFFFF',
                'primary': '#90CAF9',
                'secondary': '#F48FB1',
                'success': '#81C784',
                'warning': '#FFB74D',
                'error': '#E57373',
                'grid': '#424242'
            },
            'corporate': {
                'name': 'Corporate',
                'background': '#F5F5F5',
                'text': '#333333',
                'primary': '#003366',
                'secondary': '#666666',
                'success': '#008000',
                'warning': '#FFA500',
                'error': '#CC0000',
                'grid': '#CCCCCC'
            }
        }
        
        for theme_id, theme_data in default_themes.items():
            theme_path = self.themes_dir / f"{theme_id}.json"
            if not theme_path.exists():
                with open(theme_path, 'w') as f:
                    json.dump(theme_data, f, indent=2)
        
        # Default templates
        default_templates = {
            'overview': {
                'name': 'Overview Dashboard',
                'description': 'General purpose dashboard with key metrics',
                'layout': {
                    'type': 'grid',
                    'columns': 12,
                    'row_height': 80
                },
                'charts': [
                    {
                        'type': 'metric',
                        'position': {'row': 0, 'col': 0, 'width': 3, 'height': 1},
                        'title': 'Total Records'
                    },
                    {
                        'type': 'metric',
                        'position': {'row': 0, 'col': 3, 'width': 3, 'height': 1},
                        'title': 'Active Users'
                    },
                    {
                        'type': 'metric',
                        'position': {'row': 0, 'col': 6, 'width': 3, 'height': 1},
                        'title': 'Success Rate'
                    },
                    {
                        'type': 'metric',
                        'position': {'row': 0, 'col': 9, 'width': 3, 'height': 1},
                        'title': 'Performance'
                    },
                    {
                        'type': 'line',
                        'position': {'row': 1, 'col': 0, 'width': 6, 'height': 3},
                        'title': 'Trend Analysis'
                    },
                    {
                        'type': 'bar',
                        'position': {'row': 1, 'col': 6, 'width': 6, 'height': 3},
                        'title': 'Category Distribution'
                    }
                ]
            },
            'analytics': {
                'name': 'Analytics Dashboard',
                'description': 'Detailed analytics with multiple visualizations',
                'layout': {
                    'type': 'grid',
                    'columns': 12,
                    'row_height': 80
                },
                'charts': [
                    {
                        'type': 'line',
                        'position': {'row': 0, 'col': 0, 'width': 8, 'height': 3},
                        'title': 'Time Series Analysis'
                    },
                    {
                        'type': 'pie',
                        'position': {'row': 0, 'col': 8, 'width': 4, 'height': 3},
                        'title': 'Distribution'
                    },
                    {
                        'type': 'heatmap',
                        'position': {'row': 3, 'col': 0, 'width': 6, 'height': 3},
                        'title': 'Correlation Matrix'
                    },
                    {
                        'type': 'scatter',
                        'position': {'row': 3, 'col': 6, 'width': 6, 'height': 3},
                        'title': 'Scatter Analysis'
                    }
                ]
            }
        }
        
        for template_id, template_data in default_templates.items():
            self.save_template(template_id, template_data)
    
    def save_dashboard(self, config: DashboardConfig) -> bool:
        """Save dashboard configuration"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert config to JSON
            config_json = json.dumps(asdict(config))
            
            # Check if exists
            cursor.execute("SELECT version FROM dashboards WHERE id = ?", (config.id,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing
                old_version = existing[0]
                new_version = old_version + 1
                
                # Save version history
                cursor.execute("""
                    INSERT INTO dashboard_versions 
                    (dashboard_id, version, config, created_at, author, change_description)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (config.id, old_version, config_json, datetime.now().isoformat(),
                     config.author, "Dashboard updated"))
                
                # Update dashboard
                cursor.execute("""
                    UPDATE dashboards 
                    SET name = ?, description = ?, config = ?, theme = ?,
                        updated_at = ?, version = ?
                    WHERE id = ?
                """, (config.name, config.description, config_json, config.theme,
                     datetime.now().isoformat(), new_version, config.id))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO dashboards 
                    (id, name, description, config, theme, author, created_at, updated_at, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (config.id, config.name, config.description, config_json,
                     config.theme, config.author, config.created_at, config.updated_at, 1))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save dashboard: {e}")
            return False
    
    def load_dashboard(self, dashboard_id: str) -> Optional[DashboardConfig]:
        """Load dashboard configuration"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT config FROM dashboards WHERE id = ?", (dashboard_id,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                config_data = json.loads(result[0])
                # Convert chart configs
                config_data['charts'] = [
                    ChartConfig(**chart) for chart in config_data['charts']
                ]
                return DashboardConfig(**config_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to load dashboard: {e}")
            return None
    
    def list_dashboards(self) -> List[Dict[str, Any]]:
        """List all dashboards"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, name, description, theme, author, created_at, updated_at, version
                FROM dashboards
                WHERE is_template = 0
                ORDER BY updated_at DESC
            """)
            
            dashboards = []
            for row in cursor.fetchall():
                dashboards.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'theme': row[3],
                    'author': row[4],
                    'created_at': row[5],
                    'updated_at': row[6],
                    'version': row[7]
                })
            
            conn.close()
            return dashboards
            
        except Exception as e:
            logger.error(f"Failed to list dashboards: {e}")
            return []
    
    def save_template(self, template_id: str, template_data: Dict[str, Any]) -> bool:
        """Save dashboard template"""
        template_path = self.templates_dir / f"{template_id}.json"
        try:
            with open(template_path, 'w') as f:
                json.dump(template_data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save template: {e}")
            return False
    
    def load_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Load dashboard template"""
        template_path = self.templates_dir / f"{template_id}.json"
        if template_path.exists():
            try:
                with open(template_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load template: {e}")
        return None
    
    def list_templates(self) -> List[Dict[str, Any]]:
        """List available templates"""
        templates = []
        for template_file in self.templates_dir.glob('*.json'):
            try:
                with open(template_file, 'r') as f:
                    template_data = json.load(f)
                    templates.append({
                        'id': template_file.stem,
                        'name': template_data.get('name', template_file.stem),
                        'description': template_data.get('description', '')
                    })
            except:
                pass
        return templates
    
    def load_theme(self, theme_id: str) -> Optional[Dict[str, Any]]:
        """Load theme configuration"""
        theme_path = self.themes_dir / f"{theme_id}.json"
        if theme_path.exists():
            try:
                with open(theme_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load theme: {e}")
        return None
    
    def list_themes(self) -> List[Dict[str, Any]]:
        """List available themes"""
        themes = []
        for theme_file in self.themes_dir.glob('*.json'):
            try:
                with open(theme_file, 'r') as f:
                    theme_data = json.load(f)
                    themes.append({
                        'id': theme_file.stem,
                        'name': theme_data.get('name', theme_file.stem)
                    })
            except:
                pass
        return themes
    
    def export_dashboard(self, dashboard_id: str, export_path: str) -> bool:
        """Export dashboard to file"""
        config = self.load_dashboard(dashboard_id)
        if config:
            try:
                with open(export_path, 'w') as f:
                    json.dump(asdict(config), f, indent=2)
                return True
            except Exception as e:
                logger.error(f"Failed to export dashboard: {e}")
        return False
    
    def import_dashboard(self, import_path: str) -> Optional[str]:
        """Import dashboard from file"""
        try:
            with open(import_path, 'r') as f:
                config_data = json.load(f)
            
            # Generate new ID to avoid conflicts
            config_data['id'] = str(uuid.uuid4())
            config_data['imported_at'] = datetime.now().isoformat()
            
            # Convert to DashboardConfig
            config_data['charts'] = [
                ChartConfig(**chart) for chart in config_data['charts']
            ]
            config = DashboardConfig(**config_data)
            
            if self.save_dashboard(config):
                return config.id
            
        except Exception as e:
            logger.error(f"Failed to import dashboard: {e}")
        
        return None
    
    def share_dashboard(self, dashboard_id: str, share_path: str, 
                       expires_days: Optional[int] = None) -> bool:
        """Share dashboard via network path"""
        try:
            # Export dashboard to share path
            if not self.export_dashboard(dashboard_id, share_path):
                return False
            
            # Record share
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            expires_at = None
            if expires_days:
                expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
            
            cursor.execute("""
                INSERT INTO shared_dashboards
                (dashboard_id, shared_path, shared_by, shared_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (dashboard_id, share_path, win32api.GetUserName(),
                 datetime.now().isoformat(), expires_at))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to share dashboard: {e}")
            return False
    
    def get_dashboard_versions(self, dashboard_id: str) -> List[Dict[str, Any]]:
        """Get version history for dashboard"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT version, created_at, author, change_description
                FROM dashboard_versions
                WHERE dashboard_id = ?
                ORDER BY version DESC
            """, (dashboard_id,))
            
            versions = []
            for row in cursor.fetchall():
                versions.append({
                    'version': row[0],
                    'created_at': row[1],
                    'author': row[2],
                    'change_description': row[3]
                })
            
            conn.close()
            return versions
            
        except Exception as e:
            logger.error(f"Failed to get dashboard versions: {e}")
            return []
    
    def restore_dashboard_version(self, dashboard_id: str, version: int) -> bool:
        """Restore dashboard to specific version"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get version config
            cursor.execute("""
                SELECT config FROM dashboard_versions
                WHERE dashboard_id = ? AND version = ?
            """, (dashboard_id, version))
            
            result = cursor.fetchone()
            if not result:
                return False
            
            config_json = result[0]
            
            # Update dashboard
            cursor.execute("""
                UPDATE dashboards
                SET config = ?, updated_at = ?, version = version + 1
                WHERE id = ?
            """, (config_json, datetime.now().isoformat(), dashboard_id))
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore dashboard version: {e}")
            return False

class DashboardManager:
    """Main dashboard management class"""
    
    def __init__(self):
        self.storage = DashboardStorage()
        self.display_manager = WindowsDisplayManager()
        self.current_dashboard = None
    
    def create_dashboard(self, name: str, description: str = "", 
                        template_id: Optional[str] = None) -> DashboardConfig:
        """Create new dashboard"""
        dashboard_id = str(uuid.uuid4())
        
        if template_id:
            template = self.storage.load_template(template_id)
            if template:
                charts = [
                    ChartConfig(
                        id=str(uuid.uuid4()),
                        type=chart['type'],
                        title=chart['title'],
                        data_source={},
                        position=chart['position'],
                        options={},
                        filters=[]
                    )
                    for chart in template.get('charts', [])
                ]
                layout = template.get('layout', {'type': 'grid', 'columns': 12})
            else:
                charts = []
                layout = {'type': 'grid', 'columns': 12, 'row_height': 80}
        else:
            charts = []
            layout = {'type': 'grid', 'columns': 12, 'row_height': 80}
        
        config = DashboardConfig(
            id=dashboard_id,
            name=name,
            description=description,
            layout=layout,
            charts=charts,
            theme='light',
            filters=[],
            refresh_interval=None,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            version=1,
            author=win32api.GetUserName()
        )
        
        self.storage.save_dashboard(config)
        return config
    
    def add_chart(self, dashboard_id: str, chart_type: str, 
                  title: str, position: Dict[str, int]) -> Optional[ChartConfig]:
        """Add chart to dashboard"""
        config = self.storage.load_dashboard(dashboard_id)
        if not config:
            return None
        
        chart = ChartConfig(
            id=str(uuid.uuid4()),
            type=chart_type,
            title=title,
            data_source={},
            position=position,
            options={},
            filters=[]
        )
        
        config.charts.append(chart)
        config.updated_at = datetime.now().isoformat()
        
        if self.storage.save_dashboard(config):
            return chart
        
        return None
    
    def update_chart(self, dashboard_id: str, chart_id: str, 
                    updates: Dict[str, Any]) -> bool:
        """Update chart configuration"""
        config = self.storage.load_dashboard(dashboard_id)
        if not config:
            return False
        
        for chart in config.charts:
            if chart.id == chart_id:
                for key, value in updates.items():
                    if hasattr(chart, key):
                        setattr(chart, key, value)
                
                config.updated_at = datetime.now().isoformat()
                return self.storage.save_dashboard(config)
        
        return False
    
    def remove_chart(self, dashboard_id: str, chart_id: str) -> bool:
        """Remove chart from dashboard"""
        config = self.storage.load_dashboard(dashboard_id)
        if not config:
            return False
        
        config.charts = [c for c in config.charts if c.id != chart_id]
        config.updated_at = datetime.now().isoformat()
        
        return self.storage.save_dashboard(config)
    
    def get_optimal_layout(self, num_charts: int) -> List[Dict[str, int]]:
        """Get optimal layout positions for number of charts"""
        if num_charts == 1:
            return [{'row': 0, 'col': 0, 'width': 12, 'height': 4}]
        elif num_charts == 2:
            return [
                {'row': 0, 'col': 0, 'width': 6, 'height': 4},
                {'row': 0, 'col': 6, 'width': 6, 'height': 4}
            ]
        elif num_charts == 3:
            return [
                {'row': 0, 'col': 0, 'width': 12, 'height': 3},
                {'row': 3, 'col': 0, 'width': 6, 'height': 3},
                {'row': 3, 'col': 6, 'width': 6, 'height': 3}
            ]
        elif num_charts == 4:
            return [
                {'row': 0, 'col': 0, 'width': 6, 'height': 3},
                {'row': 0, 'col': 6, 'width': 6, 'height': 3},
                {'row': 3, 'col': 0, 'width': 6, 'height': 3},
                {'row': 3, 'col': 6, 'width': 6, 'height': 3}
            ]
        else:
            # Grid layout
            cols = 3
            positions = []
            for i in range(num_charts):
                row = (i // cols) * 3
                col = (i % cols) * 4
                positions.append({
                    'row': row,
                    'col': col,
                    'width': 4,
                    'height': 3
                })
            return positions

# Utility functions
def get_user_dashboards_path() -> Path:
    """Get user's dashboards directory"""
    return Path(os.environ['APPDATA']) / 'MIDAS' / 'Dashboards'

def get_shared_dashboards_path() -> Path:
    """Get shared dashboards network path"""
    # This could be configured per organization
    return Path(r"\\server\shared\MIDAS\Dashboards")

if __name__ == "__main__":
    # Test dashboard system
    manager = DashboardManager()
    
    # List templates
    templates = manager.storage.list_templates()
    print("Available templates:", templates)
    
    # Create dashboard from template
    dashboard = manager.create_dashboard(
        "Test Dashboard",
        "Testing dashboard system",
        template_id="overview"
    )
    print(f"Created dashboard: {dashboard.id}")
    
    # List dashboards
    dashboards = manager.storage.list_dashboards()
    print(f"Total dashboards: {len(dashboards)}")