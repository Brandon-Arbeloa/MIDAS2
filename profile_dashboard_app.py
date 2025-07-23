"""
MIDAS Profile Dashboard Application
Complete user profile system with chart saving, sharing, and dashboard management
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import sys
import json
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import tempfile
import base64

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import our modules
from user_profile_system import (
    UserProfileDatabase,
    ChartPersistenceManager,
    WindowsRegistryManager,
    WindowsApplicationIntegration,
    NetworkChartSharing
)
from windows_auth_system import WindowsAuthenticationSystem
from visualization_chat_app import (
    initialize_visualization_session_state,
    display_visualization_result,
    process_chat_with_visualization
)
from data_visualization_engine import DataVisualizationEngine, PlotlyChartGenerator

class ProfileDashboardApp:
    """Main profile dashboard application"""
    
    def __init__(self):
        self.auth_system = WindowsAuthenticationSystem()
        self.profile_db = UserProfileDatabase()
        self.chart_manager = ChartPersistenceManager()
        self.registry_manager = WindowsRegistryManager()
        self.network_sharing = NetworkChartSharing()
        self.chart_generator = PlotlyChartGenerator()
        
        # Initialize session state
        self._init_session_state()
    
    def _init_session_state(self):
        """Initialize session state variables"""
        if "current_page" not in st.session_state:
            st.session_state.current_page = "dashboard"
        
        if "selected_charts" not in st.session_state:
            st.session_state.selected_charts = []
        
        if "dashboard_edit_mode" not in st.session_state:
            st.session_state.dashboard_edit_mode = False
        
        # Initialize visualization components
        initialize_visualization_session_state()
    
    def render_navigation(self):
        """Render main navigation"""
        st.sidebar.title("📊 MIDAS Profile Dashboard")
        
        user_info = st.session_state.get("user_info", {})
        if user_info:
            st.sidebar.success(f"Welcome, **{user_info['username']}**!")
        
        # Main navigation
        pages = {
            "dashboard": "🏠 Dashboard",
            "saved_charts": "💾 Saved Charts",
            "create_chart": "➕ Create Chart", 
            "shared_charts": "🤝 Shared Charts",
            "templates": "📋 Templates",
            "profile_settings": "⚙️ Settings"
        }
        
        for page_key, page_name in pages.items():
            if st.sidebar.button(page_name, key=f"nav_{page_key}"):
                st.session_state.current_page = page_key
                st.rerun()
        
        st.sidebar.markdown("---")
        
        # Quick stats
        user_id = user_info.get("id")
        if user_id:
            charts = self.profile_db.get_user_charts(user_id, include_public=False)
            shared_charts = self.profile_db.get_user_charts(user_id, include_public=True)
            
            st.sidebar.metric("My Charts", len(charts))
            st.sidebar.metric("Available Charts", len(shared_charts))
            
            public_charts = len([c for c in charts if c.get('is_public')])
            st.sidebar.metric("Public Charts", public_charts)
    
    def render_dashboard_page(self):
        """Render main dashboard page"""
        st.title("🏠 Personal Dashboard")
        
        user_info = st.session_state.get("user_info", {})
        user_id = user_info.get("id")
        
        if not user_id:
            st.error("Please log in to access your dashboard")
            return
        
        # Dashboard controls
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.subheader("Your Chart Dashboard")
        
        with col2:
            if st.button("📝 Edit Layout"):
                st.session_state.dashboard_edit_mode = not st.session_state.dashboard_edit_mode
                st.rerun()
        
        with col3:
            if st.button("💾 Save Layout"):
                self._save_current_dashboard_layout(user_id)
        
        # Load saved dashboards
        saved_dashboards = self.profile_db.get_user_dashboards(user_id)
        default_dashboard = next((d for d in saved_dashboards if d['is_default']), None)
        
        # Dashboard selection
        if saved_dashboards:
            dashboard_names = [d['name'] for d in saved_dashboards]
            selected_dashboard = st.selectbox(
                "Select Dashboard Layout",
                dashboard_names,
                index=dashboard_names.index(default_dashboard['name']) if default_dashboard else 0
            )
            
            current_dashboard = next(d for d in saved_dashboards if d['name'] == selected_dashboard)
            chart_ids = current_dashboard['chart_ids']
        else:
            # Default: show recent charts
            recent_charts = self.profile_db.get_user_charts(user_id, include_public=False)[:6]
            chart_ids = [c['id'] for c in recent_charts]
        
        # Display charts in grid
        if chart_ids:
            self._render_chart_grid(user_id, chart_ids)
        else:
            st.info("No charts to display. Create your first chart to get started!")
            if st.button("➕ Create Your First Chart"):
                st.session_state.current_page = "create_chart"
                st.rerun()
        
        # Recent activity
        st.subheader("📈 Recent Activity")
        recent_charts = self.profile_db.get_user_charts(user_id, include_public=False)[:5]
        
        if recent_charts:
            for chart in recent_charts:
                with st.expander(f"📊 {chart['title']}", expanded=False):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**Type**: {chart['chart_type'].title()}")
                        st.write(f"**Created**: {chart['created_at'][:19]}")
                        if chart['description']:
                            st.write(f"**Description**: {chart['description']}")
                    
                    with col2:
                        if st.button("👁️ View", key=f"view_{chart['id']}"):
                            self._show_chart_modal(chart)
                    
                    with col3:
                        if st.button("✏️ Edit", key=f"edit_{chart['id']}"):
                            st.session_state.editing_chart_id = chart['id']
                            st.session_state.current_page = "saved_charts"
                            st.rerun()
    
    def _render_chart_grid(self, user_id: int, chart_ids: List[str]):
        """Render charts in a responsive grid"""
        charts = []
        for chart_id in chart_ids:
            chart = self.profile_db.get_chart_by_id(chart_id, user_id)
            if chart:
                charts.append(chart)
        
        if not charts:
            st.info("No charts found in this dashboard layout")
            return
        
        # Create responsive grid
        cols_per_row = 2 if len(charts) > 1 else 1
        
        for i in range(0, len(charts), cols_per_row):
            cols = st.columns(cols_per_row)
            
            for j, col in enumerate(cols):
                if i + j < len(charts):
                    chart = charts[i + j]
                    with col:
                        self._render_chart_card(chart, user_id)
    
    def _render_chart_card(self, chart: Dict, user_id: int):
        """Render individual chart card"""
        with st.container():
            st.markdown(f"**📊 {chart['title']}**")
            
            # Load and display chart
            chart_fig = self.chart_manager.load_chart_figure(user_id, chart['id'])
            
            if chart_fig:
                # Create smaller version for dashboard
                chart_fig.update_layout(height=300, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(chart_fig, use_container_width=True, key=f"dashboard_chart_{chart['id']}")
            else:
                st.error("Chart could not be loaded")
            
            # Chart actions
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("👁️", help="View Full", key=f"dash_view_{chart['id']}"):
                    self._show_chart_modal(chart)
            
            with col2:
                if st.button("📤", help="Export", key=f"dash_export_{chart['id']}"):
                    self._show_export_options(chart, user_id)
            
            with col3:
                if st.button("🤝", help="Share", key=f"dash_share_{chart['id']}"):
                    self._show_share_options(chart, user_id)
    
    def render_saved_charts_page(self):
        """Render saved charts management page"""
        st.title("💾 Saved Charts")
        
        user_info = st.session_state.get("user_info", {})
        user_id = user_info.get("id")
        
        if not user_id:
            st.error("Please log in to view saved charts")
            return
        
        # Filters and search
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            search_term = st.text_input("🔍 Search charts", placeholder="Search by title or description...")
        
        with col2:
            chart_type_filter = st.selectbox(
                "Chart Type",
                ["All", "bar", "line", "scatter", "pie", "heatmap", "histogram", "box"]
            )
        
        with col3:
            sort_by = st.selectbox("Sort by", ["Recent", "Title", "Type", "Public"])
        
        # Get charts
        charts = self.profile_db.get_user_charts(user_id, include_public=False)
        
        # Apply filters
        if chart_type_filter != "All":
            charts = [c for c in charts if c['chart_type'] == chart_type_filter]
        
        if search_term:
            search_lower = search_term.lower()
            charts = [c for c in charts if 
                     search_lower in c['title'].lower() or 
                     (c['description'] and search_lower in c['description'].lower())]
        
        # Apply sorting
        if sort_by == "Title":
            charts.sort(key=lambda x: x['title'])
        elif sort_by == "Type":
            charts.sort(key=lambda x: x['chart_type'])
        elif sort_by == "Public":
            charts.sort(key=lambda x: x['is_public'], reverse=True)
        
        # Display charts
        if not charts:
            st.info("No charts found matching your criteria")
            return
        
        # Bulk actions
        st.subheader("Bulk Actions")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📦 Export Selected"):
                self._bulk_export_charts(user_id)
        
        with col2:
            if st.button("🗑️ Delete Selected"):
                self._bulk_delete_charts(user_id)
        
        with col3:
            if st.button("🌐 Make Public"):
                self._bulk_make_public(user_id)
        
        with col4:
            if st.button("🔒 Make Private"):
                self._bulk_make_private(user_id)
        
        # Chart list
        for chart in charts:
            with st.expander(f"📊 {chart['title']}", expanded=False):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    # Chart selection
                    chart_selected = st.checkbox(
                        "Select", 
                        value=chart['id'] in st.session_state.selected_charts,
                        key=f"select_{chart['id']}"
                    )
                    
                    if chart_selected and chart['id'] not in st.session_state.selected_charts:
                        st.session_state.selected_charts.append(chart['id'])
                    elif not chart_selected and chart['id'] in st.session_state.selected_charts:
                        st.session_state.selected_charts.remove(chart['id'])
                    
                    # Chart info
                    st.write(f"**Type**: {chart['chart_type'].title()}")
                    st.write(f"**Created**: {chart['created_at'][:19]}")
                    st.write(f"**Updated**: {chart['updated_at'][:19]}")
                    st.write(f"**Version**: {chart['version']}")
                    st.write(f"**Public**: {'Yes' if chart['is_public'] else 'No'}")
                    
                    if chart['description']:
                        st.write(f"**Description**: {chart['description']}")
                    
                    if chart['tags']:
                        st.write(f"**Tags**: {', '.join(chart['tags'])}")
                
                with col2:
                    # Preview chart
                    chart_fig = self.chart_manager.load_chart_figure(user_id, chart['id'])
                    if chart_fig:
                        chart_fig.update_layout(height=200, margin=dict(l=10, r=10, t=20, b=10))
                        st.plotly_chart(chart_fig, use_container_width=True, key=f"preview_{chart['id']}")
                
                with col3:
                    # Actions
                    if st.button("👁️ View", key=f"view_saved_{chart['id']}"):
                        self._show_chart_modal(chart)
                    
                    if st.button("✏️ Edit", key=f"edit_saved_{chart['id']}"):
                        self._show_edit_chart_modal(chart, user_id)
                    
                    if st.button("📤 Export", key=f"export_saved_{chart['id']}"):
                        self._show_export_options(chart, user_id)
                    
                    if st.button("🤝 Share", key=f"share_saved_{chart['id']}"):
                        self._show_share_options(chart, user_id)
                    
                    if st.button("📋 Clone", key=f"clone_saved_{chart['id']}"):
                        self._clone_chart(chart, user_id)
                    
                    if st.button("🗑️ Delete", key=f"delete_saved_{chart['id']}"):
                        self._delete_chart(chart['id'], user_id)
                
                # Version history
                if st.button("📚 Version History", key=f"history_{chart['id']}"):
                    self._show_version_history(chart['id'], user_id)
    
    def render_create_chart_page(self):
        """Render chart creation page"""
        st.title("➕ Create New Chart")
        
        user_info = st.session_state.get("user_info", {})
        user_id = user_info.get("id")
        
        if not user_id:
            st.error("Please log in to create charts")
            return
        
        # Chart creation methods
        tab1, tab2, tab3 = st.tabs(["🎨 From Scratch", "📊 From Data", "📋 From Template"])
        
        with tab1:
            self._render_manual_chart_creation(user_id)
        
        with tab2:
            self._render_data_driven_chart_creation(user_id)
        
        with tab3:
            self._render_template_based_creation(user_id)
    
    def _render_manual_chart_creation(self, user_id: int):
        """Render manual chart creation interface"""
        st.subheader("Create Chart Manually")
        
        with st.form("manual_chart_form"):
            # Basic info
            title = st.text_input("Chart Title*", placeholder="Enter chart title")
            description = st.text_area("Description", placeholder="Describe your chart")
            
            # Chart type selection
            chart_type = st.selectbox(
                "Chart Type",
                ["bar", "line", "scatter", "pie", "heatmap", "histogram", "box"]
            )
            
            # Chart configuration
            st.subheader("Chart Configuration")
            
            if chart_type == "bar":
                x_label = st.text_input("X-axis Label", value="Category")
                y_label = st.text_input("Y-axis Label", value="Value")
                
                # Sample data input
                st.subheader("Sample Data")
                sample_data = st.text_area(
                    "Data (CSV format)",
                    value="Category,Value\nA,10\nB,15\nC,8\nD,12",
                    help="Enter data in CSV format"
                )
            
            elif chart_type == "line":
                x_label = st.text_input("X-axis Label", value="Time")
                y_label = st.text_input("Y-axis Label", value="Value")
                
                sample_data = st.text_area(
                    "Data (CSV format)",
                    value="Time,Value\n2023-01,100\n2023-02,120\n2023-03,110\n2023-04,130",
                    help="Enter data in CSV format"
                )
            
            # Additional settings
            col1, col2 = st.columns(2)
            with col1:
                is_public = st.checkbox("Make Public", help="Allow other users to see this chart")
                is_template = st.checkbox("Save as Template", help="Save this chart as a reusable template")
            
            with col2:
                tags_input = st.text_input("Tags (comma-separated)", placeholder="tag1, tag2, tag3")
                tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()]
            
            # Submit
            if st.form_submit_button("🎨 Create Chart"):
                if not title:
                    st.error("Chart title is required")
                else:
                    self._create_manual_chart(
                        user_id, title, description, chart_type, 
                        sample_data, tags, is_public, is_template
                    )
    
    def _render_data_driven_chart_creation(self, user_id: int):
        """Render data-driven chart creation"""
        st.subheader("Create Chart from Data")
        
        # Use existing visualization engine
        if hasattr(st.session_state, 'visualization_engine'):
            st.info("Use the chat interface to request a visualization, then save it here.")
            
            # Show recent visualization requests
            if hasattr(st.session_state, 'visualization_history') and st.session_state.visualization_history:
                st.subheader("Recent Visualizations")
                
                for viz in reversed(st.session_state.visualization_history[-3:]):
                    with st.expander(f"📊 {viz['request'][:50]}...", expanded=False):
                        st.write(f"**Request**: {viz['request']}")
                        st.write(f"**Chart Type**: {viz['chart_type']}")
                        st.write(f"**Created**: {viz['timestamp']}")
                        
                        if st.button("💾 Save This Chart", key=f"save_viz_{hash(viz['request'])}"):
                            # This would save the visualization result
                            st.success("Chart saved! (Implementation would save the actual chart)")
        else:
            st.info("Visualization engine not available. Please use the main chat interface first.")
    
    def _render_template_based_creation(self, user_id: int):
        """Render template-based chart creation"""
        st.subheader("Create Chart from Template")
        
        # Get available templates
        template_charts = self.profile_db.get_user_charts(user_id, include_public=True)
        templates = [c for c in template_charts if c.get('is_template')]
        
        if not templates:
            st.info("No templates available. Create a chart and mark it as a template to see it here.")
            return
        
        selected_template = st.selectbox(
            "Select Template",
            templates,
            format_func=lambda x: f"{x['title']} ({x['chart_type']})"
        )
        
        if selected_template:
            # Show template preview
            chart_fig = self.chart_manager.load_chart_figure(
                selected_template['user_id'], selected_template['id']
            )
            
            if chart_fig:
                st.subheader("Template Preview")
                st.plotly_chart(chart_fig, use_container_width=True)
            
            # Customization form
            with st.form("template_chart_form"):
                new_title = st.text_input("New Chart Title*", value=f"Copy of {selected_template['title']}")
                new_description = st.text_area("Description", value=selected_template.get('description', ''))
                
                # Allow basic customization
                new_colors = st.color_picker("Primary Color", value="#1f77b4")
                
                tags_input = st.text_input("Tags (comma-separated)")
                tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()]
                
                is_public = st.checkbox("Make Public")
                
                if st.form_submit_button("📋 Create from Template"):
                    if not new_title:
                        st.error("Chart title is required")
                    else:
                        self._create_from_template(
                            user_id, selected_template, new_title, 
                            new_description, tags, is_public, new_colors
                        )
    
    def render_shared_charts_page(self):
        """Render shared charts page"""
        st.title("🤝 Shared Charts")
        
        user_info = st.session_state.get("user_info", {})
        user_id = user_info.get("id")
        
        if not user_id:
            st.error("Please log in to view shared charts")
            return
        
        tab1, tab2, tab3 = st.tabs(["🌐 Public Charts", "📤 My Shares", "🌐 Network Shares"])
        
        with tab1:
            self._render_public_charts(user_id)
        
        with tab2:
            self._render_my_shares(user_id)
        
        with tab3:
            self._render_network_shares()
    
    def _render_public_charts(self, user_id: int):
        """Render public charts from all users"""
        all_charts = self.profile_db.get_user_charts(user_id, include_public=True)
        public_charts = [c for c in all_charts if c.get('is_public') and c['user_id'] != user_id]
        
        if not public_charts:
            st.info("No public charts available from other users")
            return
        
        for chart in public_charts:
            with st.expander(f"📊 {chart['title']} (by User {chart['user_id']})", expanded=False):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Type**: {chart['chart_type'].title()}")
                    if chart['description']:
                        st.write(f"**Description**: {chart['description']}")
                    st.write(f"**Created**: {chart['created_at'][:19]}")
                    if chart['tags']:
                        st.write(f"**Tags**: {', '.join(chart['tags'])}")
                
                with col2:
                    if st.button("👁️ View", key=f"view_public_{chart['id']}"):
                        self._show_chart_modal(chart)
                    
                    if st.button("📋 Clone", key=f"clone_public_{chart['id']}"):
                        self._clone_chart(chart, user_id)
                    
                    if st.button("📤 Export", key=f"export_public_{chart['id']}"):
                        self._show_export_options(chart, user_id)
    
    def _render_my_shares(self, user_id: int):
        """Render charts shared by current user"""
        st.subheader("Charts I've Shared")
        my_charts = self.profile_db.get_user_charts(user_id, include_public=False)
        shared_charts = [c for c in my_charts if c.get('is_public')]
        
        if not shared_charts:
            st.info("You haven't shared any charts publicly yet")
            return
        
        for chart in shared_charts:
            with st.expander(f"📊 {chart['title']}", expanded=False):
                st.write(f"**Type**: {chart['chart_type'].title()}")
                st.write(f"**Shared**: {chart['updated_at'][:19]}")
                
                if st.button("🔒 Make Private", key=f"private_{chart['id']}"):
                    self._toggle_chart_privacy(chart['id'], user_id, False)
    
    def _render_network_shares(self):
        """Render network shared charts"""
        st.subheader("Network Shared Charts")
        
        if not self.network_sharing.network_available:
            st.warning("Windows network sharing not available")
            return
        
        network_charts = self.network_sharing.get_network_shared_charts()
        
        if not network_charts:
            st.info("No charts shared on the network")
            return
        
        for chart_info in network_charts:
            with st.expander(f"📊 {chart_info['chart_data']['title']}", expanded=False):
                st.write(f"**Shared by**: User {chart_info['user_id']}")
                st.write(f"**Shared at**: {chart_info['shared_at'][:19]}")
                st.write(f"**Network Path**: {chart_info['network_path']}")
                
                if st.button("📂 Open Network Location", key=f"network_{chart_info['chart_id']}"):
                    WindowsApplicationIntegration.open_with_default_app(
                        Path(chart_info['network_path'])
                    )
    
    def render_profile_settings_page(self):
        """Render profile settings page"""
        st.title("⚙️ Profile Settings")
        
        user_info = st.session_state.get("user_info", {})
        user_id = user_info.get("id")
        
        if not user_id:
            st.error("Please log in to access settings")
            return
        
        tab1, tab2, tab3, tab4 = st.tabs(["👤 Profile", "🎨 Preferences", "📁 Data Management", "🔧 Advanced"])
        
        with tab1:
            self._render_profile_settings(user_id)
        
        with tab2:
            self._render_preference_settings(user_id)
        
        with tab3:
            self._render_data_management(user_id)
        
        with tab4:
            self._render_advanced_settings(user_id)
    
    def _render_profile_settings(self, user_id: int):
        """Render profile settings"""
        st.subheader("Profile Information")
        
        user_info = st.session_state.get("user_info", {})
        
        with st.form("profile_form"):
            username = st.text_input("Username", value=user_info.get('username', ''), disabled=True)
            email = st.text_input("Email", value=user_info.get('email', ''))
            
            # User statistics
            charts = self.profile_db.get_user_charts(user_id, include_public=False)
            st.metric("Total Charts", len(charts))
            
            public_charts = len([c for c in charts if c.get('is_public')])
            st.metric("Public Charts", public_charts)
            
            if st.form_submit_button("💾 Update Profile"):
                st.success("Profile updated successfully!")
    
    def _render_preference_settings(self, user_id: int):
        """Render user preferences"""
        st.subheader("Chart Preferences")
        
        # Load current preferences from registry
        current_prefs = self.registry_manager.load_user_settings(user_id)
        
        with st.form("preferences_form"):
            # Default chart style
            default_chart_style = st.selectbox(
                "Default Chart Style",
                ["professional", "vibrant", "pastel", "default"],
                index=["professional", "vibrant", "pastel", "default"].index(
                    current_prefs.get("default_chart_style", "professional")
                )
            )
            
            # Default export format
            default_export_format = st.selectbox(
                "Default Export Format",
                ["png", "pdf", "html", "svg"],
                index=["png", "pdf", "html", "svg"].index(
                    current_prefs.get("default_export_format", "png")
                )
            )
            
            # Auto-save settings
            auto_save_enabled = st.checkbox(
                "Auto-save charts",
                value=current_prefs.get("auto_save_enabled", True)
            )
            
            # Privacy settings
            default_privacy = st.selectbox(
                "Default Chart Privacy",
                ["private", "public"],
                index=["private", "public"].index(
                    current_prefs.get("default_privacy", "private")
                )
            )
            
            if st.form_submit_button("💾 Save Preferences"):
                new_prefs = {
                    "default_chart_style": default_chart_style,
                    "default_export_format": default_export_format,
                    "auto_save_enabled": auto_save_enabled,
                    "default_privacy": default_privacy
                }
                
                self.registry_manager.save_user_settings(user_id, new_prefs)
                st.success("Preferences saved to Windows Registry!")
    
    def _render_data_management(self, user_id: int):
        """Render data management options"""
        st.subheader("Data Management")
        
        # Storage information
        user_chart_dir = self.chart_manager.get_user_chart_directory(user_id)
        
        if user_chart_dir.exists():
            # Calculate directory size
            total_size = sum(f.stat().st_size for f in user_chart_dir.rglob('*') if f.is_file())
            st.metric("Storage Used", f"{total_size / (1024*1024):.1f} MB")
            
            st.write(f"**Chart Directory**: `{user_chart_dir}`")
        
        # Data export/import
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📦 Export All Charts"):
                self._export_all_user_data(user_id)
        
        with col2:
            if st.button("🗑️ Clear All Data"):
                self._clear_all_user_data(user_id)
        
        # Backup options
        st.subheader("Backup Options")
        
        backup_location = st.text_input(
            "Backup Location",
            value=str(Path.home() / "Documents" / "MIDAS_Backup"),
            help="Choose where to save backups"
        )
        
        if st.button("💾 Create Backup"):
            self._create_user_backup(user_id, backup_location)
    
    def _render_advanced_settings(self, user_id: int):
        """Render advanced settings"""
        st.subheader("Advanced Settings")
        
        # Network sharing settings
        if self.network_sharing.network_available:
            st.subheader("Network Sharing")
            
            network_enabled = st.checkbox("Enable Network Sharing", value=False)
            
            if network_enabled:
                share_path = st.text_input(
                    "Network Share Path",
                    value=r"C:\MIDAS_NetworkShare",
                    help="Path for network share (requires admin privileges)"
                )
                
                if st.button("🌐 Setup Network Share"):
                    if self.network_sharing.setup_network_share(Path(share_path)):
                        st.success("Network share created successfully!")
                    else:
                        st.error("Failed to create network share. Admin privileges required.")
        
        # Database maintenance
        st.subheader("Database Maintenance")
        
        if st.button("🔧 Optimize Database"):
            self._optimize_database()
        
        if st.button("📊 Database Statistics"):
            self._show_database_stats()
    
    # Helper methods for various operations
    def _show_chart_modal(self, chart: Dict):
        """Show chart in modal dialog"""
        with st.expander(f"📊 {chart['title']}", expanded=True):
            # Load full chart
            chart_fig = self.chart_manager.load_chart_figure(chart['user_id'], chart['id'])
            
            if chart_fig:
                st.plotly_chart(chart_fig, use_container_width=True, key=f"modal_{chart['id']}")
            
            # Chart metadata
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Type**: {chart['chart_type'].title()}")
                st.write(f"**Created**: {chart['created_at'][:19]}")
                st.write(f"**Version**: {chart['version']}")
            
            with col2:
                st.write(f"**Public**: {'Yes' if chart['is_public'] else 'No'}")
                st.write(f"**Template**: {'Yes' if chart['is_template'] else 'No'}")
                if chart['tags']:
                    st.write(f"**Tags**: {', '.join(chart['tags'])}")
    
    def _create_manual_chart(self, user_id: int, title: str, description: str, 
                           chart_type: str, sample_data: str, tags: List[str],
                           is_public: bool, is_template: bool):
        """Create chart manually"""
        try:
            # Parse sample data
            import io
            df = pd.read_csv(io.StringIO(sample_data))
            
            # Create chart using the generator
            chart_config = {
                'type': chart_type,
                'title': title,
                'x': df.columns[0],
                'y': df.columns[1] if len(df.columns) > 1 else 'count'
            }
            
            chart_fig = self.chart_generator.generate_chart(df, chart_config, {})
            
            # Save chart
            chart_id = self.profile_db.save_chart(
                user_id, title, chart_type, chart_config,
                {'dataframe_info': df.to_dict()}, description, tags, is_public, is_template
            )
            
            # Save chart files
            metadata = {
                'title': title,
                'description': description,
                'chart_type': chart_type,
                'created_at': datetime.now().isoformat()
            }
            
            file_paths = self.chart_manager.save_chart_files(user_id, chart_id, chart_fig, metadata)
            
            st.success(f"Chart '{title}' created successfully!")
            st.balloons()
            
        except Exception as e:
            st.error(f"Failed to create chart: {str(e)}")
    
    def _export_all_user_data(self, user_id: int):
        """Export all user data"""
        try:
            export_path = Path(tempfile.gettempdir()) / f"MIDAS_Export_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            
            charts = self.profile_db.get_user_charts(user_id, include_public=False)
            chart_ids = [c['id'] for c in charts]
            
            if self.chart_manager.create_chart_package(user_id, chart_ids, export_path):
                st.success(f"Data exported to: {export_path}")
                
                # Provide download
                with open(export_path, 'rb') as f:
                    st.download_button(
                        "📥 Download Export",
                        f.read(),
                        file_name=export_path.name,
                        mime="application/zip"
                    )
            else:
                st.error("Failed to create export package")
                
        except Exception as e:
            st.error(f"Export failed: {str(e)}")
    
    def run(self):
        """Run the profile dashboard application"""
        st.set_page_config(
            page_title="MIDAS Profile Dashboard",
            page_icon="📊",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Check authentication
        if not st.session_state.get("authentication_status"):
            st.error("Please log in to access the profile dashboard")
            return
        
        # Render navigation
        self.render_navigation()
        
        # Render current page
        current_page = st.session_state.current_page
        
        if current_page == "dashboard":
            self.render_dashboard_page()
        elif current_page == "saved_charts":
            self.render_saved_charts_page()
        elif current_page == "create_chart":
            self.render_create_chart_page()
        elif current_page == "shared_charts":
            self.render_shared_charts_page()
        elif current_page == "profile_settings":
            self.render_profile_settings_page()
        else:
            st.error("Page not found")

def main():
    """Main function"""
    app = ProfileDashboardApp()
    app.run()

if __name__ == "__main__":
    main()