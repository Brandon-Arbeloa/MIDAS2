"""
MIDAS - Modular Intelligence & Data Analysis System
Simplified unified application with improved theming
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
import logging
from typing import Dict, List, Any, Optional

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

# Initialize session state
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.current_tab = 0
    st.session_state.chat_messages = []
    st.session_state.uploaded_files = []
    st.session_state.dashboards = []
    st.session_state.db_connections = []
    st.session_state.search_results = []

# Initialize theme
if 'theme' not in st.session_state:
    st.session_state.theme = 'light'

def apply_theme():
    """Apply theme-based CSS"""
    if st.session_state.theme == 'dark':
        # Dark mode: Black/Red theme
        st.markdown("""
        <style>
            /* Dark mode styles */
            .stApp {
                background-color: #0a0a0a !important;
                color: #ffffff !important;
            }
            
            .main-header {
                background: linear-gradient(135deg, #8B0000 0%, #DC143C 100%) !important;
                padding: 2rem;
                border-radius: 10px;
                color: white !important;
                text-align: center;
                margin-bottom: 2rem;
                box-shadow: 0 4px 6px rgba(220, 20, 60, 0.3);
            }
            
            .feature-card {
                background: #1a1a1a !important;
                padding: 1.5rem;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(220, 20, 60, 0.2);
                margin-bottom: 1rem;
                border-left: 4px solid #DC143C;
                color: #ffffff !important;
            }
            
            .feature-card h4 {
                color: #FF6B6B !important;
            }
            
            .stTabs [data-baseweb="tab-list"] {
                gap: 24px;
                background-color: #0a0a0a !important;
            }
            
            .stTabs [data-baseweb="tab"] {
                height: 50px;
                padding-left: 20px;
                padding-right: 20px;
                background-color: #1a1a1a !important;
                border-radius: 10px;
                font-weight: 600;
                color: #ffffff !important;
                border: 1px solid #333 !important;
            }
            
            .stTabs [aria-selected="true"] {
                background-color: #DC143C !important;
                color: white !important;
                border: 1px solid #DC143C !important;
            }
            
            /* Sidebar dark mode */
            section[data-testid="stSidebar"] {
                background-color: #0f0f0f !important;
            }
            section[data-testid="stSidebar"] > div {
                background-color: #0f0f0f !important;
            }
            
            /* Input fields dark mode */
            .stTextInput > div > div > input {
                background-color: #1a1a1a !important;
                color: white !important;
                border: 2px solid #DC143C !important;
            }
            
            .stTextArea > div > div > textarea {
                background-color: #1a1a1a !important;
                color: white !important;
                border: 2px solid #DC143C !important;
            }
            
            /* Buttons dark mode */
            .stButton > button {
                background-color: #DC143C !important;
                color: white !important;
                border: none !important;
                font-weight: 600;
            }
            
            .stButton > button:hover {
                background-color: #8B0000 !important;
            }
            
            /* Selectbox dark mode */
            .stSelectbox > div > div > div {
                background-color: #1a1a1a !important;
                color: white !important;
                border: 2px solid #DC143C !important;
            }
            
            /* Metrics dark mode */
            [data-testid="metric-container"] {
                background-color: #1a1a1a !important;
                border: 2px solid #DC143C !important;
                border-radius: 8px;
                padding: 1rem;
                color: white !important;
            }
            
            /* Chat messages dark mode */
            .stChatMessage {
                background-color: #1a1a1a !important;
                border: 1px solid #333 !important;
                color: white !important;
            }
            
            /* Dataframe dark mode */
            .stDataFrame {
                background-color: #1a1a1a !important;
                color: white !important;
            }
            
            /* All text white in dark mode */
            .stMarkdown, .stText, p, div, span, h1, h2, h3, h4, h5, h6 {
                color: #ffffff !important;
            }
        </style>
        """, unsafe_allow_html=True)
    else:
        # Light mode: Blue/Dark Gray theme
        st.markdown("""
        <style>
            /* Light mode styles */
            .stApp {
                background-color: #374151 !important;
                color: #FFFFFF !important;
            }
            
            .main-header {
                background: linear-gradient(135deg, #1976D2 0%, #2196F3 100%) !important;
                padding: 2rem;
                border-radius: 10px;
                color: white !important;
                text-align: center;
                margin-bottom: 2rem;
                box-shadow: 0 4px 6px rgba(25, 118, 210, 0.2);
            }
            
            .feature-card {
                background: #4B5563 !important;
                padding: 1.5rem;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                margin-bottom: 1rem;
                border-left: 4px solid #2196F3;
                color: #FFFFFF !important;
            }
            
            .feature-card h4 {
                color: #60A5FA !important;
            }
            
            .stTabs [data-baseweb="tab-list"] {
                gap: 24px;
                background-color: #4B5563 !important;
                padding: 0.5rem;
                border-radius: 12px;
            }
            
            .stTabs [data-baseweb="tab"] {
                height: 50px;
                padding-left: 20px;
                padding-right: 20px;
                background-color: #6B7280 !important;
                border-radius: 10px;
                font-weight: 600;
                color: #FFFFFF !important;
                border: 1px solid #9CA3AF !important;
            }
            
            .stTabs [aria-selected="true"] {
                background-color: #2196F3 !important;
                color: white !important;
                border: 1px solid #2196F3 !important;
                box-shadow: 0 2px 4px rgba(33, 150, 243, 0.3);
            }
            
            /* Sidebar light mode */
            section[data-testid="stSidebar"] {
                background-color: #4B5563 !important;
            }
            section[data-testid="stSidebar"] > div {
                background-color: #4B5563 !important;
            }
            
            /* Input fields light mode */
            .stTextInput > div > div > input {
                background-color: #6B7280 !important;
                color: #FFFFFF !important;
                border: 2px solid #9CA3AF !important;
            }
            
            .stTextInput > div > div > input:focus {
                border-color: #2196F3 !important;
            }
            
            .stTextArea > div > div > textarea {
                background-color: #6B7280 !important;
                color: #FFFFFF !important;
                border: 2px solid #9CA3AF !important;
            }
            
            .stTextArea > div > div > textarea:focus {
                border-color: #2196F3 !important;
            }
            
            /* Buttons light mode */
            .stButton > button {
                background-color: #2196F3 !important;
                color: white !important;
                border: none !important;
                font-weight: 600;
            }
            
            .stButton > button:hover {
                background-color: #1976D2 !important;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
            }
            
            /* Selectbox light mode */
            .stSelectbox > div > div > div {
                background-color: #6B7280 !important;
                color: #FFFFFF !important;
                border: 2px solid #9CA3AF !important;
            }
            
            /* Metrics light mode */
            [data-testid="metric-container"] {
                background-color: #4B5563 !important;
                border: 2px solid #60A5FA !important;
                border-radius: 8px;
                padding: 1rem;
                color: #60A5FA !important;
            }
            
            /* Chat messages light mode */
            .stChatMessage {
                background-color: #4B5563 !important;
                border: 1px solid #9CA3AF !important;
                color: #FFFFFF !important;
            }
            
            /* Dataframe light mode */
            .stDataFrame {
                background-color: #4B5563 !important;
                color: #FFFFFF !important;
            }
            
            /* All text white in light mode with dark gray background */
            .stMarkdown, .stText, p, div, span, h1, h2, h3, h4, h5, h6 {
                color: #ffffff !important;
            }
        </style>
        """, unsafe_allow_html=True)

def render_header():
    """Render application header"""
    st.markdown("""
    <div class="main-header">
        <h1 style="margin: 0;">🎯 MIDAS</h1>
        <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">Modular Intelligence & Data Analysis System</p>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar():
    """Render sidebar with system status and quick actions"""
    with st.sidebar:
        # Theme toggle at the top
        st.markdown("### 🎨 Theme")
        theme_toggle = st.checkbox("🌙 Dark Mode", value=st.session_state.theme == 'dark', key="theme_toggle")
        if theme_toggle != (st.session_state.theme == 'dark'):
            st.session_state.theme = 'dark' if theme_toggle else 'light'
            st.rerun()
        
        st.divider()
        
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
            # Check services
            st.info("Docker ◯")
        
        st.markdown("### 📊 Quick Stats")
        st.metric("Documents", len(st.session_state.uploaded_files))
        st.metric("Chats", len(st.session_state.chat_messages))
        st.metric("Dashboards", len(st.session_state.dashboards))
        
        st.markdown("### ⚡ Quick Actions")
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
        
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()
        
        if st.button("📥 Export Data", use_container_width=True):
            st.info("Export functionality coming soon!")

def home_tab():
    """Home/Overview tab"""
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ## Welcome to MIDAS
        
        Your all-in-one platform for intelligent data analysis:
        
        - **🤖 AI Chat**: Chat with documents using Ollama LLMs
        - **📊 Dashboards**: Create interactive visualizations
        - **🔍 Smart Search**: Semantic search across all content
        - **🗄️ SQL Integration**: Query databases with natural language
        - **📈 Monitoring**: Track system performance in real-time
        """)
        
        st.info("💡 **Tip**: Use the tabs above to navigate between features")
    
    with col2:
        st.markdown("### 🚀 Getting Started")
        st.markdown("""
        1. Upload documents in the **Documents** tab
        2. Ask questions in the **Chat** tab
        3. Create visualizations in **Dashboards**
        4. Connect databases in **SQL** tab
        5. Monitor performance in **System**
        """)
    
    # Feature cards
    st.markdown("### ✨ Key Features")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="feature-card">
            <h4>📚 RAG System</h4>
            <p>Upload PDFs, Word docs, CSVs and more. Ask questions and get AI-powered answers with source citations.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="feature-card">
            <h4>📊 Visual Analytics</h4>
            <p>Drag-and-drop dashboard builder with real-time data updates and interactive charts.</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="feature-card">
            <h4>🔗 SQL Integration</h4>
            <p>Connect to any database and query using natural language. Supports PostgreSQL, MySQL, and more.</p>
        </div>
        """, unsafe_allow_html=True)

def documents_tab():
    """Document management tab"""
    st.markdown("## 📁 Document Management")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # File uploader
        uploaded = st.file_uploader(
            "Upload documents for RAG processing",
            type=['pdf', 'txt', 'docx', 'csv', 'json', 'xlsx'],
            accept_multiple_files=True
        )
        
        if uploaded:
            for file in uploaded:
                if file.name not in [f['name'] for f in st.session_state.uploaded_files]:
                    st.session_state.uploaded_files.append({
                        'name': file.name,
                        'size': file.size,
                        'type': file.type,
                        'uploaded': datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    st.success(f"✅ Uploaded: {file.name}")
    
    with col2:
        st.markdown("### 📋 Supported Formats")
        st.markdown("""
        - PDF documents
        - Word documents (.docx)
        - Text files (.txt)
        - CSV files
        - Excel spreadsheets
        - JSON files
        """)
    
    # Document list
    if st.session_state.uploaded_files:
        st.markdown("### 📄 Uploaded Documents")
        
        df = pd.DataFrame(st.session_state.uploaded_files)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Search documents
        search = st.text_input("🔍 Search documents...", placeholder="Enter keywords")
        if search:
            filtered = [f for f in st.session_state.uploaded_files if search.lower() in f['name'].lower()]
            if filtered:
                st.write(f"Found {len(filtered)} matching documents")
    else:
        st.info("No documents uploaded yet. Upload some files to get started!")

def chat_tab():
    """AI Chat tab"""
    st.markdown("## 💬 AI Chat Assistant")
    
    # Chat settings
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        model = st.selectbox("Model", ["llama2", "mistral", "phi", "neural-chat"])
    with col2:
        temperature = st.slider("Temperature", 0.0, 1.0, 0.7)
    with col3:
        use_rag = st.checkbox("Use RAG", value=True)
    
    # Chat interface
    chat_container = st.container()
    
    # Display messages
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "sources" in msg:
                with st.expander("📚 Sources"):
                    for source in msg["sources"]:
                        st.write(f"- {source}")
    
    # Chat input
    if prompt := st.chat_input("Ask me anything..."):
        # Add user message
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Generate response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            # Check if Ollama is available
            try:
                import requests
                resp = requests.get("http://localhost:11434/api/tags", timeout=1)
                
                # Simulate streaming response
                response = f"I understand you're asking about '{prompt}'. "
                if use_rag and st.session_state.uploaded_files:
                    response += f"Based on the {len(st.session_state.uploaded_files)} documents you've uploaded, "
                response += "here's what I can tell you..."
                
                # Stream the response
                full_response = ""
                for word in response.split():
                    full_response += word + " "
                    time.sleep(0.05)
                    message_placeholder.markdown(full_response + "▌")
                
                message_placeholder.markdown(full_response)
                
                # Add to history
                msg_data = {"role": "assistant", "content": full_response}
                if use_rag and st.session_state.uploaded_files:
                    msg_data["sources"] = [f["name"] for f in st.session_state.uploaded_files[:2]]
                
                st.session_state.chat_messages.append(msg_data)
                
            except:
                st.error("⚠️ Ollama is not running. Please start Ollama to use the chat feature.")
                st.code("ollama serve", language="bash")

def dashboards_tab():
    """Dashboard builder tab"""
    st.markdown("## 📊 Dashboard Builder")
    
    tab1, tab2, tab3 = st.tabs(["My Dashboards", "Create New", "Templates"])
    
    with tab1:
        if st.session_state.dashboards:
            cols = st.columns(3)
            for i, dash in enumerate(st.session_state.dashboards):
                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="feature-card">
                        <h4>{dash['name']}</h4>
                        <p>{dash['description']}</p>
                        <small>Created: {dash['created']}</small>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Open", key=f"open_dash_{i}"):
                        st.info(f"Opening {dash['name']}...")
        else:
            st.info("No dashboards created yet. Create your first dashboard!")
    
    with tab2:
        with st.form("create_dashboard"):
            name = st.text_input("Dashboard Name")
            description = st.text_area("Description")
            
            col1, col2 = st.columns(2)
            with col1:
                template = st.selectbox("Template", ["Blank", "Analytics", "Monitoring"])
            with col2:
                theme = st.selectbox("Theme", ["Light", "Dark", "Corporate"])
            
            if st.form_submit_button("Create Dashboard"):
                if name:
                    st.session_state.dashboards.append({
                        'name': name,
                        'description': description,
                        'template': template,
                        'theme': theme,
                        'created': datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    st.success(f"✅ Dashboard '{name}' created!")
                    st.rerun()
    
    with tab3:
        st.markdown("### Dashboard Templates")
        
        templates = [
            {"name": "Analytics Dashboard", "desc": "Data analysis with charts and metrics"},
            {"name": "Monitoring Dashboard", "desc": "System performance and health"},
            {"name": "Executive Overview", "desc": "High-level KPIs and summaries"}
        ]
        
        cols = st.columns(3)
        for i, tmpl in enumerate(templates):
            with cols[i]:
                st.markdown(f"""
                <div class="feature-card">
                    <h4>{tmpl['name']}</h4>
                    <p>{tmpl['desc']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"Use This", key=f"tmpl_{i}"):
                    st.info(f"Creating from template: {tmpl['name']}")

def sql_tab():
    """SQL Integration tab"""
    st.markdown("## 🗄️ SQL Database Integration")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Natural language query
        nl_query = st.text_area(
            "Ask a question about your data",
            placeholder="Show me the top 10 customers by revenue last month"
        )
        
        if st.button("🔮 Generate SQL", type="primary"):
            if nl_query:
                # Simulate SQL generation
                st.markdown("### Generated SQL:")
                sql = f"""SELECT customer_name, SUM(revenue) as total_revenue
FROM sales
WHERE date >= DATE_SUB(CURRENT_DATE, INTERVAL 1 MONTH)
GROUP BY customer_name
ORDER BY total_revenue DESC
LIMIT 10;"""
                st.code(sql, language="sql")
                
                # Sample results
                if st.button("▶️ Execute Query"):
                    data = pd.DataFrame({
                        'customer_name': [f'Customer {i+1}' for i in range(10)],
                        'total_revenue': np.random.randint(10000, 100000, 10)
                    })
                    st.dataframe(data, use_container_width=True)
    
    with col2:
        st.markdown("### 🔌 Database Connections")
        
        with st.form("add_db"):
            db_type = st.selectbox("Type", ["PostgreSQL", "MySQL", "SQLite"])
            host = st.text_input("Host", "localhost")
            port = st.number_input("Port", value=5432)
            
            if st.form_submit_button("Connect"):
                st.session_state.db_connections.append({
                    'type': db_type,
                    'host': host,
                    'port': port
                })
                st.success("✅ Connected!")

def system_tab():
    """System monitoring tab"""
    st.markdown("## 📈 System Monitoring")
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("CPU Usage", "45%", "−5%")
    with col2:
        st.metric("Memory", "62%", "+3%")
    with col3:
        st.metric("Disk", "78%", "+1%")
    with col4:
        st.metric("Network", "12 MB/s", "+2 MB/s")
    
    # Charts
    tab1, tab2, tab3 = st.tabs(["Performance", "Services", "Logs"])
    
    with tab1:
        # Create sample performance data
        time_range = pd.date_range(end=datetime.now(), periods=50, freq='1min')
        
        perf_data = pd.DataFrame({
            'Time': time_range,
            'CPU': np.random.normal(45, 10, 50).clip(0, 100),
            'Memory': np.random.normal(62, 5, 50).clip(0, 100),
            'Disk I/O': np.random.normal(30, 15, 50).clip(0, 100)
        })
        
        fig = px.line(perf_data, x='Time', y=['CPU', 'Memory', 'Disk I/O'],
                     title='System Performance')
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        services = [
            {"name": "Ollama", "status": "🟢 Running", "port": 11434},
            {"name": "Streamlit", "status": "🟢 Running", "port": 8501},
            {"name": "PostgreSQL", "status": "🔴 Stopped", "port": 5432},
            {"name": "Redis", "status": "🟡 Starting", "port": 6379}
        ]
        
        for svc in services:
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.write(f"**{svc['name']}**")
            with col2:
                st.write(svc['status'])
            with col3:
                st.write(f"Port: {svc['port']}")
    
    with tab3:
        st.markdown("### Recent Logs")
        
        log_level = st.selectbox("Filter", ["All", "Error", "Warning", "Info"])
        
        logs = [
            ("INFO", "System initialized successfully"),
            ("WARNING", "High memory usage detected"),
            ("ERROR", "Failed to connect to PostgreSQL"),
            ("INFO", "Document processing completed"),
            ("INFO", "Dashboard saved successfully")
        ]
        
        for level, msg in logs:
            if log_level == "All" or log_level == level.capitalize():
                icon = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌"}[level]
                st.write(f"{icon} **{level}**: {msg}")

def main():
    """Main application"""
    # Apply theme CSS
    apply_theme()
    
    render_header()
    
    # Main navigation tabs
    tab_names = ["🏠 Home", "📁 Documents", "💬 Chat", "📊 Dashboards", "🗄️ SQL", "📈 System"]
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        home_tab()
    
    with tabs[1]:
        documents_tab()
    
    with tabs[2]:
        chat_tab()
    
    with tabs[3]:
        dashboards_tab()
    
    with tabs[4]:
        sql_tab()
    
    with tabs[5]:
        system_tab()
    
    # Render sidebar
    render_sidebar()

if __name__ == "__main__":
    main()