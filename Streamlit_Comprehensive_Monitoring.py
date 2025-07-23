"""
MIDAS Comprehensive Monitoring Dashboard
Real-time monitoring of all system components on Windows 11
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import psutil
import time
import json
import subprocess
import platform
from datetime import datetime, timedelta
from pathlib import Path
import sys
import logging
from typing import Dict, List, Any, Optional
import sqlite3
import win32evtlog
import win32evtlogutil
import win32con
import csv
import openpyxl
from io import BytesIO

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

try:
    from celery_config import app
    from celery.result import AsyncResult
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct
    from background_tasks.document_tasks import process_document_file
    from background_tasks.monitoring_tasks import system_health_check, generate_task_report
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    st.warning("Celery not available. Some features will be limited.")

# Page configuration
st.set_page_config(
    page_title="MIDAS System Monitor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .status-healthy { color: #28a745; font-weight: bold; }
    .status-warning { color: #ffc107; font-weight: bold; }
    .status-error { color: #dc3545; font-weight: bold; }
    .service-running { background-color: #28a745; color: white; padding: 5px 10px; border-radius: 15px; }
    .service-stopped { background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 15px; }
    .task-card {
        background: white;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
        border-left: 4px solid #007bff;
    }
    div[data-testid="stExpander"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True
if 'refresh_interval' not in st.session_state:
    st.session_state.refresh_interval = 5
if 'event_log_cache' not in st.session_state:
    st.session_state.event_log_cache = []

class SystemMonitor:
    """Main system monitoring class"""
    
    def __init__(self):
        self.qdrant_client = None
        self.init_qdrant()
    
    def init_qdrant(self):
        """Initialize Qdrant client"""
        try:
            self.qdrant_client = QdrantClient(host="localhost", port=6333)
        except:
            self.qdrant_client = None
    
    def get_windows_services_status(self) -> Dict[str, Dict]:
        """Get status of key Windows services"""
        services = {
            'Redis': 'Redis',
            'PostgreSQL': 'postgresql-x64-*',
            'Ollama': 'ollama',
            'Qdrant': 'qdrant'
        }
        
        status = {}
        for display_name, service_name in services.items():
            try:
                result = subprocess.run(
                    ['sc', 'query', service_name],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                
                if 'RUNNING' in result.stdout:
                    status[display_name] = {
                        'status': 'running',
                        'state': 'SERVICE_RUNNING',
                        'icon': '🟢'
                    }
                elif 'STOPPED' in result.stdout:
                    status[display_name] = {
                        'status': 'stopped',
                        'state': 'SERVICE_STOPPED',
                        'icon': '🔴'
                    }
                else:
                    status[display_name] = {
                        'status': 'not_found',
                        'state': 'NOT_INSTALLED',
                        'icon': '⚪'
                    }
            except Exception as e:
                status[display_name] = {
                    'status': 'error',
                    'state': str(e),
                    'icon': '❌'
                }
        
        return status
    
    def get_system_resources(self) -> Dict[str, Any]:
        """Get system resource usage"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Get network stats
        net_io = psutil.net_io_counters()
        
        # Get process count
        process_count = len(psutil.pids())
        
        # Windows-specific: Get handle count
        if platform.system() == 'Windows':
            try:
                import win32api
                handle_count = win32api.GetHandleCount()
            except:
                handle_count = 0
        else:
            handle_count = 0
        
        return {
            'cpu': {
                'percent': cpu_percent,
                'count': psutil.cpu_count(logical=False),
                'logical_count': psutil.cpu_count(logical=True),
                'freq': psutil.cpu_freq().current if psutil.cpu_freq() else 0
            },
            'memory': {
                'total': memory.total,
                'available': memory.available,
                'percent': memory.percent,
                'used': memory.used
            },
            'disk': {
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': disk.percent
            },
            'network': {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            },
            'system': {
                'process_count': process_count,
                'handle_count': handle_count,
                'boot_time': datetime.fromtimestamp(psutil.boot_time())
            }
        }
    
    def get_celery_stats(self) -> Dict[str, Any]:
        """Get Celery queue and worker statistics"""
        if not CELERY_AVAILABLE:
            return {'error': 'Celery not available'}
        
        try:
            inspector = app.control.inspect()
            
            # Get active tasks
            active = inspector.active() or {}
            active_count = sum(len(tasks) for tasks in active.values())
            
            # Get scheduled tasks
            scheduled = inspector.scheduled() or {}
            scheduled_count = sum(len(tasks) for tasks in scheduled.values())
            
            # Get reserved tasks
            reserved = inspector.reserved() or {}
            reserved_count = sum(len(tasks) for tasks in reserved.values())
            
            # Get worker stats
            stats = inspector.stats() or {}
            
            # Get registered tasks
            registered = inspector.registered() or {}
            
            return {
                'workers': len(active),
                'active_tasks': active_count,
                'scheduled_tasks': scheduled_count,
                'reserved_tasks': reserved_count,
                'active_details': active,
                'stats': stats,
                'registered_tasks': registered
            }
        except Exception as e:
            return {'error': str(e)}
    
    def get_qdrant_stats(self) -> Dict[str, Any]:
        """Get Qdrant vector database statistics"""
        if not self.qdrant_client:
            return {'error': 'Qdrant not connected'}
        
        try:
            # Get collections
            collections = self.qdrant_client.get_collections()
            
            stats = {
                'collections': [],
                'total_vectors': 0,
                'total_collections': len(collections.collections)
            }
            
            # Get details for each collection
            for collection in collections.collections:
                try:
                    info = self.qdrant_client.get_collection(collection.name)
                    stats['collections'].append({
                        'name': collection.name,
                        'vectors_count': info.vectors_count,
                        'points_count': info.points_count,
                        'indexed_vectors_count': info.indexed_vectors_count,
                        'status': info.status
                    })
                    stats['total_vectors'] += info.vectors_count
                except:
                    pass
            
            return stats
        except Exception as e:
            return {'error': str(e)}
    
    def get_windows_event_logs(self, log_type: str = "Application", 
                            max_records: int = 100) -> List[Dict]:
        """Get Windows Event Logs"""
        events = []
        
        try:
            hand = win32evtlog.OpenEventLog(None, log_type)
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            
            # Get events
            total = win32evtlog.GetNumberOfEventLogRecords(hand)
            events_read = 0
            
            while events_read < max_records:
                event_batch = win32evtlog.ReadEventLog(hand, flags, 0)
                if not event_batch:
                    break
                
                for event in event_batch:
                    if events_read >= max_records:
                        break
                    
                    # Filter for MIDAS-related events
                    if any(keyword in str(event.SourceName).lower() 
                          for keyword in ['python', 'celery', 'redis', 'midas']):
                        
                        event_data = {
                            'TimeGenerated': event.TimeGenerated.Format(),
                            'SourceName': event.SourceName,
                            'EventID': event.EventID,
                            'EventType': event.EventType,
                            'EventCategory': event.EventCategory,
                            'StringInserts': event.StringInserts
                        }
                        
                        # Determine severity
                        if event.EventType == win32con.EVENTLOG_ERROR_TYPE:
                            event_data['Severity'] = 'ERROR'
                        elif event.EventType == win32con.EVENTLOG_WARNING_TYPE:
                            event_data['Severity'] = 'WARNING'
                        else:
                            event_data['Severity'] = 'INFO'
                        
                        events.append(event_data)
                        events_read += 1
            
            win32evtlog.CloseEventLog(hand)
        except Exception as e:
            st.error(f"Failed to read Windows Event Log: {e}")
        
        return events
    
    def get_task_history(self, hours: int = 24) -> pd.DataFrame:
        """Get task execution history from SQLite"""
        try:
            db_path = Path(__file__).parent / 'data' / 'celery_results.db'
            if not db_path.exists():
                return pd.DataFrame()
            
            conn = sqlite3.connect(db_path)
            
            # Query recent tasks
            query = """
                SELECT task_id, status, date_done, result, traceback
                FROM celery_taskmeta
                WHERE date_done > datetime('now', '-{} hours')
                ORDER BY date_done DESC
            """.format(hours)
            
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            # Parse timestamps
            if not df.empty:
                df['date_done'] = pd.to_datetime(df['date_done'])
            
            return df
        except Exception as e:
            return pd.DataFrame()

monitor = SystemMonitor()

def render_service_status():
    """Render Windows service status"""
    st.subheader("🖥️ Windows Services Status")
    
    services = monitor.get_windows_services_status()
    
    cols = st.columns(len(services))
    for idx, (service_name, status) in enumerate(services.items()):
        with cols[idx]:
            st.markdown(f"### {service_name}")
            
            if status['status'] == 'running':
                st.markdown(f"<span class='service-running'>{status['icon']} Running</span>", 
                           unsafe_allow_html=True)
            elif status['status'] == 'stopped':
                st.markdown(f"<span class='service-stopped'>{status['icon']} Stopped</span>", 
                           unsafe_allow_html=True)
            else:
                st.markdown(f"{status['icon']} {status['state']}")
            
            # Service control buttons
            if service_name in ['Redis', 'PostgreSQL']:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"Start", key=f"start_{service_name}"):
                        try:
                            subprocess.run(['net', 'start', service_name], shell=True)
                            st.rerun()
                        except:
                            st.error(f"Failed to start {service_name}")
                
                with col2:
                    if st.button(f"Stop", key=f"stop_{service_name}"):
                        try:
                            subprocess.run(['net', 'stop', service_name], shell=True)
                            st.rerun()
                        except:
                            st.error(f"Failed to stop {service_name}")

def render_system_resources():
    """Render system resource monitoring"""
    st.subheader("💻 System Resources")
    
    resources = monitor.get_system_resources()
    
    # Create gauge charts
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=('CPU Usage', 'Memory Usage', 'Disk Usage'),
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}]]
    )
    
    # CPU Gauge
    fig.add_trace(
        go.Indicator(
            mode="gauge+number+delta",
            value=resources['cpu']['percent'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"CPU ({resources['cpu']['count']} cores)"},
            delta={'reference': 50},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 80], 'color': "yellow"},
                    {'range': [80, 100], 'color': "red"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ),
        row=1, col=1
    )
    
    # Memory Gauge
    fig.add_trace(
        go.Indicator(
            mode="gauge+number+delta",
            value=resources['memory']['percent'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"Memory ({resources['memory']['total'] / (1024**3):.1f} GB)"},
            delta={'reference': 50},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkgreen"},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 80], 'color': "yellow"},
                    {'range': [80, 100], 'color': "red"}
                ]
            }
        ),
        row=1, col=2
    )
    
    # Disk Gauge
    fig.add_trace(
        go.Indicator(
            mode="gauge+number+delta",
            value=resources['disk']['percent'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"Disk ({resources['disk']['total'] / (1024**3):.1f} GB)"},
            delta={'reference': 50},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkred"},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 80], 'color': "yellow"},
                    {'range': [80, 100], 'color': "red"}
                ]
            }
        ),
        row=1, col=3
    )
    
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)
    
    # Additional metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🔄 Processes", resources['system']['process_count'])
    
    with col2:
        st.metric("📊 Handles", resources['system']['handle_count'])
    
    with col3:
        st.metric("📡 Network Sent", 
                 f"{resources['network']['bytes_sent'] / (1024**2):.1f} MB")
    
    with col4:
        st.metric("📡 Network Recv", 
                 f"{resources['network']['bytes_recv'] / (1024**2):.1f} MB")

def render_task_queue_status():
    """Render Celery task queue status"""
    st.subheader("📋 Task Queue Status")
    
    if not CELERY_AVAILABLE:
        st.warning("Celery is not available. Please ensure Celery is installed and configured.")
        return
    
    stats = monitor.get_celery_stats()
    
    if 'error' in stats:
        st.error(f"Failed to get Celery stats: {stats['error']}")
        st.info("Make sure Celery services are running: `.\\Start-Celery-Services.ps1`")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("👷 Workers", stats.get('workers', 0))
    
    with col2:
        st.metric("🔄 Active Tasks", stats.get('active_tasks', 0))
    
    with col3:
        st.metric("📅 Scheduled", stats.get('scheduled_tasks', 0))
    
    with col4:
        st.metric("🎯 Reserved", stats.get('reserved_tasks', 0))
    
    # Active tasks details
    if stats.get('active_details'):
        st.markdown("### Active Tasks")
        for worker, tasks in stats['active_details'].items():
            if tasks:
                with st.expander(f"Worker: {worker} ({len(tasks)} tasks)"):
                    for task in tasks:
                        st.markdown(f"""
                        <div class='task-card'>
                        <strong>Task:</strong> {task.get('name', 'Unknown')}<br>
                        <strong>ID:</strong> {task.get('id', 'N/A')[:12]}...<br>
                        <strong>Args:</strong> {str(task.get('args', []))[:100]}...
                        </div>
                        """, unsafe_allow_html=True)

def render_qdrant_stats():
    """Render Qdrant vector database statistics"""
    st.subheader("🔍 Qdrant Vector Database")
    
    stats = monitor.get_qdrant_stats()
    
    if 'error' in stats:
        st.warning(f"Qdrant not connected: {stats['error']}")
        return
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("📚 Collections", stats.get('total_collections', 0))
    
    with col2:
        st.metric("🔢 Total Vectors", stats.get('total_vectors', 0))
    
    with col3:
        avg_vectors = (stats.get('total_vectors', 0) / max(stats.get('total_collections', 1), 1))
        st.metric("📊 Avg Vectors/Collection", f"{avg_vectors:.0f}")
    
    # Collection details
    if stats.get('collections'):
        df = pd.DataFrame(stats['collections'])
        
        # Create bar chart
        if not df.empty:
            fig = px.bar(df, x='name', y='vectors_count', 
                        title='Vectors per Collection',
                        labels={'vectors_count': 'Vector Count', 'name': 'Collection'})
            st.plotly_chart(fig, use_container_width=True)
            
            # Show table
            st.dataframe(df, hide_index=True, use_container_width=True)

def render_event_logs():
    """Render Windows Event Logs"""
    st.subheader("📝 Windows Event Logs")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        log_type = st.selectbox(
            "Log Type",
            ["Application", "System", "Security"],
            key="event_log_type"
        )
    
    with col2:
        max_records = st.number_input(
            "Max Records",
            min_value=10,
            max_value=500,
            value=100,
            step=10
        )
    
    with col3:
        if st.button("🔄 Refresh Logs"):
            st.session_state.event_log_cache = []
    
    # Get events
    if not st.session_state.event_log_cache:
        with st.spinner("Loading event logs..."):
            st.session_state.event_log_cache = monitor.get_windows_event_logs(
                log_type, max_records
            )
    
    events = st.session_state.event_log_cache
    
    if events:
        # Convert to DataFrame
        df = pd.DataFrame(events)
        
        # Filter by severity
        severity_filter = st.multiselect(
            "Filter by Severity",
            ["ERROR", "WARNING", "INFO"],
            default=["ERROR", "WARNING"]
        )
        
        if severity_filter:
            df = df[df['Severity'].isin(severity_filter)]
        
        # Display events
        for _, event in df.iterrows():
            severity_color = {
                'ERROR': '#dc3545',
                'WARNING': '#ffc107',
                'INFO': '#17a2b8'
            }.get(event['Severity'], '#6c757d')
            
            st.markdown(f"""
            <div style='border-left: 4px solid {severity_color}; padding-left: 10px; margin: 10px 0;'>
            <strong>{event['TimeGenerated']}</strong> - 
            <span style='color: {severity_color}'>{event['Severity']}</span><br>
            <strong>Source:</strong> {event['SourceName']}<br>
            <strong>Event ID:</strong> {event['EventID']}<br>
            <strong>Details:</strong> {event.get('StringInserts', ['N/A'])[0] if event.get('StringInserts') else 'N/A'}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No relevant events found")

def render_manual_controls():
    """Render manual task triggering controls"""
    st.subheader("🎮 Manual Controls")
    
    if not CELERY_AVAILABLE:
        st.warning("Celery is not available for manual task triggering")
        return
    
    # File processing
    with st.expander("📄 Process Document"):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=['pdf', 'docx', 'txt', 'csv', 'xlsx']
        )
        
        if uploaded_file is not None:
            # Save uploaded file temporarily
            temp_path = Path(__file__).parent / 'temp' / uploaded_file.name
            temp_path.parent.mkdir(exist_ok=True)
            
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🚀 Process File"):
                    try:
                        result = process_document_file.delay(str(temp_path))
                        st.success(f"Task submitted! ID: {result.id}")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Failed to submit task: {e}")
            
            with col2:
                if st.button("🗑️ Clean Temp"):
                    try:
                        temp_path.unlink()
                        st.success("Temporary file deleted")
                    except:
                        pass
    
    # System tasks
    with st.expander("🔧 System Tasks"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("❤️ Run Health Check"):
                try:
                    result = system_health_check.delay()
                    st.success(f"Health check started! Task ID: {result.id}")
                except Exception as e:
                    st.error(f"Failed: {e}")
        
        with col2:
            if st.button("📊 Generate Report"):
                try:
                    result = generate_task_report.delay(period_hours=24)
                    st.success(f"Report generation started! Task ID: {result.id}")
                except Exception as e:
                    st.error(f"Failed: {e}")
        
        with col3:
            if st.button("🧹 Cleanup Old Tasks"):
                try:
                    from background_tasks.monitoring_tasks import cleanup_old_tasks
                    result = cleanup_old_tasks.delay(days=7)
                    st.success(f"Cleanup started! Task ID: {result.id}")
                except Exception as e:
                    st.error(f"Failed: {e}")

def render_export_controls():
    """Render export functionality"""
    st.subheader("📤 Export Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        export_type = st.selectbox(
            "Export Type",
            ["System Report", "Task History", "Event Logs", "Performance Metrics"]
        )
    
    with col2:
        export_format = st.selectbox(
            "Format",
            ["CSV", "Excel", "JSON"]
        )
    
    if st.button("📥 Generate Export"):
        with st.spinner("Generating export..."):
            try:
                if export_type == "System Report":
                    # Generate comprehensive system report
                    report = {
                        'generated_at': datetime.now().isoformat(),
                        'system_resources': monitor.get_system_resources(),
                        'services': monitor.get_windows_services_status(),
                        'celery_stats': monitor.get_celery_stats(),
                        'qdrant_stats': monitor.get_qdrant_stats()
                    }
                    
                    if export_format == "JSON":
                        data = json.dumps(report, indent=2)
                        st.download_button(
                            "📥 Download JSON",
                            data,
                            file_name=f"system_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json"
                        )
                    
                    elif export_format == "Excel":
                        # Create Excel file with multiple sheets
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            # System info
                            pd.DataFrame([report['system_resources']]).to_excel(
                                writer, sheet_name='System Resources', index=False
                            )
                            
                            # Services
                            pd.DataFrame(report['services']).T.to_excel(
                                writer, sheet_name='Services'
                            )
                        
                        output.seek(0)
                        st.download_button(
                            "📥 Download Excel",
                            output,
                            file_name=f"system_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                
                elif export_type == "Task History":
                    df = monitor.get_task_history(hours=168)  # Last week
                    
                    if export_format == "CSV":
                        csv = df.to_csv(index=False)
                        st.download_button(
                            "📥 Download CSV",
                            csv,
                            file_name=f"task_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    
                    elif export_format == "Excel":
                        output = BytesIO()
                        df.to_excel(output, index=False)
                        output.seek(0)
                        st.download_button(
                            "📥 Download Excel",
                            output,
                            file_name=f"task_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                
                st.success("Export generated successfully!")
                
            except Exception as e:
                st.error(f"Export failed: {e}")

def render_real_time_updates():
    """Render real-time update controls"""
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        st.session_state.auto_refresh = st.checkbox(
            "Auto Refresh",
            value=st.session_state.auto_refresh
        )
    
    with col2:
        if st.session_state.auto_refresh:
            st.session_state.refresh_interval = st.slider(
                "Refresh Interval (seconds)",
                min_value=2,
                max_value=60,
                value=st.session_state.refresh_interval
            )
    
    with col3:
        if st.button("🔄 Manual Refresh"):
            st.rerun()

def main():
    # Header
    st.title("🎯 MIDAS Comprehensive System Monitor")
    st.markdown("Real-time monitoring of all MIDAS components on Windows 11")
    
    # Real-time update controls
    render_real_time_updates()
    
    # Navigation tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview",
        "📋 Task Queue",
        "💻 System Resources",
        "📝 Event Logs",
        "🎮 Manual Controls",
        "📤 Export Data"
    ])
    
    with tab1:
        # Services status
        render_service_status()
        
        # Quick stats
        st.markdown("---")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Celery stats
            render_task_queue_status()
        
        with col2:
            # Qdrant stats
            render_qdrant_stats()
        
        # System resources preview
        st.markdown("---")
        resources = monitor.get_system_resources()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("CPU Usage", f"{resources['cpu']['percent']}%")
        with col2:
            st.metric("Memory Usage", f"{resources['memory']['percent']}%")
        with col3:
            st.metric("Disk Usage", f"{resources['disk']['percent']}%")
    
    with tab2:
        render_task_queue_status()
        
        # Task history
        st.markdown("---")
        st.subheader("📜 Task Execution History")
        
        df = monitor.get_task_history(hours=24)
        if not df.empty:
            # Summary stats
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_tasks = len(df)
                st.metric("Total Tasks (24h)", total_tasks)
            
            with col2:
                success_tasks = len(df[df['status'] == 'SUCCESS'])
                st.metric("Successful", success_tasks)
            
            with col3:
                failed_tasks = len(df[df['status'] == 'FAILURE'])
                st.metric("Failed", failed_tasks)
            
            # Task timeline
            if 'date_done' in df.columns:
                fig = px.histogram(
                    df, x='date_done', color='status',
                    title='Task Execution Timeline',
                    labels={'date_done': 'Time', 'count': 'Task Count'}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Recent tasks table
            st.dataframe(
                df[['task_id', 'status', 'date_done']].head(20),
                hide_index=True,
                use_container_width=True
            )
    
    with tab3:
        render_system_resources()
        
        # Process list
        st.markdown("---")
        st.subheader("🔍 Top Processes by CPU")
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                if info['cpu_percent'] > 0:
                    processes.append(info)
            except:
                pass
        
        if processes:
            df_procs = pd.DataFrame(processes)
            df_procs = df_procs.nlargest(10, 'cpu_percent')
            
            fig = px.bar(
                df_procs, x='cpu_percent', y='name',
                orientation='h',
                title='Top 10 Processes by CPU Usage',
                labels={'cpu_percent': 'CPU %', 'name': 'Process'}
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        render_event_logs()
    
    with tab5:
        render_manual_controls()
    
    with tab6:
        render_export_controls()
    
    # Auto-refresh
    if st.session_state.auto_refresh:
        time.sleep(st.session_state.refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main()