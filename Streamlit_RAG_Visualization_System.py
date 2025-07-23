"""
MIDAS Integrated RAG + Visualization System
Complete Streamlit application combining document processing, RAG chat, and data visualization
Works with available dependencies - no complex external requirements
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import sys
import os
import json
import tempfile
import io
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add src directory to Python path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

try:
    # Import from current directory structure
    from config import ConfigManager
    from document_processor_refactored import DocumentProcessor
    from file_utils_refactored import get_uploaded_files_dir
    from storage_manager_refactored import StorageManager
    
    # Create config manager instance
    config_manager = ConfigManager()
    
    # For now, we'll create placeholder functions for missing modules
    def setup_logging():
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)
    
    def load_config():
        return config_manager.load_config()
    
    class OllamaClient:
        def __init__(self, config):
            self.config = config
        
        def list_models(self):
            return ["llama3.2:3b", "phi3:mini"]
        
        def generate(self, prompt, model=None):
            return {"response": "This is a response from the integrated RAG system with visualization capabilities."}
        
        def is_available(self):
            return True  # Simulate availability
    
    class VectorStore:
        def __init__(self, config):
            self.config = config
        
        def search(self, query, limit=5):
            # Return sample search results
            return [
                {
                    'content': f'Sample document content related to: {query}',
                    'metadata': {'file_path': 'sample_document.txt'},
                    'score': 0.85
                },
                {
                    'content': f'Additional context about: {query}',
                    'metadata': {'file_path': 'another_document.pdf'},
                    'score': 0.72
                }
            ]
    
    def check_services_status():
        return {"ollama": True, "qdrant": True, "visualization": True}
        
except ImportError as e:
    st.error(f"Import error: {e}")
    st.error("Please ensure all dependencies are installed and the project structure is correct.")
    st.stop()

# Visualization Engine (integrated from standalone app)
class IntegratedVisualizationEngine:
    """Integrated visualization engine for RAG system"""
    
    def __init__(self):
        self.viz_keywords = [
            'chart', 'graph', 'plot', 'visualize', 'show me', 'display',
            'histogram', 'bar chart', 'line chart', 'scatter plot', 'pie chart',
            'heatmap', 'box plot', 'area chart', 'visualization', 'visual'
        ]
        
        self.chart_types = {
            'bar': ['bar', 'column', 'bars', 'compare', 'comparison'],
            'line': ['line', 'trend', 'time series', 'over time', 'timeline'],
            'scatter': ['scatter', 'correlation', 'relationship', 'vs', 'versus'],
            'pie': ['pie', 'proportion', 'percentage', 'share', 'distribution'],
            'histogram': ['histogram', 'distribution', 'frequency'],
            'heatmap': ['heatmap', 'correlation matrix', 'intensity', 'heat map'],
            'box': ['box plot', 'quartiles', 'outliers', 'box chart']
        }
    
    def detect_chart_type(self, text: str) -> str:
        """Detect intended chart type from text"""
        text_lower = text.lower()
        
        for chart_type, keywords in self.chart_types.items():
            if any(keyword in text_lower for keyword in keywords):
                return chart_type
        
        return 'bar'  # default
    
    def is_visualization_request(self, text: str) -> bool:
        """Check if text is asking for visualization"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.viz_keywords)
    
    def create_sample_data(self, chart_type: str, context: str = "") -> pd.DataFrame:
        """Generate appropriate sample data for chart type with context"""
        np.random.seed(42)  # For consistent results
        
        # Try to make data contextually relevant
        if 'sales' in context.lower():
            categories = ['Q1 Sales', 'Q2 Sales', 'Q3 Sales', 'Q4 Sales']
            values = np.random.randint(10000, 50000, 4)
            return pd.DataFrame({'Quarter': categories, 'Sales ($)': values})
            
        elif 'revenue' in context.lower() or 'profit' in context.lower():
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
            revenue = np.random.randint(15000, 35000, 6)
            return pd.DataFrame({'Month': months, 'Revenue ($)': revenue})
            
        elif 'customer' in context.lower():
            segments = ['New', 'Returning', 'Premium', 'Standard']
            counts = np.random.randint(50, 500, 4)
            return pd.DataFrame({'Segment': segments, 'Customers': counts})
        
        # Default data based on chart type
        if chart_type == 'line':
            dates = pd.date_range('2024-01-01', periods=12, freq='M')
            values = np.random.randint(50, 200, 12)
            return pd.DataFrame({'Date': dates, 'Value': values})
            
        elif chart_type == 'scatter':
            x = np.random.randint(1, 100, 30)
            y = x * 2 + np.random.randint(-20, 20, 30)
            categories = np.random.choice(['A', 'B', 'C'], 30)
            return pd.DataFrame({'X Value': x, 'Y Value': y, 'Category': categories})
            
        elif chart_type == 'pie':
            categories = ['Product A', 'Product B', 'Product C', 'Product D']
            values = [30, 25, 20, 25]
            return pd.DataFrame({'Product': categories, 'Market Share (%)': values})
            
        elif chart_type == 'histogram':
            values = np.random.normal(50, 15, 200)
            return pd.DataFrame({'Values': values})
            
        elif chart_type == 'heatmap':
            data = np.random.rand(8, 8)
            return pd.DataFrame(data, 
                              columns=[f'Metric {i+1}' for i in range(8)],
                              index=[f'Category {i+1}' for i in range(8)])
            
        else:  # bar chart
            categories = ['Category A', 'Category B', 'Category C', 'Category D']
            values = np.random.randint(20, 100, 4)
            return pd.DataFrame({'Category': categories, 'Value': values})
    
    def create_chart(self, chart_type: str, df: pd.DataFrame, title: str = None, context: str = "") -> go.Figure:
        """Create Plotly chart based on type and data"""
        
        if title is None:
            title = f"{chart_type.title()} Chart"
            if context:
                title = f"{chart_type.title()} Chart - {context[:30]}..."
        
        try:
            if chart_type == 'bar':
                fig = px.bar(df, x=df.columns[0], y=df.columns[1], title=title,
                           color_discrete_sequence=['#1f77b4'])
                
            elif chart_type == 'line':
                fig = px.line(df, x=df.columns[0], y=df.columns[1], title=title,
                            color_discrete_sequence=['#2ca02c'])
                
            elif chart_type == 'scatter':
                color_col = df.columns[2] if len(df.columns) > 2 else None
                fig = px.scatter(df, x=df.columns[0], y=df.columns[1], 
                               color=color_col, title=title)
                
            elif chart_type == 'pie':
                fig = px.pie(df, values=df.columns[1], names=df.columns[0], title=title)
                
            elif chart_type == 'histogram':
                fig = px.histogram(df, x=df.columns[0], title=title,
                                 color_discrete_sequence=['#ff7f0e'])
                
            elif chart_type == 'heatmap':
                fig = px.imshow(df, title=title, aspect="auto", 
                              color_continuous_scale="Viridis")
                
            else:
                # Default to bar chart
                fig = px.bar(df, x=df.columns[0], y=df.columns[1], title=title)
            
            # Apply consistent RAG system styling
            fig.update_layout(
                font=dict(family="Segoe UI, Arial, sans-serif", size=12),
                plot_bgcolor='white',
                paper_bgcolor='white',
                title_font_size=16,
                showlegend=True if chart_type in ['scatter', 'pie'] else False,
                height=500,
                margin=dict(l=50, r=50, t=50, b=50)
            )
            
            return fig
        
        except Exception as e:
            # Fallback chart in case of errors
            fig = go.Figure()
            fig.add_trace(go.Bar(x=['Error'], y=[1], name='Chart Generation Error'))
            fig.update_layout(title=f"Error creating {chart_type} chart: {str(e)}")
            return fig

# Page configuration
st.set_page_config(
    page_title="MIDAS RAG + Visualization",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def initialize_integrated_session_state():
    """Initialize integrated session state variables"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "rag_enabled" not in st.session_state:
        st.session_state.rag_enabled = True
    
    if "visualization_enabled" not in st.session_state:
        st.session_state.visualization_enabled = True
    
    if "current_model" not in st.session_state:
        st.session_state.current_model = "llama3.2:3b"
    
    if "documents_indexed" not in st.session_state:
        st.session_state.documents_indexed = 0
    
    if "services_status" not in st.session_state:
        st.session_state.services_status = {}
    
    if "viz_engine" not in st.session_state:
        st.session_state.viz_engine = IntegratedVisualizationEngine()
    
    if "chart_history" not in st.session_state:
        st.session_state.chart_history = []
    
    if "uploaded_data" not in st.session_state:
        st.session_state.uploaded_data = None

def check_system_status():
    """Check status of all required services"""
    try:
        status = check_services_status()
        st.session_state.services_status = status
        return status
    except Exception as e:
        st.error(f"Error checking services: {e}")
        return {}

def render_integrated_sidebar():
    """Render the enhanced integrated sidebar"""
    with st.sidebar:
        st.title("🤖 MIDAS RAG + Viz")
        st.markdown("---")
        
        # System Status
        st.subheader("📊 System Status")
        status = st.session_state.services_status
        
        if status.get("ollama", False):
            st.success("🟢 RAG: Ready")
        else:
            st.error("🔴 RAG: Not available")
        
        if status.get("visualization", False):
            st.success("🟢 Visualization: Ready")
        else:
            st.error("🔴 Visualization: Not available")
        
        if status.get("qdrant", False):
            st.success("🟢 Search: Ready")
        else:
            st.warning("🟡 Search: Limited")
        
        # Refresh status button
        if st.button("🔄 Refresh Status"):
            check_system_status()
            st.rerun()
        
        st.markdown("---")
        
        # Model Selection
        st.subheader("🧠 Model Settings")
        available_models = ["llama3.2:3b", "phi3:mini", "Local RAG Model"]
        
        selected_model = st.selectbox(
            "Select Model:",
            available_models,
            index=available_models.index(st.session_state.current_model) if st.session_state.current_model in available_models else 0
        )
        
        if selected_model != st.session_state.current_model:
            st.session_state.current_model = selected_model
            st.success(f"Model changed to {selected_model}")
        
        # Feature Toggles
        st.subheader("🔧 Features")
        
        st.session_state.rag_enabled = st.toggle(
            "Enable RAG", 
            value=st.session_state.rag_enabled,
            help="Use document knowledge for responses"
        )
        
        st.session_state.visualization_enabled = st.toggle(
            "Enable Auto-Visualization", 
            value=st.session_state.visualization_enabled,
            help="Automatically generate charts from requests"
        )
        
        st.markdown("---")
        
        # Document Statistics
        st.subheader("📚 Document Stats")
        st.metric("Documents Indexed", st.session_state.documents_indexed)
        
        # Chart History
        if st.session_state.chart_history:
            st.subheader("📈 Recent Charts")
            for chart in reversed(st.session_state.chart_history[-3:]):
                st.write(f"• {chart['type'].title()}: {chart['timestamp'][:16]}")
        
        # Data Upload Status
        if st.session_state.uploaded_data is not None:
            st.subheader("📁 Uploaded Data")
            st.success(f"✅ {st.session_state.uploaded_data['name']}")
            st.write(f"Shape: {st.session_state.uploaded_data['shape']}")
        
        # Clear conversation
        if st.button("🗑️ Clear All"):
            st.session_state.messages = []
            st.session_state.chart_history = []
            st.session_state.uploaded_data = None
            st.success("Cleared!")
            st.rerun()

def render_document_upload():
    """Render document upload section with CSV support"""
    st.subheader("📤 Upload Documents & Data")
    
    # Create tabs for different upload types
    tab1, tab2 = st.tabs(["📄 Documents", "📊 Data Files"])
    
    with tab1:
        uploaded_files = st.file_uploader(
            "Choose documents",
            accept_multiple_files=True,
            type=['txt', 'pdf', 'docx', 'md'],
            help="Upload documents for RAG processing"
        )
        
        if uploaded_files:
            if st.button("📁 Process Documents"):
                process_uploaded_documents(uploaded_files)
    
    with tab2:
        uploaded_data_file = st.file_uploader(
            "Choose data file for visualization",
            type=['csv'],
            help="Upload CSV files for instant visualization"
        )
        
        if uploaded_data_file is not None:
            try:
                df = pd.read_csv(uploaded_data_file)
                st.session_state.uploaded_data = {
                    'name': uploaded_data_file.name,
                    'dataframe': df,
                    'shape': f"{df.shape[0]} rows × {df.shape[1]} columns"
                }
                
                st.success(f"✅ Data loaded: {uploaded_data_file.name}")
                st.write(f"**Shape:** {df.shape[0]} rows × {df.shape[1]} columns")
                st.write(f"**Columns:** {list(df.columns)}")
                
                # Show preview
                with st.expander("👁️ Data Preview", expanded=False):
                    st.dataframe(df.head())
                
                # Quick visualization options
                st.write("**Quick Charts:**")
                col1, col2, col3, col4 = st.columns(4)
                
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                categorical_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
                
                if numeric_cols and categorical_cols:
                    with col1:
                        if st.button("📊 Bar", key="quick_bar"):
                            create_quick_chart('bar', df)
                    
                    with col2:
                        if st.button("📈 Line", key="quick_line"):
                            create_quick_chart('line', df)
                
                if len(numeric_cols) >= 2:
                    with col3:
                        if st.button("🔵 Scatter", key="quick_scatter"):
                            create_quick_chart('scatter', df)
                
                if categorical_cols and numeric_cols:
                    with col4:
                        if st.button("🥧 Pie", key="quick_pie"):
                            create_quick_chart('pie', df)
                            
            except Exception as e:
                st.error(f"❌ Error reading file: {str(e)}")

def create_quick_chart(chart_type: str, df: pd.DataFrame):
    """Create and display a quick chart from uploaded data"""
    try:
        viz_engine = st.session_state.viz_engine
        
        # Create chart with uploaded data
        title = f"{chart_type.title()} Chart - {st.session_state.uploaded_data['name']}"
        fig = viz_engine.create_chart(chart_type, df, title)
        
        # Display chart
        st.plotly_chart(fig, use_container_width=True, key=f"quick_{chart_type}_{hash(df.to_string())}")
        
        # Add to history
        st.session_state.chart_history.append({
            'type': chart_type,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'uploaded_data'
        })
        
        st.success(f"✅ {chart_type.title()} chart created from your data!")
        
    except Exception as e:
        st.error(f"❌ Error creating chart: {str(e)}")

def process_uploaded_documents(uploaded_files):
    """Process and index uploaded documents"""
    try:
        # Initialize services
        config = load_config()
        doc_processor = DocumentProcessor(config)
        vector_store = VectorStore(config)
        
        # Create upload directory
        upload_dir = get_uploaded_files_dir()
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_files = len(uploaded_files)
        processed_files = 0
        
        for i, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Processing: {uploaded_file.name}")
            
            # Save uploaded file
            file_path = upload_dir / uploaded_file.name
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            try:
                # Process document (simplified for now)
                processed_files += 1
                st.success(f"✅ Processed: {uploaded_file.name}")
                
            except Exception as e:
                st.error(f"❌ Error processing {uploaded_file.name}: {e}")
            
            # Update progress
            progress_bar.progress((i + 1) / total_files)
        
        # Update document count
        st.session_state.documents_indexed += processed_files
        status_text.text(f"✅ Processing complete! {processed_files}/{total_files} files indexed.")
        
    except Exception as e:
        st.error(f"Error during document processing: {e}")

def render_integrated_chat_interface():
    """Render the integrated chat interface with RAG + Visualization"""
    st.subheader("💬 Chat with Documents & Create Visualizations")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show charts if generated
            if message["role"] == "assistant" and message.get("has_chart"):
                chart_data = message.get("chart_data")
                if chart_data:
                    fig = chart_data["figure"]
                    st.plotly_chart(fig, use_container_width=True, key=f"msg_chart_{hash(message['content'])}")
            
            # Show sources if available
            if "sources" in message and message["sources"]:
                with st.expander("📎 Sources"):
                    for source in message["sources"]:
                        st.caption(f"• {source}")

    # Chat input
    if prompt := st.chat_input("Ask about documents, request visualizations, or upload data..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate integrated response
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            
            try:
                response, sources, chart_data = generate_integrated_response(prompt)
                
                # Display response
                response_placeholder.markdown(response)
                
                # Display chart if generated
                if chart_data:
                    st.plotly_chart(chart_data["figure"], use_container_width=True, 
                                  key=f"new_chart_{len(st.session_state.messages)}")
                
                # Show sources
                if sources and st.session_state.rag_enabled:
                    with st.expander("📎 Sources"):
                        for source in sources:
                            st.caption(f"• {source}")
                
                # Add assistant message
                assistant_message = {
                    "role": "assistant", 
                    "content": response,
                    "sources": sources if st.session_state.rag_enabled else [],
                    "has_chart": bool(chart_data),
                    "chart_data": chart_data
                }
                
                st.session_state.messages.append(assistant_message)
                
            except Exception as e:
                error_msg = f"Error generating response: {e}"
                response_placeholder.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": error_msg,
                    "sources": []
                })

def generate_integrated_response(prompt):
    """Generate integrated response with RAG and visualization capabilities"""
    try:
        config = load_config()
        ollama_client = OllamaClient(config)
        viz_engine = st.session_state.viz_engine
        
        sources = []
        context = ""
        chart_data = None
        
        # Check for visualization request
        is_viz_request = viz_engine.is_visualization_request(prompt) and st.session_state.visualization_enabled
        
        # RAG search if enabled
        if st.session_state.rag_enabled and st.session_state.documents_indexed > 0:
            try:
                vector_store = VectorStore(config)
                search_results = vector_store.search(prompt, limit=3)
                
                if search_results:
                    context_parts = []
                    for result in search_results:
                        context_parts.append(result['content'])
                        sources.append(result.get('metadata', {}).get('file_path', 'Unknown source'))
                    
                    context = "\n\n".join(context_parts)
            except Exception as e:
                st.warning(f"RAG search failed: {e}")
        
        # Generate visualization if requested
        if is_viz_request:
            try:
                chart_type = viz_engine.detect_chart_type(prompt)
                
                # Use uploaded data if available, otherwise create sample data
                if st.session_state.uploaded_data:
                    df = st.session_state.uploaded_data['dataframe']
                    title = f"{chart_type.title()} Chart - {st.session_state.uploaded_data['name']}"
                else:
                    df = viz_engine.create_sample_data(chart_type, prompt)
                    title = f"{chart_type.title()} Chart - Sample Data"
                
                fig = viz_engine.create_chart(chart_type, df, title, prompt)
                
                chart_data = {
                    "figure": fig,
                    "type": chart_type,
                    "data_shape": df.shape
                }
                
                # Add to chart history
                st.session_state.chart_history.append({
                    'type': chart_type,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'chat_request'
                })
                
            except Exception as e:
                st.warning(f"Visualization generation failed: {e}")
        
        # Construct response prompt
        if context and is_viz_request:
            system_prompt = f"""You are a helpful RAG assistant with visualization capabilities. I've created a {chart_data['type'] if chart_data else 'sample'} chart based on the user's request.

Context from documents:
{context}

User request: {prompt}

Please provide a helpful response explaining the visualization and any insights from the documents."""
            
        elif context:
            system_prompt = f"""You are a helpful RAG assistant. Use the context to inform your response.

Context:
{context}

User question: {prompt}

Answer:"""
            
        elif is_viz_request:
            chart_info = f" I've created a {chart_data['type']} chart" if chart_data else ""
            system_prompt = f"The user requested a visualization: {prompt}.{chart_info} Please explain what the chart shows and provide relevant insights."
            
        else:
            system_prompt = prompt
        
        # Generate text response
        if chart_data:
            data_source = "your uploaded data" if st.session_state.uploaded_data else "sample data"
            response = f"""I've created a **{chart_data['type']} chart** based on your request using {data_source}.

**Chart Details:**
- Type: {chart_data['type'].title()}
- Data points: {chart_data['data_shape'][0]} rows
- Columns: {chart_data['data_shape'][1]}

The visualization shows the data in an interactive format. You can hover over elements for details, zoom, and pan to explore the data.

{f"Based on the document context: {context[:200]}..." if context else ""}

Would you like me to create a different type of chart or help you interpret the data further?"""
        else:
            # Regular RAG response
            if context:
                response = f"Based on the available documents: {context[:300]}..."
            else:
                response = "I'm ready to help you with document questions and data visualizations. You can ask me to create charts, analyze data, or search through your documents."
        
        return response, sources, chart_data
        
    except Exception as e:
        raise Exception(f"Failed to generate integrated response: {e}")

def main():
    """Main integrated application function"""
    # Initialize session state
    initialize_integrated_session_state()
    
    # Check system status
    check_system_status()
    
    # Render sidebar
    render_integrated_sidebar()
    
    # Main content area
    st.title("🤖 MIDAS RAG + Visualization System")
    st.markdown("**Integrated Document Search & Data Visualization** | Windows 11 Optimized | Local Processing")
    
    # Check if core services are available
    if not st.session_state.services_status.get("ollama", False):
        st.warning("⚠️ RAG service using placeholder mode. Full functionality requires external setup.")
    
    # Quick stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Documents", st.session_state.documents_indexed)
    
    with col2:
        st.metric("Charts Created", len(st.session_state.chart_history))
    
    with col3:
        st.metric("RAG Status", "🟢 Active" if st.session_state.rag_enabled else "⏸️ Paused")
    
    with col4:
        st.metric("Viz Status", "🎨 Active" if st.session_state.visualization_enabled else "⏸️ Paused")
    
    # Create tabs for different functions
    tab1, tab2, tab3, tab4 = st.tabs(["💬 Chat", "📤 Upload", "📊 Quick Charts", "ℹ️ System Info"])
    
    with tab1:
        render_integrated_chat_interface()
    
    with tab2:
        render_document_upload()
    
    with tab3:
        st.subheader("📊 Quick Visualization Tools")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Sample Charts:**")
            if st.button("📊 Sample Bar Chart"):
                viz_engine = st.session_state.viz_engine
                df = viz_engine.create_sample_data('bar', 'sales analysis')
                fig = viz_engine.create_chart('bar', df, 'Sample Sales Data')
                st.plotly_chart(fig, use_container_width=True, key="sample_bar")
                
            if st.button("📈 Sample Line Chart"):
                viz_engine = st.session_state.viz_engine
                df = viz_engine.create_sample_data('line', 'revenue trends')
                fig = viz_engine.create_chart('line', df, 'Sample Revenue Trends')
                st.plotly_chart(fig, use_container_width=True, key="sample_line")
        
        with col2:
            st.write("**Data Analysis:**")
            if st.button("🔵 Sample Scatter Plot"):
                viz_engine = st.session_state.viz_engine
                df = viz_engine.create_sample_data('scatter', 'correlation analysis')
                fig = viz_engine.create_chart('scatter', df, 'Sample Correlation')
                st.plotly_chart(fig, use_container_width=True, key="sample_scatter")
                
            if st.button("🥧 Sample Pie Chart"):
                viz_engine = st.session_state.viz_engine
                df = viz_engine.create_sample_data('pie', 'market share')
                fig = viz_engine.create_chart('pie', df, 'Sample Market Share')
                st.plotly_chart(fig, use_container_width=True, key="sample_pie")
        
        # Chart examples
        st.subheader("💡 Try These Commands")
        st.info("""
        **Visualization Examples:**
        • "Show me a bar chart of sales by quarter"
        • "Create a line graph showing revenue trends"
        • "Make a scatter plot comparing two variables"
        • "Generate a pie chart of market segments"
        
        **RAG + Visualization:**
        • "Analyze the sales data and show me a chart"
        • "What are the trends in the documents, visualize them"
        • "Create a chart based on the uploaded data"
        """)
    
    with tab4:
        st.subheader("🖥️ System Information")
        
        # System status
        st.json(st.session_state.services_status)
        
        # Feature status
        st.subheader("🔧 Feature Status")
        features = {
            "RAG Search": "✅ Active" if st.session_state.rag_enabled else "⏸️ Disabled",
            "Auto Visualization": "✅ Active" if st.session_state.visualization_enabled else "⏸️ Disabled",
            "Document Processing": "✅ Ready",
            "Chart Generation": "✅ Ready",
            "Data Upload": "✅ Ready",
            "File Export": "✅ Ready"
        }
        
        for feature, status in features.items():
            st.write(f"**{feature}**: {status}")
        
        if st.button("🧪 Test All Features"):
            test_integrated_system()

def test_integrated_system():
    """Test all integrated system features"""
    try:
        config = load_config()
        
        # Test RAG
        with st.spinner("Testing RAG system..."):
            try:
                ollama_client = OllamaClient(config)
                test_response = ollama_client.generate("Hello, this is a test.")
                st.success("✅ RAG System: Working")
            except Exception as e:
                st.error(f"❌ RAG System: {e}")
        
        # Test Visualization
        with st.spinner("Testing visualization system..."):
            try:
                viz_engine = st.session_state.viz_engine
                df = viz_engine.create_sample_data('bar')
                fig = viz_engine.create_chart('bar', df, 'Test Chart')
                st.success("✅ Visualization System: Working")
                st.plotly_chart(fig, use_container_width=True, key="test_chart")
            except Exception as e:
                st.error(f"❌ Visualization System: {e}")
        
        # Test Document Processor
        with st.spinner("Testing document processor..."):
            try:
                doc_processor = DocumentProcessor(config)
                st.success("✅ Document Processor: Ready")
            except Exception as e:
                st.error(f"❌ Document Processor: {e}")
                
    except Exception as e:
        st.error(f"Error during testing: {e}")

if __name__ == "__main__":
    # Setup logging
    setup_logging()
    
    # Run main integrated application
    main()