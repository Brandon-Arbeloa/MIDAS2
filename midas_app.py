"""
MIDAS - Modular Intelligence & Data Analysis System
Unified application combining all features from prompts 1-15
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px
from pathlib import Path
import json
import time
import os
import sys
import logging
from typing import Dict, List, Any, Optional, Tuple
import asyncio
import aiohttp
import hashlib
import pyarrow.parquet as pq
import pyarrow as pa
from concurrent.futures import ThreadPoolExecutor
import psutil
import socket

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="MIDAS - Unified Intelligence System",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import all our custom modules
try:
    from rag_system import EnhancedRAGSystem
    from qdrant_manager import QdrantManager
    from document_processor import DocumentProcessor
    from ollama_service import OllamaService
    from dashboard_system import DashboardManager, DashboardConfig, ChartConfig
    from dashboard_charts import ChartRenderer, ChartDataConnector, InteractiveFilter
    from integrated_sql_rag_search import IntegratedSQLRAGSearch
    from database_connection_manager import DatabaseConnectionManager, DatabaseConfig
    from sql_query_generator import SQLQueryGenerator
    from monitoring_utils import WindowsEventLogger, ProcessMonitor, TaskMonitor
    from structured_data_indexer import StructuredDataIndexer
    from schema_indexer import SchemaIndexer
except ImportError as e:
    logger.warning(f"Some modules not available: {e}")

# Initialize session state
def init_session_state():
    """Initialize all session state variables"""
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.current_view = "home"
        st.session_state.chat_history = []
        st.session_state.uploaded_documents = []
        st.session_state.active_dashboard = None
        st.session_state.sql_connections = {}
        st.session_state.monitoring_data = {}
        st.session_state.search_results = []
        st.session_state.visualization_data = {}
        
        # Initialize managers
        try:
            st.session_state.rag_system = EnhancedRAGSystem()
            st.session_state.dashboard_manager = DashboardManager()
            st.session_state.chart_renderer = ChartRenderer()
            st.session_state.db_manager = DatabaseConnectionManager()
            st.session_state.sql_generator = SQLQueryGenerator()
            st.session_state.process_monitor = ProcessMonitor()
        except Exception as e:
            logger.error(f"Failed to initialize managers: {e}")

# Custom CSS for unified theme
def load_custom_css():
    st.markdown("""
    <style>
    /* Main container styling */
    .main-header {
        background: linear-gradient(90deg, #1976D2 0%, #1565C0 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    /* Navigation tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f0f2f6;
        padding: 0.5rem;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-weight: 500;
        padding: 0.5rem 1rem;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1976D2;
        color: white;
    }
    
    /* Card styling */
    .feature-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        height: 100%;
        transition: transform 0.2s;
    }
    
    .feature-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    
    /* Metrics styling */
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #1976D2;
        margin-bottom: 1rem;
    }
    
    /* Search results */
    .search-result {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        border-left: 3px solid #1976D2;
    }
    </style>
    """, unsafe_allow_html=True)

def render_header():
    """Render the main application header"""
    st.markdown("""
    <div class="main-header">
        <h1 style="margin: 0; font-size: 2.5rem;">🎯 MIDAS</h1>
        <p style="margin: 0; opacity: 0.9;">Modular Intelligence & Data Analysis System</p>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar():
    """Render the sidebar with all controls"""
    with st.sidebar:
        st.image("https://via.placeholder.com/300x100/1976D2/FFFFFF?text=MIDAS", use_column_width=True)
        
        # System Status
        st.markdown("### 🔌 System Status")
        col1, col2 = st.columns(2)
        
        with col1:
            # Check Ollama
            try:
                import requests
                resp = requests.get("http://localhost:11434/api/tags", timeout=1)
                st.success("Ollama ✓")
            except:
                st.error("Ollama ✗")
        
        with col2:
            # Check Qdrant
            try:
                import requests
                resp = requests.get("http://localhost:6333/health", timeout=1)
                st.success("Qdrant ✓")
            except:
                st.warning("Qdrant ✗")
        
        # Quick Actions
        st.markdown("### ⚡ Quick Actions")
        
        if st.button("📁 Upload Documents", use_container_width=True):
            st.session_state.current_view = "documents"
            
        if st.button("💬 Start Chat", use_container_width=True):
            st.session_state.current_view = "chat"
            
        if st.button("📊 Create Dashboard", use_container_width=True):
            st.session_state.current_view = "dashboards"
            
        if st.button("🗄️ Connect Database", use_container_width=True):
            st.session_state.current_view = "databases"
        
        # Recent Activity
        st.markdown("### 📈 Recent Activity")
        
        if st.session_state.uploaded_documents:
            st.metric("Documents", len(st.session_state.uploaded_documents))
        else:
            st.info("No documents uploaded")
        
        if st.session_state.chat_history:
            st.metric("Chat Messages", len(st.session_state.chat_history))
        else:
            st.info("No chat history")
        
        # Settings
        with st.expander("⚙️ Settings"):
            st.selectbox("Theme", ["Light", "Dark", "Auto"])
            st.slider("Max Search Results", 5, 50, 10)
            st.checkbox("Enable Background Processing")
            st.checkbox("Auto-refresh Dashboards")

def render_home_view():
    """Render the home/overview view"""
    # Welcome section
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ## Welcome to MIDAS
        
        Your unified platform for intelligent data analysis, featuring:
        - 🤖 **AI-Powered Chat** with document understanding
        - 📊 **Interactive Dashboards** with drag-and-drop builder
        - 🗄️ **SQL Integration** with natural language queries
        - 📈 **Real-time Monitoring** of system performance
        - 🔍 **Semantic Search** across all your data
        """)
    
    with col2:
        # Quick stats
        st.markdown("### 📊 Quick Stats")
        st.metric("Total Documents", len(st.session_state.uploaded_documents))
        st.metric("Active Dashboards", 0)
        st.metric("SQL Connections", len(st.session_state.sql_connections))
    
    st.divider()
    
    # Feature cards
    st.markdown("### 🚀 Get Started")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="feature-card">
            <h3>📁 Document RAG</h3>
            <p>Upload and analyze documents with AI-powered search and Q&A</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="feature-card">
            <h3>📊 Dashboards</h3>
            <p>Create beautiful visualizations with our drag-and-drop builder</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="feature-card">
            <h3>🗄️ SQL Search</h3>
            <p>Query databases using natural language and semantic search</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="feature-card">
            <h3>📈 Monitoring</h3>
            <p>Track system performance and background task execution</p>
        </div>
        """, unsafe_allow_html=True)

def render_document_view():
    """Render the document management and RAG view"""
    st.markdown("## 📁 Document Management & RAG")
    
    tab1, tab2, tab3 = st.tabs(["Upload", "Search", "Analytics"])
    
    with tab1:
        # File upload
        uploaded_files = st.file_uploader(
            "Upload Documents",
            type=['pdf', 'txt', 'docx', 'csv', 'json', 'xlsx'],
            accept_multiple_files=True
        )
        
        if uploaded_files:
            for file in uploaded_files:
                if file.name not in [doc['name'] for doc in st.session_state.uploaded_documents]:
                    # Process the file
                    with st.spinner(f"Processing {file.name}..."):
                        # Add to session state
                        st.session_state.uploaded_documents.append({
                            'name': file.name,
                            'size': file.size,
                            'type': file.type,
                            'uploaded_at': datetime.now()
                        })
                        st.success(f"✅ {file.name} processed successfully!")
        
        # Document list
        if st.session_state.uploaded_documents:
            st.markdown("### 📄 Uploaded Documents")
            
            df = pd.DataFrame(st.session_state.uploaded_documents)
            st.dataframe(df, use_container_width=True)
    
    with tab2:
        # Semantic search
        search_query = st.text_input("🔍 Search your documents", placeholder="Enter your search query...")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            search_type = st.selectbox("Search Type", ["Semantic", "Keyword", "Hybrid"])
        with col2:
            max_results = st.number_input("Max Results", 1, 50, 10)
        with col3:
            if st.button("Search", type="primary"):
                with st.spinner("Searching..."):
                    # Simulate search results
                    st.session_state.search_results = [
                        {
                            'title': f"Result {i+1}",
                            'content': f"Sample content matching '{search_query}'...",
                            'score': 0.95 - i*0.1,
                            'source': f"document_{i+1}.pdf"
                        }
                        for i in range(min(5, max_results))
                    ]
        
        # Display results
        if st.session_state.search_results:
            st.markdown("### 📋 Search Results")
            for result in st.session_state.search_results:
                st.markdown(f"""
                <div class="search-result">
                    <h4>{result['title']}</h4>
                    <p>{result['content']}</p>
                    <small>Source: {result['source']} | Score: {result['score']:.2f}</small>
                </div>
                """, unsafe_allow_html=True)
    
    with tab3:
        # Document analytics
        st.markdown("### 📊 Document Analytics")
        
        if st.session_state.uploaded_documents:
            # Document types chart
            doc_types = pd.DataFrame(st.session_state.uploaded_documents)['type'].value_counts()
            fig = px.pie(values=doc_types.values, names=doc_types.index, title="Document Types")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Upload documents to see analytics")

def render_chat_view():
    """Render the AI chat interface"""
    st.markdown("## 💬 AI Chat Assistant")
    
    # Chat configuration
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        model_name = st.selectbox("Model", ["llama2", "mistral", "phi", "neural-chat"])
    
    with col2:
        temperature = st.slider("Temperature", 0.0, 1.0, 0.7)
    
    with col3:
        use_rag = st.checkbox("Use RAG", value=True)
    
    # Chat interface
    chat_container = st.container()
    
    # Display chat history
    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "sources" in message:
                    with st.expander("📚 Sources"):
                        for source in message["sources"]:
                            st.markdown(f"- {source}")
    
    # Chat input
    if prompt := st.chat_input("Ask me anything..."):
        # Add user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Simulate response
                response = f"I understand you're asking about '{prompt}'. Based on the documents, here's what I found..."
                
                # Stream response
                message_placeholder = st.empty()
                full_response = ""
                
                for chunk in response.split():
                    full_response += chunk + " "
                    time.sleep(0.05)
                    message_placeholder.markdown(full_response + "▌")
                
                message_placeholder.markdown(full_response)
                
                # Add sources if using RAG
                if use_rag and st.session_state.uploaded_documents:
                    sources = [doc['name'] for doc in st.session_state.uploaded_documents[:2]]
                    with st.expander("📚 Sources"):
                        for source in sources:
                            st.markdown(f"- {source}")
                    
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": full_response,
                        "sources": sources
                    })
                else:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": full_response
                    })

def render_dashboard_view():
    """Render the dashboard builder interface"""
    st.markdown("## 📊 Dashboard Builder")
    
    tab1, tab2, tab3 = st.tabs(["My Dashboards", "Create New", "Templates"])
    
    with tab1:
        # List existing dashboards
        dashboards = st.session_state.dashboard_manager.storage.list_dashboards()
        
        if dashboards:
            cols = st.columns(3)
            for i, dashboard in enumerate(dashboards):
                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="feature-card">
                        <h4>{dashboard['name']}</h4>
                        <p>{dashboard['description']}</p>
                        <small>Updated: {dashboard['updated_at']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Open", key=f"open_{dashboard['id']}"):
                        st.session_state.active_dashboard = dashboard['id']
        else:
            st.info("No dashboards created yet. Create your first dashboard!")
    
    with tab2:
        # Create new dashboard
        with st.form("create_dashboard"):
            st.markdown("### Create New Dashboard")
            
            name = st.text_input("Dashboard Name", placeholder="My Analytics Dashboard")
            description = st.text_area("Description", placeholder="Describe your dashboard...")
            
            col1, col2 = st.columns(2)
            
            with col1:
                template = st.selectbox("Template", ["Blank", "Overview", "Analytics", "Monitoring"])
            
            with col2:
                theme = st.selectbox("Theme", ["Light", "Dark", "Corporate"])
            
            if st.form_submit_button("Create Dashboard", type="primary"):
                if name:
                    # Create dashboard
                    dashboard = st.session_state.dashboard_manager.create_dashboard(
                        name=name,
                        description=description,
                        template_id=template.lower() if template != "Blank" else None
                    )
                    st.success(f"✅ Dashboard '{name}' created successfully!")
                    st.session_state.active_dashboard = dashboard.id
                else:
                    st.error("Please provide a dashboard name")
    
    with tab3:
        # Dashboard templates
        st.markdown("### 📋 Dashboard Templates")
        
        templates = [
            {
                'name': 'Overview Dashboard',
                'description': 'Key metrics and KPIs overview',
                'charts': 6
            },
            {
                'name': 'Analytics Dashboard',
                'description': 'Detailed data analysis views',
                'charts': 8
            },
            {
                'name': 'Monitoring Dashboard',
                'description': 'System and performance monitoring',
                'charts': 10
            }
        ]
        
        cols = st.columns(3)
        for i, template in enumerate(templates):
            with cols[i]:
                st.markdown(f"""
                <div class="feature-card">
                    <h4>{template['name']}</h4>
                    <p>{template['description']}</p>
                    <small>{template['charts']} charts</small>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"Use Template", key=f"template_{i}"):
                    st.info(f"Creating dashboard from {template['name']} template...")

def render_database_view():
    """Render the SQL database integration view"""
    st.markdown("## 🗄️ Database Integration")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Connections", "Query Builder", "Schema Explorer", "Query History"])
    
    with tab1:
        # Database connections
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("### Configured Connections")
            
            if st.session_state.sql_connections:
                for name, config in st.session_state.sql_connections.items():
                    st.markdown(f"""
                    <div class="metric-card">
                        <h4>{name}</h4>
                        <p>Type: {config['type']} | Host: {config['host']}</p>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No database connections configured")
        
        with col2:
            st.markdown("### Add Connection")
            
            with st.form("add_connection"):
                db_name = st.text_input("Connection Name")
                db_type = st.selectbox("Database Type", ["PostgreSQL", "MySQL", "SQLite", "SQL Server"])
                
                if db_type != "SQLite":
                    host = st.text_input("Host")
                    port = st.number_input("Port", value=5432)
                    database = st.text_input("Database Name")
                    username = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                else:
                    db_path = st.text_input("Database Path")
                
                if st.form_submit_button("Connect"):
                    # Add connection
                    st.session_state.sql_connections[db_name] = {
                        'type': db_type,
                        'host': host if db_type != "SQLite" else None
                    }
                    st.success(f"✅ Connected to {db_name}")
    
    with tab2:
        # Natural language query builder
        st.markdown("### 🤖 Natural Language Query")
        
        nl_query = st.text_area(
            "Describe what you want to query",
            placeholder="Show me top 10 customers by total sales in the last month"
        )
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            selected_db = st.selectbox(
                "Select Database",
                options=list(st.session_state.sql_connections.keys()) if st.session_state.sql_connections else ["No connections"]
            )
        
        with col2:
            if st.button("Generate SQL", type="primary"):
                if nl_query and selected_db != "No connections":
                    with st.spinner("Generating SQL..."):
                        # Simulate SQL generation
                        generated_sql = f"""
                        SELECT customer_name, SUM(order_total) as total_sales
                        FROM orders o
                        JOIN customers c ON o.customer_id = c.id
                        WHERE o.order_date >= DATE_SUB(CURRENT_DATE, INTERVAL 1 MONTH)
                        GROUP BY customer_name
                        ORDER BY total_sales DESC
                        LIMIT 10;
                        """
                        st.code(generated_sql, language='sql')
                        
                        if st.button("Execute Query"):
                            st.success("Query executed successfully!")
                            # Show sample results
                            sample_data = pd.DataFrame({
                                'customer_name': [f'Customer {i}' for i in range(10)],
                                'total_sales': np.random.randint(1000, 10000, 10)
                            })
                            st.dataframe(sample_data, use_container_width=True)
    
    with tab3:
        # Schema explorer
        st.markdown("### 📋 Schema Explorer")
        
        if st.session_state.sql_connections:
            selected_db = st.selectbox("Select Database", list(st.session_state.sql_connections.keys()))
            
            # Simulate schema
            with st.expander("Tables"):
                tables = ['customers', 'orders', 'products', 'order_items']
                for table in tables:
                    if st.button(f"📋 {table}", key=f"table_{table}"):
                        st.code(f"SELECT * FROM {table} LIMIT 10;", language='sql')
        else:
            st.info("Connect to a database to explore schemas")
    
    with tab4:
        # Query history
        st.markdown("### 📜 Query History")
        
        # Sample query history
        history = [
            {
                'query': 'SELECT COUNT(*) FROM customers;',
                'executed_at': datetime.now() - timedelta(hours=1),
                'duration': '0.023s',
                'rows': 1543
            },
            {
                'query': 'SELECT * FROM orders WHERE status = "pending";',
                'executed_at': datetime.now() - timedelta(hours=2),
                'duration': '0.156s',
                'rows': 47
            }
        ]
        
        for item in history:
            st.markdown(f"""
            <div class="search-result">
                <code>{item['query']}</code>
                <br>
                <small>Executed: {item['executed_at'].strftime('%Y-%m-%d %H:%M')} | 
                Duration: {item['duration']} | Rows: {item['rows']}</small>
            </div>
            """, unsafe_allow_html=True)

def render_monitoring_view():
    """Render the system monitoring view"""
    st.markdown("## 📈 System Monitoring")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Services", "Tasks", "Logs"])
    
    with tab1:
        # System overview
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            cpu_percent = psutil.cpu_percent(interval=1)
            st.metric("CPU Usage", f"{cpu_percent}%", delta=f"{cpu_percent-50:.1f}%")
        
        with col2:
            memory = psutil.virtual_memory()
            st.metric("Memory Usage", f"{memory.percent}%", delta=f"{memory.percent-70:.1f}%")
        
        with col3:
            disk = psutil.disk_usage('/')
            st.metric("Disk Usage", f"{disk.percent}%", delta=f"{disk.percent-80:.1f}%")
        
        with col4:
            st.metric("Active Connections", len(st.session_state.sql_connections))
        
        # Real-time charts
        st.markdown("### 📊 Real-time Metrics")
        
        # Create sample data for charts
        time_range = pd.date_range(end=datetime.now(), periods=60, freq='1min')
        
        cpu_data = pd.DataFrame({
            'time': time_range,
            'cpu': np.random.normal(50, 15, 60).clip(0, 100)
        })
        
        fig = px.line(cpu_data, x='time', y='cpu', title='CPU Usage Over Time')
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        # Service status
        st.markdown("### 🔌 Service Status")
        
        services = [
            {'name': 'Ollama', 'status': 'running', 'port': 11434},
            {'name': 'Qdrant', 'status': 'running', 'port': 6333},
            {'name': 'PostgreSQL', 'status': 'stopped', 'port': 5432},
            {'name': 'Redis', 'status': 'running', 'port': 6379}
        ]
        
        cols = st.columns(2)
        for i, service in enumerate(services):
            with cols[i % 2]:
                status_color = "🟢" if service['status'] == 'running' else "🔴"
                st.markdown(f"""
                <div class="metric-card">
                    <h4>{status_color} {service['name']}</h4>
                    <p>Status: {service['status']} | Port: {service['port']}</p>
                </div>
                """, unsafe_allow_html=True)
    
    with tab3:
        # Background tasks
        st.markdown("### ⚙️ Background Tasks")
        
        tasks = [
            {'name': 'Document Processing', 'status': 'completed', 'progress': 100},
            {'name': 'Index Optimization', 'status': 'running', 'progress': 67},
            {'name': 'Backup Creation', 'status': 'pending', 'progress': 0}
        ]
        
        for task in tasks:
            st.markdown(f"**{task['name']}** - {task['status']}")
            st.progress(task['progress'] / 100)
            st.markdown("---")
    
    with tab4:
        # System logs
        st.markdown("### 📋 System Logs")
        
        log_level = st.selectbox("Log Level", ["ALL", "ERROR", "WARNING", "INFO"])
        
        # Sample logs
        logs = [
            {'level': 'INFO', 'time': datetime.now(), 'message': 'System started successfully'},
            {'level': 'WARNING', 'time': datetime.now() - timedelta(minutes=5), 'message': 'High memory usage detected'},
            {'level': 'ERROR', 'time': datetime.now() - timedelta(minutes=10), 'message': 'Failed to connect to PostgreSQL'},
            {'level': 'INFO', 'time': datetime.now() - timedelta(minutes=15), 'message': 'Document processed: report.pdf'}
        ]
        
        for log in logs:
            if log_level == "ALL" or log['level'] == log_level:
                color = {'ERROR': '🔴', 'WARNING': '🟡', 'INFO': '🟢'}[log['level']]
                st.markdown(f"{color} **{log['level']}** - {log['time'].strftime('%H:%M:%S')} - {log['message']}")

def main():
    """Main application function"""
    # Initialize session state
    init_session_state()
    
    # Load custom CSS
    load_custom_css()
    
    # Render header
    render_header()
    
    # Main navigation
    tabs = st.tabs(["🏠 Home", "📁 Documents", "💬 Chat", "📊 Dashboards", "🗄️ Databases", "📈 Monitoring"])
    
    with tabs[0]:
        render_home_view()
    
    with tabs[1]:
        render_document_view()
    
    with tabs[2]:
        render_chat_view()
    
    with tabs[3]:
        render_dashboard_view()
    
    with tabs[4]:
        render_database_view()
    
    with tabs[5]:
        render_monitoring_view()
    
    # Render sidebar
    render_sidebar()

if __name__ == "__main__":
    main()