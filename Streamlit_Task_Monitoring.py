"""
MIDAS Task Monitoring Dashboard
Real-time monitoring of background tasks and system health
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import time
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from celery_config import app
from celery.result import AsyncResult
from background_tasks.monitoring_tasks import (
    system_health_check, check_task_queue, generate_task_report
)

# Page configuration
st.set_page_config(
    page_title="MIDAS Task Monitoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .status-ok { color: #28a745; }
    .status-warning { color: #ffc107; }
    .status-error { color: #dc3545; }
    .task-running { background-color: #007bff; color: white; padding: 5px 10px; border-radius: 5px; }
    .task-success { background-color: #28a745; color: white; padding: 5px 10px; border-radius: 5px; }
    .task-failed { background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

def get_celery_stats():
    """Get current Celery statistics"""
    stats = {
        'workers': 0,
        'active_tasks': 0,
        'reserved_tasks': 0,
        'worker_details': {}
    }
    
    try:
        inspector = app.control.inspect()
        
        # Active workers
        active_workers = inspector.active()
        if active_workers:
            stats['workers'] = len(active_workers)
            for worker, tasks in active_workers.items():
                stats['active_tasks'] += len(tasks)
                stats['worker_details'][worker] = {
                    'active': len(tasks),
                    'tasks': tasks
                }
        
        # Reserved tasks
        reserved = inspector.reserved()
        if reserved:
            for worker, tasks in reserved.items():
                stats['reserved_tasks'] += len(tasks)
                if worker in stats['worker_details']:
                    stats['worker_details'][worker]['reserved'] = len(tasks)
        
        # Worker stats
        worker_stats = inspector.stats()
        if worker_stats:
            for worker, info in worker_stats.items():
                if worker in stats['worker_details']:
                    stats['worker_details'][worker]['stats'] = info
    
    except Exception as e:
        st.error(f"Failed to connect to Celery: {e}")
    
    return stats

def get_health_status():
    """Get latest health status"""
    health_file = Path(__file__).parent / 'background_tasks' / 'data' / 'health_status.json'
    
    if health_file.exists():
        try:
            with open(health_file, 'r') as f:
                data = json.load(f)
                return data.get('latest', {})
        except Exception:
            pass
    
    return {}

def get_task_report():
    """Get latest task report"""
    report_file = Path(__file__).parent / 'background_tasks' / 'data' / 'latest_task_report.json'
    
    if report_file.exists():
        try:
            with open(report_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    
    return {}

def render_system_health(health_data):
    """Render system health metrics"""
    st.subheader("System Health")
    
    if not health_data:
        st.warning("No health data available. Run a health check first.")
        if st.button("Run Health Check"):
            with st.spinner("Running health check..."):
                result = system_health_check.delay()
                health_data = result.get(timeout=10)
        return
    
    # Overall status
    status = health_data.get('status', 'unknown')
    status_color = {
        'healthy': 'status-ok',
        'degraded': 'status-warning',
        'unhealthy': 'status-error',
        'error': 'status-error'
    }.get(status, '')
    
    st.markdown(f"<h3>Overall Status: <span class='{status_color}'>{status.upper()}</span></h3>", 
                unsafe_allow_html=True)
    
    # Metrics columns
    col1, col2, col3, col4 = st.columns(4)
    
    checks = health_data.get('checks', {})
    
    # CPU
    with col1:
        cpu_data = checks.get('cpu', {})
        st.metric(
            "CPU Usage",
            f"{cpu_data.get('usage_percent', 0)}%",
            delta=None,
            delta_color="inverse"
        )
    
    # Memory
    with col2:
        memory_data = checks.get('memory', {})
        st.metric(
            "Memory Usage",
            f"{memory_data.get('used_percent', 0)}%",
            f"{memory_data.get('available_gb', 0)} GB free"
        )
    
    # Redis
    with col3:
        redis_data = checks.get('redis', {})
        redis_status = "Connected" if redis_data.get('connected') else "Disconnected"
        st.metric(
            "Redis Status",
            redis_status,
            f"{redis_data.get('connected_clients', 0)} clients"
        )
    
    # Celery
    with col4:
        celery_data = checks.get('celery', {})
        st.metric(
            "Celery Workers",
            celery_data.get('worker_count', 0),
            f"{celery_data.get('active_tasks', 0)} active tasks"
        )
    
    # Warnings and Errors
    if health_data.get('warnings'):
        st.warning("**Warnings:**")
        for warning in health_data['warnings']:
            st.write(f"⚠️ {warning}")
    
    if health_data.get('errors'):
        st.error("**Errors:**")
        for error in health_data['errors']:
            st.write(f"❌ {error}")

def render_task_queue(stats):
    """Render task queue information"""
    st.subheader("Task Queue Status")
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Active Workers", stats['workers'])
    
    with col2:
        st.metric("Active Tasks", stats['active_tasks'])
    
    with col3:
        st.metric("Reserved Tasks", stats['reserved_tasks'])
    
    # Worker details
    if stats['worker_details']:
        st.subheader("Worker Details")
        
        for worker, details in stats['worker_details'].items():
            with st.expander(f"Worker: {worker}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Active Tasks:** {details.get('active', 0)}")
                    st.write(f"**Reserved Tasks:** {details.get('reserved', 0)}")
                
                # Active task list
                if details.get('tasks'):
                    st.write("**Running Tasks:**")
                    for task in details['tasks'][:5]:  # Show first 5
                        task_name = task.get('name', 'Unknown')
                        task_id = task.get('id', '')[:8]
                        st.write(f"- {task_name} ({task_id}...)")

def render_task_history():
    """Render task execution history"""
    st.subheader("Task Execution History")
    
    report = get_task_report()
    if not report:
        st.info("No task history available. Generate a report first.")
        if st.button("Generate Report"):
            with st.spinner("Generating report..."):
                result = generate_task_report.delay(period_hours=24)
                report = result.get(timeout=30)
        return
    
    # Summary
    summary = report.get('summary', {})
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Tasks", summary.get('total_tasks', 0))
    
    with col2:
        st.metric("Successful", summary.get('successful', 0))
    
    with col3:
        st.metric("Failed", summary.get('failed', 0))
    
    with col4:
        success_rate = report.get('performance_metrics', {}).get('success_rate', 0)
        st.metric("Success Rate", f"{success_rate}%")
    
    # Task statistics chart
    task_stats = report.get('task_stats', {})
    if task_stats:
        # Create DataFrame for plotting
        df = pd.DataFrame([
            {'Task': k, 'Count': v['count']} 
            for k, v in task_stats.items()
        ])
        
        if not df.empty:
            fig = px.bar(
                df.head(10), 
                x='Count', 
                y='Task',
                orientation='h',
                title='Top 10 Tasks by Execution Count'
            )
            st.plotly_chart(fig, use_container_width=True)

def render_live_monitoring():
    """Render live monitoring view"""
    st.subheader("Live Task Monitoring")
    
    # Create placeholder for live updates
    placeholder = st.empty()
    
    # Auto-refresh toggle
    col1, col2 = st.columns([1, 4])
    with col1:
        auto_refresh = st.checkbox("Auto-refresh", value=True)
    with col2:
        refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 10)
    
    if auto_refresh:
        # Continuous update loop
        while auto_refresh:
            with placeholder.container():
                stats = get_celery_stats()
                
                # Current time
                st.write(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Active tasks
                if stats['active_tasks'] > 0:
                    st.write("**Currently Running Tasks:**")
                    
                    for worker, details in stats['worker_details'].items():
                        if details.get('tasks'):
                            for task in details['tasks']:
                                col1, col2, col3 = st.columns([3, 2, 1])
                                
                                with col1:
                                    st.write(f"📋 {task.get('name', 'Unknown')}")
                                
                                with col2:
                                    task_id = task.get('id', '')[:12]
                                    st.write(f"ID: {task_id}...")
                                
                                with col3:
                                    runtime = 0
                                    if task.get('time_start'):
                                        runtime = int(time.time() - task['time_start'])
                                    st.write(f"⏱️ {runtime}s")
                else:
                    st.info("No tasks currently running")
            
            time.sleep(refresh_interval)

def main():
    st.title("🚀 MIDAS Task Monitoring Dashboard")
    st.markdown("Real-time monitoring of background tasks and system health")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select View",
        ["Overview", "Task Queue", "Task History", "Live Monitoring", "System Health"]
    )
    
    # Sidebar actions
    st.sidebar.markdown("---")
    st.sidebar.subheader("Quick Actions")
    
    if st.sidebar.button("🔄 Refresh Data"):
        st.rerun()
    
    if st.sidebar.button("📊 Generate Report"):
        with st.spinner("Generating report..."):
            result = generate_task_report.delay(period_hours=24)
            st.sidebar.success("Report generation started!")
    
    if st.sidebar.button("❤️ Run Health Check"):
        with st.spinner("Running health check..."):
            result = system_health_check.delay()
            st.sidebar.success("Health check started!")
    
    # Main content
    if page == "Overview":
        # Combined overview
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # System health summary
            health_data = get_health_status()
            render_system_health(health_data)
        
        with col2:
            # Quick stats
            stats = get_celery_stats()
            st.subheader("Quick Stats")
            st.metric("Active Workers", stats['workers'])
            st.metric("Running Tasks", stats['active_tasks'])
            
            # Recent report summary
            report = get_task_report()
            if report:
                summary = report.get('summary', {})
                st.metric("Tasks (24h)", summary.get('total_tasks', 0))
                
                success_rate = report.get('performance_metrics', {}).get('success_rate', 0)
                st.metric("Success Rate", f"{success_rate}%")
    
    elif page == "Task Queue":
        stats = get_celery_stats()
        render_task_queue(stats)
    
    elif page == "Task History":
        render_task_history()
    
    elif page == "Live Monitoring":
        render_live_monitoring()
    
    elif page == "System Health":
        health_data = get_health_status()
        render_system_health(health_data)
        
        # Historical health data
        st.subheader("Health History")
        health_file = Path(__file__).parent / 'background_tasks' / 'data' / 'health_status.json'
        
        if health_file.exists():
            try:
                with open(health_file, 'r') as f:
                    data = json.load(f)
                    history = data.get('history', [])
                
                if history:
                    # CPU usage over time
                    cpu_data = []
                    memory_data = []
                    timestamps = []
                    
                    for entry in history[-20:]:  # Last 20 entries
                        checks = entry.get('checks', {})
                        cpu = checks.get('cpu', {})
                        memory = checks.get('memory', {})
                        
                        if cpu.get('usage_percent') is not None:
                            cpu_data.append(cpu['usage_percent'])
                            memory_data.append(memory.get('used_percent', 0))
                            timestamps.append(entry.get('timestamp', ''))
                    
                    if cpu_data:
                        # Create line chart
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=timestamps,
                            y=cpu_data,
                            mode='lines+markers',
                            name='CPU %',
                            line=dict(color='blue')
                        ))
                        fig.add_trace(go.Scatter(
                            x=timestamps,
                            y=memory_data,
                            mode='lines+markers',
                            name='Memory %',
                            line=dict(color='red')
                        ))
                        
                        fig.update_layout(
                            title="System Resource Usage Over Time",
                            xaxis_title="Time",
                            yaxis_title="Usage %",
                            height=400
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
            
            except Exception as e:
                st.error(f"Failed to load health history: {e}")

if __name__ == "__main__":
    main()