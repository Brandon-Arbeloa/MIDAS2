"""
MIDAS Advanced Dashboard Builder
Streamlit interface with drag-and-drop dashboard creation
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid

# Set page config for wide layout
st.set_page_config(
    page_title="MIDAS Dashboard Builder",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Local imports
from dashboard_system import (
    DashboardManager, DashboardConfig, ChartConfig,
    WindowsDisplayManager, get_user_dashboards_path
)
from dashboard_charts import (
    ChartRenderer, ChartDataConnector, InteractiveFilter,
    generate_sample_timeseries, generate_sample_categorical
)

# Custom CSS for drag-and-drop and responsive design
st.markdown("""
<style>
    /* Dashboard grid styling */
    .dashboard-grid {
        display: grid;
        gap: 10px;
        padding: 10px;
        background: #f0f2f6;
        border-radius: 10px;
        min-height: 600px;
    }
    
    /* Chart container styling */
    .chart-container {
        background: white;
        border-radius: 8px;
        padding: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        position: relative;
        overflow: hidden;
    }
    
    .chart-container:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    /* Drag handle */
    .drag-handle {
        position: absolute;
        top: 5px;
        right: 5px;
        cursor: move;
        color: #666;
        font-size: 20px;
    }
    
    /* Edit mode styling */
    .edit-mode .chart-container {
        border: 2px dashed #1976d2;
        cursor: move;
    }
    
    /* Filter container */
    .filter-container {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 20px;
    }
    
    /* Responsive adjustments */
    @media (max-width: 768px) {
        .dashboard-grid {
            grid-template-columns: 1fr !important;
        }
    }
    
    /* High-DPI support */
    @media (-webkit-min-device-pixel-ratio: 2), (min-resolution: 192dpi) {
        .chart-container {
            image-rendering: -webkit-crisp-edges;
            image-rendering: crisp-edges;
        }
    }
    
    /* Theme customization */
    .dark-theme {
        background-color: #1e1e1e;
        color: #ffffff;
    }
    
    .dark-theme .chart-container {
        background: #2d2d2d;
        color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'dashboard_manager' not in st.session_state:
    st.session_state.dashboard_manager = DashboardManager()

if 'current_dashboard' not in st.session_state:
    st.session_state.current_dashboard = None

if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False

if 'chart_renderer' not in st.session_state:
    st.session_state.chart_renderer = ChartRenderer()

if 'filter_manager' not in st.session_state:
    st.session_state.filter_manager = InteractiveFilter()

if 'refresh_interval' not in st.session_state:
    st.session_state.refresh_interval = None

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

if 'show_add_chart' not in st.session_state:
    st.session_state.show_add_chart = False

# Data source registration
if 'data_connector' not in st.session_state:
    connector = ChartDataConnector()
    # Register sample data sources
    connector.register_data_source('sample_timeseries', generate_sample_timeseries)
    connector.register_data_source('sample_categorical', generate_sample_categorical)
    st.session_state.data_connector = connector

def render_sidebar():
    """Render sidebar with dashboard management"""
    with st.sidebar:
        st.header("📊 Dashboard Builder")
        
        # Dashboard selection
        st.subheader("Dashboards")
        
        dashboards = st.session_state.dashboard_manager.storage.list_dashboards()
        
        if dashboards:
            dashboard_names = ["Create New..."] + [d['name'] for d in dashboards]
            selected_idx = st.selectbox(
                "Select Dashboard",
                range(len(dashboard_names)),
                format_func=lambda x: dashboard_names[x]
            )
            
            if selected_idx > 0:
                selected_dashboard = dashboards[selected_idx - 1]
                if st.button("📂 Load Dashboard"):
                    load_dashboard(selected_dashboard['id'])
        else:
            st.info("No dashboards created yet")
        
        st.divider()
        
        # Create new dashboard
        st.subheader("Create New Dashboard")
        with st.form("new_dashboard_form"):
            name = st.text_input("Dashboard Name")
            description = st.text_area("Description")
            
            templates = st.session_state.dashboard_manager.storage.list_templates()
            template_names = ["Blank"] + [t['name'] for t in templates]
            template_idx = st.selectbox(
                "Template",
                range(len(template_names)),
                format_func=lambda x: template_names[x]
            )
            
            if st.form_submit_button("➕ Create Dashboard"):
                if template_idx > 0 and template_idx <= len(templates):
                    template_id = templates[template_idx - 1]['id']
                else:
                    template_id = None
                create_dashboard(name, description, template_id)
        
        st.divider()
        
        # Edit mode toggle
        if st.session_state.current_dashboard:
            st.subheader("Dashboard Controls")
            
            st.session_state.edit_mode = st.checkbox(
                "Edit Mode",
                value=st.session_state.edit_mode
            )
            
            if st.session_state.edit_mode:
                st.info("🖱️ Drag charts to rearrange")
                
                # Add chart button
                if st.button("➕ Add Chart"):
                    st.session_state.show_add_chart = True
            
            # Theme selection
            themes = st.session_state.dashboard_manager.storage.list_themes()
            theme_names = [t['name'] for t in themes]
            current_theme_idx = 0
            
            if st.session_state.current_dashboard:
                for i, theme in enumerate(themes):
                    if theme['id'] == st.session_state.current_dashboard.theme:
                        current_theme_idx = i
                        break
            
            selected_theme_idx = st.selectbox(
                "Theme",
                range(len(theme_names)),
                format_func=lambda x: theme_names[x],
                index=current_theme_idx
            )
            
            if themes and selected_theme_idx != current_theme_idx:
                apply_theme(themes[selected_theme_idx]['id'])
            
            # Refresh settings
            st.subheader("Auto Refresh")
            
            refresh_enabled = st.checkbox("Enable Auto Refresh")
            
            if refresh_enabled:
                refresh_interval = st.slider(
                    "Refresh Interval (seconds)",
                    min_value=5,
                    max_value=300,
                    value=30,
                    step=5
                )
                st.session_state.refresh_interval = refresh_interval
            else:
                st.session_state.refresh_interval = None
            
            # Save/Export options
            st.divider()
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("💾 Save"):
                    save_dashboard()
            
            with col2:
                if st.button("📤 Export"):
                    export_dashboard()
            
            # Version history
            if st.button("📜 Version History"):
                show_version_history()
            
            # Share dashboard
            if st.button("🔗 Share"):
                share_dashboard()

def load_dashboard(dashboard_id: str):
    """Load dashboard configuration"""
    config = st.session_state.dashboard_manager.storage.load_dashboard(dashboard_id)
    if config:
        st.session_state.current_dashboard = config
        
        # Load theme
        theme_data = st.session_state.dashboard_manager.storage.load_theme(config.theme)
        if theme_data:
            st.session_state.chart_renderer.theme = theme_data
        
        # Initialize filters
        for filter_config in config.filters:
            st.session_state.filter_manager.register_filter(
                filter_config['id'],
                filter_config
            )
        
        st.success(f"Loaded dashboard: {config.name}")
        st.rerun()

def create_dashboard(name: str, description: str, template_id: Optional[str]):
    """Create new dashboard"""
    if not name:
        st.error("Dashboard name is required")
        return
    
    try:
        config = st.session_state.dashboard_manager.create_dashboard(
            name, description, template_id
        )
        
        st.session_state.current_dashboard = config
        st.success(f"Created dashboard: {name}")
        # Force a refresh to show the new dashboard
        time.sleep(0.5)  # Small delay to ensure success message is shown
        st.rerun()
    except Exception as e:
        st.error(f"Error creating dashboard: {str(e)}")
        import traceback
        st.error(traceback.format_exc())

def save_dashboard():
    """Save current dashboard"""
    if st.session_state.current_dashboard:
        success = st.session_state.dashboard_manager.storage.save_dashboard(
            st.session_state.current_dashboard
        )
        
        if success:
            st.success("Dashboard saved successfully")
        else:
            st.error("Failed to save dashboard")

def apply_theme(theme_id: str):
    """Apply theme to dashboard"""
    if st.session_state.current_dashboard:
        st.session_state.current_dashboard.theme = theme_id
        
        theme_data = st.session_state.dashboard_manager.storage.load_theme(theme_id)
        if theme_data:
            st.session_state.chart_renderer.theme = theme_data
        
        save_dashboard()
        st.rerun()

def render_dashboard_filters():
    """Render dashboard-level filters"""
    if not st.session_state.current_dashboard:
        return
    
    filters = st.session_state.current_dashboard.filters
    if not filters:
        return
    
    st.markdown("### 🔍 Filters")
    
    # Create columns for filters
    num_filters = len(filters)
    if num_filters > 0:
        cols = st.columns(min(num_filters, 4))
        
        for i, filter_config in enumerate(filters):
            col_idx = i % len(cols)
            
            with cols[col_idx]:
                render_filter(filter_config)

def render_filter(filter_config: Dict[str, Any]):
    """Render individual filter control"""
    filter_id = filter_config['id']
    filter_type = filter_config['type']
    label = filter_config.get('label', filter_id)
    
    if filter_type == 'select':
        options = filter_config.get('options', [])
        current_value = st.session_state.filter_manager.get_filter_value(filter_id)
        
        selected = st.selectbox(
            label,
            options,
            index=options.index(current_value) if current_value in options else 0,
            key=f"filter_{filter_id}"
        )
        
        st.session_state.filter_manager.update_filter_value(filter_id, selected)
    
    elif filter_type == 'multiselect':
        options = filter_config.get('options', [])
        current_value = st.session_state.filter_manager.get_filter_value(filter_id) or []
        
        selected = st.multiselect(
            label,
            options,
            default=current_value,
            key=f"filter_{filter_id}"
        )
        
        st.session_state.filter_manager.update_filter_value(filter_id, selected)
    
    elif filter_type == 'range':
        min_val = filter_config.get('min', 0)
        max_val = filter_config.get('max', 100)
        current_value = st.session_state.filter_manager.get_filter_value(filter_id) or [min_val, max_val]
        
        selected = st.slider(
            label,
            min_val,
            max_val,
            current_value,
            key=f"filter_{filter_id}"
        )
        
        st.session_state.filter_manager.update_filter_value(filter_id, selected)
    
    elif filter_type == 'date_range':
        current_value = st.session_state.filter_manager.get_filter_value(filter_id)
        if not current_value:
            current_value = [datetime.now() - timedelta(days=30), datetime.now()]
        
        col1, col2 = st.columns(2)
        
        with col1:
            start_date = st.date_input(
                f"{label} Start",
                value=current_value[0],
                key=f"filter_{filter_id}_start"
            )
        
        with col2:
            end_date = st.date_input(
                f"{label} End",
                value=current_value[1],
                key=f"filter_{filter_id}_end"
            )
        
        st.session_state.filter_manager.update_filter_value(
            filter_id, 
            [start_date, end_date]
        )

def render_dashboard_grid():
    """Render main dashboard grid"""
    if not st.session_state.current_dashboard:
        st.info("Select or create a dashboard to get started")
        return
    
    dashboard = st.session_state.current_dashboard
    
    # Dashboard header
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        st.title(dashboard.name)
        if dashboard.description:
            st.caption(dashboard.description)
    
    with col2:
        if st.session_state.refresh_interval:
            time_since_refresh = (datetime.now() - st.session_state.last_refresh).total_seconds()
            st.metric("Last Refresh", f"{int(time_since_refresh)}s ago")
    
    with col3:
        if st.button("🔄 Refresh Now"):
            st.session_state.last_refresh = datetime.now()
            st.rerun()
    
    # Render filters
    render_dashboard_filters()
    
    # Calculate grid layout
    layout = dashboard.layout
    num_columns = layout.get('columns', 12)
    row_height = layout.get('row_height', 80)
    
    # Group charts by row
    charts_by_row = {}
    for chart in dashboard.charts:
        row = chart.position['row']
        if row not in charts_by_row:
            charts_by_row[row] = []
        charts_by_row[row].append(chart)
    
    # Render charts row by row
    for row_num in sorted(charts_by_row.keys()):
        row_charts = sorted(charts_by_row[row_num], key=lambda c: c.position['col'])
        
        # Create columns for this row
        col_specs = []
        for chart in row_charts:
            col_specs.append(chart.position['width'])
        
        if col_specs:
            cols = st.columns(col_specs)
            
            for i, chart in enumerate(row_charts):
                with cols[i]:
                    render_chart_container(chart)

def render_chart_container(chart: ChartConfig):
    """Render individual chart container"""
    container_id = f"chart_{chart.id}"
    
    # Container with drag handle in edit mode
    if st.session_state.edit_mode:
        st.markdown(
            f"""<div class="chart-container edit-mode" id="{container_id}">
            <span class="drag-handle">⋮⋮</span>""",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""<div class="chart-container" id="{container_id}">""",
            unsafe_allow_html=True
        )
    
    # Chart header with controls
    col1, col2 = st.columns([4, 1])
    
    with col1:
        if st.session_state.edit_mode:
            # Editable title
            new_title = st.text_input(
                "Title",
                value=chart.title,
                key=f"title_{chart.id}"
            )
            if new_title != chart.title:
                update_chart_property(chart.id, 'title', new_title)
        else:
            st.subheader(chart.title)
    
    with col2:
        if st.session_state.edit_mode:
            col_a, col_b = st.columns(2)
            
            with col_a:
                if st.button("⚙️", key=f"config_{chart.id}"):
                    show_chart_config(chart.id)
            
            with col_b:
                if st.button("🗑️", key=f"delete_{chart.id}"):
                    delete_chart(chart.id)
    
    # Render chart
    try:
        # Get data with filters applied
        data = st.session_state.data_connector.get_data(chart.data_source)
        
        if not data.empty:
            data = st.session_state.filter_manager.apply_filters_to_data(data)
        
        # Apply chart-specific filters
        for filter_config in chart.filters:
            data = apply_chart_filter(data, filter_config)
        
        # Render chart
        fig = st.session_state.chart_renderer.render_chart(
            {
                'type': chart.type,
                'title': chart.title,
                'options': chart.options,
                'data_source': chart.data_source
            },
            data
        )
        
        # Display with appropriate height
        chart_height = chart.position['height'] * st.session_state.current_dashboard.layout['row_height']
        st.plotly_chart(fig, use_container_width=True, height=chart_height)
        
    except Exception as e:
        st.error(f"Error rendering chart: {str(e)}")
    
    st.markdown("</div>", unsafe_allow_html=True)

def apply_chart_filter(data: pd.DataFrame, filter_config: Dict[str, Any]) -> pd.DataFrame:
    """Apply chart-specific filter"""
    # Implementation similar to dashboard filters but scoped to chart
    return data

def update_chart_property(chart_id: str, property_name: str, value: Any):
    """Update chart property"""
    if st.session_state.current_dashboard:
        for chart in st.session_state.current_dashboard.charts:
            if chart.id == chart_id:
                setattr(chart, property_name, value)
                save_dashboard()
                break

def delete_chart(chart_id: str):
    """Delete chart from dashboard"""
    if st.session_state.current_dashboard:
        success = st.session_state.dashboard_manager.remove_chart(
            st.session_state.current_dashboard.id,
            chart_id
        )
        
        if success:
            st.session_state.current_dashboard = st.session_state.dashboard_manager.storage.load_dashboard(
                st.session_state.current_dashboard.id
            )
            st.rerun()

def show_add_chart_dialog():
    """Show dialog to add new chart"""
    with st.form("add_chart_form"):
        st.subheader("Add New Chart")
        
        # Chart type selection
        chart_types = [
            'line', 'bar', 'scatter', 'pie', 'heatmap', 
            'table', 'metric', 'gauge'
        ]
        
        chart_type = st.selectbox("Chart Type", chart_types)
        title = st.text_input("Chart Title")
        
        # Data source selection
        st.subheader("Data Source")
        
        source_type = st.selectbox(
            "Source Type",
            ['function', 'sql', 'api', 'static']
        )
        
        data_source = {'type': source_type}
        
        if source_type == 'function':
            functions = list(st.session_state.data_connector.data_sources.keys())
            selected_func = st.selectbox("Function", functions)
            data_source['function'] = selected_func
        
        elif source_type == 'sql':
            query = st.text_area("SQL Query")
            database = st.text_input("Database Name")
            data_source['query'] = query
            data_source['database'] = database
        
        # Position
        st.subheader("Position")
        
        col1, col2 = st.columns(2)
        
        with col1:
            row = st.number_input("Row", min_value=0, value=0)
            width = st.number_input("Width", min_value=1, max_value=12, value=6)
        
        with col2:
            col = st.number_input("Column", min_value=0, max_value=11, value=0)
            height = st.number_input("Height", min_value=1, max_value=10, value=3)
        
        position = {
            'row': row,
            'col': col,
            'width': width,
            'height': height
        }
        
        if st.form_submit_button("Add Chart"):
            if title and st.session_state.current_dashboard:
                chart = st.session_state.dashboard_manager.add_chart(
                    st.session_state.current_dashboard.id,
                    chart_type,
                    title,
                    position
                )
                
                if chart:
                    # Update data source
                    chart.data_source = data_source
                    save_dashboard()
                    
                    st.session_state.current_dashboard = st.session_state.dashboard_manager.storage.load_dashboard(
                        st.session_state.current_dashboard.id
                    )
                    st.success("Chart added successfully")
                    st.rerun()

def show_chart_config(chart_id: str):
    """Show chart configuration dialog"""
    # Find chart
    chart = None
    if st.session_state.current_dashboard:
        for c in st.session_state.current_dashboard.charts:
            if c.id == chart_id:
                chart = c
                break
    
    if not chart:
        return
    
    with st.expander(f"Configure: {chart.title}", expanded=True):
        # Chart-specific options based on type
        if chart.type == 'line':
            x_col = st.text_input(
                "X Column",
                value=chart.options.get('x_column', ''),
                key=f"x_col_{chart_id}"
            )
            
            y_cols = st.text_input(
                "Y Columns (comma-separated)",
                value=','.join(chart.options.get('y_columns', [])),
                key=f"y_cols_{chart_id}"
            )
            
            if st.button("Update", key=f"update_{chart_id}"):
                chart.options['x_column'] = x_col
                chart.options['y_columns'] = [c.strip() for c in y_cols.split(',')]
                save_dashboard()
                st.rerun()
        
        # Add more chart type configurations as needed

def export_dashboard():
    """Export dashboard configuration"""
    if st.session_state.current_dashboard:
        config_json = json.dumps(
            st.session_state.current_dashboard.__dict__,
            default=str,
            indent=2
        )
        
        st.download_button(
            label="📥 Download Dashboard Configuration",
            data=config_json,
            file_name=f"{st.session_state.current_dashboard.name}_export.json",
            mime="application/json"
        )

def share_dashboard():
    """Share dashboard dialog"""
    if st.session_state.current_dashboard:
        with st.form("share_form"):
            st.subheader("Share Dashboard")
            
            share_path = st.text_input(
                "Network Path",
                value=r"\\server\shared\dashboards\\" + st.session_state.current_dashboard.name + ".json"
            )
            
            expires_days = st.number_input(
                "Expires After (days)",
                min_value=0,
                value=30,
                help="0 = No expiration"
            )
            
            if st.form_submit_button("Share"):
                success = st.session_state.dashboard_manager.storage.share_dashboard(
                    st.session_state.current_dashboard.id,
                    share_path,
                    expires_days if expires_days > 0 else None
                )
                
                if success:
                    st.success(f"Dashboard shared to: {share_path}")
                else:
                    st.error("Failed to share dashboard")

def show_version_history():
    """Show version history dialog"""
    if st.session_state.current_dashboard:
        versions = st.session_state.dashboard_manager.storage.get_dashboard_versions(
            st.session_state.current_dashboard.id
        )
        
        if versions:
            with st.expander("Version History", expanded=True):
                for version in versions:
                    col1, col2, col3 = st.columns([1, 2, 1])
                    
                    with col1:
                        st.write(f"v{version['version']}")
                    
                    with col2:
                        st.write(f"{version['created_at']}")
                        st.caption(f"By: {version['author']}")
                        if version['change_description']:
                            st.caption(version['change_description'])
                    
                    with col3:
                        if st.button("Restore", key=f"restore_{version['version']}"):
                            success = st.session_state.dashboard_manager.storage.restore_dashboard_version(
                                st.session_state.current_dashboard.id,
                                version['version']
                            )
                            
                            if success:
                                st.success(f"Restored to version {version['version']}")
                                load_dashboard(st.session_state.current_dashboard.id)
                            else:
                                st.error("Failed to restore version")

def auto_refresh():
    """Handle auto-refresh logic"""
    if st.session_state.refresh_interval:
        time_since_refresh = (datetime.now() - st.session_state.last_refresh).total_seconds()
        
        if time_since_refresh >= st.session_state.refresh_interval:
            st.session_state.last_refresh = datetime.now()
            st.rerun()

def main():
    # Render sidebar
    render_sidebar()
    
    # Debug info (temporary)
    if 'current_dashboard' in st.session_state and st.session_state.current_dashboard:
        st.sidebar.success(f"Current Dashboard: {st.session_state.current_dashboard.name}")
    else:
        st.sidebar.info("No dashboard currently loaded")
    
    # Main content area
    if st.session_state.current_dashboard:
        # Show add chart dialog if requested
        if st.session_state.show_add_chart:
            show_add_chart_dialog()
            st.session_state.show_add_chart = False
        else:
            # Add edit mode class to body
            if st.session_state.edit_mode:
                st.markdown(
                    '<div class="edit-mode">',
                    unsafe_allow_html=True
                )
            
            # Render dashboard
            render_dashboard_grid()
            
            if st.session_state.edit_mode:
                st.markdown('</div>', unsafe_allow_html=True)
        
        # Auto-refresh
        auto_refresh()
    
    else:
        # Welcome screen
        st.markdown("""
        # 📊 Welcome to MIDAS Dashboard Builder
        
        Create beautiful, interactive dashboards with drag-and-drop functionality.
        
        ### Features:
        - 🎨 **Drag-and-Drop Layout** - Arrange charts with ease
        - 📊 **Multiple Chart Types** - Line, bar, scatter, pie, and more
        - 🎨 **Themes** - Light, dark, and corporate themes
        - 🔄 **Real-time Updates** - Auto-refresh with configurable intervals
        - 🔍 **Interactive Filters** - Filter data across all charts
        - 💾 **Version Control** - Track changes and restore versions
        - 🔗 **Sharing** - Share dashboards via network paths
        - 🖥️ **High-DPI Support** - Optimized for Windows displays
        
        ### Getting Started:
        1. Click **"New Dashboard"** in the sidebar
        2. Choose a template or start from scratch
        3. Add charts and configure data sources
        4. Arrange charts by enabling edit mode
        5. Save and share your dashboard
        
        """)
        
        # Show recent dashboards
        dashboards = st.session_state.dashboard_manager.storage.list_dashboards()
        if dashboards:
            st.subheader("Recent Dashboards")
            
            cols = st.columns(3)
            for i, dashboard in enumerate(dashboards[:6]):
                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="chart-container" style="cursor: pointer;">
                        <h4>{dashboard['name']}</h4>
                        <p>{dashboard['description']}</p>
                        <small>Updated: {dashboard['updated_at']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("Open", key=f"open_{dashboard['id']}"):
                        load_dashboard(dashboard['id'])

if __name__ == "__main__":
    main()