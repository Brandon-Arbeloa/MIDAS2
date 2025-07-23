"""
MIDAS Standalone Visualization Application
Independent Streamlit app with Plotly visualizations - no external dependencies
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import io
import tempfile

class StandaloneVisualizationEngine:
    """Self-contained visualization engine"""
    
    def __init__(self):
        self.viz_keywords = [
            'chart', 'graph', 'plot', 'visualize', 'show me', 'display',
            'histogram', 'bar chart', 'line chart', 'scatter plot', 'pie chart',
            'heatmap', 'box plot', 'area chart'
        ]
        
        self.chart_types = {
            'bar': ['bar', 'column', 'bars'],
            'line': ['line', 'trend', 'time series', 'over time'],
            'scatter': ['scatter', 'correlation', 'relationship', 'vs', 'versus'],
            'pie': ['pie', 'proportion', 'percentage', 'share'],
            'histogram': ['histogram', 'distribution', 'frequency'],
            'heatmap': ['heatmap', 'correlation matrix', 'intensity'],
            'box': ['box plot', 'quartiles', 'outliers']
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
    
    def create_sample_data(self, chart_type: str) -> pd.DataFrame:
        """Generate appropriate sample data for chart type"""
        np.random.seed(42)  # For consistent results
        
        if chart_type == 'line':
            dates = pd.date_range('2024-01-01', periods=12, freq='M')
            values = np.random.randint(50, 200, 12)
            return pd.DataFrame({'Date': dates, 'Value': values})
            
        elif chart_type == 'scatter':
            x = np.random.randint(1, 100, 30)
            y = x * 2 + np.random.randint(-20, 20, 30)
            categories = np.random.choice(['A', 'B', 'C'], 30)
            return pd.DataFrame({'X': x, 'Y': y, 'Category': categories})
            
        elif chart_type == 'pie':
            categories = ['Product A', 'Product B', 'Product C', 'Product D']
            values = [30, 25, 20, 25]
            return pd.DataFrame({'Category': categories, 'Value': values})
            
        elif chart_type == 'histogram':
            values = np.random.normal(50, 15, 200)
            return pd.DataFrame({'Values': values})
            
        elif chart_type == 'heatmap':
            data = np.random.rand(10, 10)
            return pd.DataFrame(data)
            
        else:  # bar chart
            categories = ['Q1', 'Q2', 'Q3', 'Q4']
            values = np.random.randint(20, 100, 4)
            return pd.DataFrame({'Quarter': categories, 'Sales': values})
    
    def create_chart(self, chart_type: str, df: pd.DataFrame, title: str = None) -> go.Figure:
        """Create Plotly chart based on type and data"""
        
        if title is None:
            title = f"Sample {chart_type.title()} Chart"
        
        if chart_type == 'bar':
            fig = px.bar(df, x=df.columns[0], y=df.columns[1], title=title)
            
        elif chart_type == 'line':
            fig = px.line(df, x=df.columns[0], y=df.columns[1], title=title)
            
        elif chart_type == 'scatter':
            color_col = df.columns[2] if len(df.columns) > 2 else None
            fig = px.scatter(df, x=df.columns[0], y=df.columns[1], 
                           color=color_col, title=title)
            
        elif chart_type == 'pie':
            fig = px.pie(df, values=df.columns[1], names=df.columns[0], title=title)
            
        elif chart_type == 'histogram':
            fig = px.histogram(df, x=df.columns[0], title=title)
            
        elif chart_type == 'heatmap':
            fig = px.imshow(df, title=title, aspect="auto")
            
        else:
            # Default to bar chart
            fig = px.bar(df, x=df.columns[0], y=df.columns[1], title=title)
        
        # Apply consistent styling
        fig.update_layout(
            font=dict(family="Segoe UI, Arial, sans-serif", size=12),
            plot_bgcolor='white',
            paper_bgcolor='white',
            title_font_size=16,
            showlegend=True if chart_type in ['scatter', 'pie'] else False,
            height=500
        )
        
        return fig

def initialize_session_state():
    """Initialize session state variables"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "viz_engine" not in st.session_state:
        st.session_state.viz_engine = StandaloneVisualizationEngine()
    
    if "chart_history" not in st.session_state:
        st.session_state.chart_history = []

def render_sidebar():
    """Render application sidebar"""
    with st.sidebar:
        st.title("📊 MIDAS Standalone Viz")
        
        st.success("✅ Ready to create charts!")
        
        # Settings
        st.subheader("⚙️ Settings")
        
        auto_detect = st.checkbox(
            "Auto-detect chart requests",
            value=True,
            help="Automatically create charts when you ask for them"
        )
        
        chart_style = st.selectbox(
            "Chart Color Scheme",
            ["plotly", "viridis", "plasma", "inferno", "magma"],
            index=0
        )
        
        # Store in session state
        st.session_state.auto_detect = auto_detect
        st.session_state.chart_style = chart_style
        
        st.subheader("💡 Try These Commands")
        st.markdown("""
        **Chart Requests:**
        - "Show me a bar chart"
        - "Create a line graph"  
        - "Make a scatter plot"
        - "Generate a pie chart"
        - "Display a histogram"
        - "Show me a heatmap"
        
        **With Data:**
        - Upload CSV files
        - Paste data in chat
        - Use sample data
        """)
        
        # Chart history
        if st.session_state.chart_history:
            st.subheader("📈 Recent Charts")
            for i, chart_info in enumerate(reversed(st.session_state.chart_history[-3:])):
                st.write(f"• {chart_info['type'].title()}: {chart_info['timestamp'][:16]}")
        
        # Clear data
        if st.button("🗑️ Clear All"):
            st.session_state.messages = []
            st.session_state.chart_history = []
            st.rerun()

def process_chat_message(prompt: str):
    """Process user message and generate response"""
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.write(prompt)
    
    # Process the message
    viz_engine = st.session_state.viz_engine
    is_viz_request = viz_engine.is_visualization_request(prompt)
    
    with st.chat_message("assistant"):
        if is_viz_request and st.session_state.get("auto_detect", True):
            # Handle visualization request
            chart_type = viz_engine.detect_chart_type(prompt)
            
            with st.spinner(f"Creating {chart_type} chart..."):
                # Generate sample data
                df = viz_engine.create_sample_data(chart_type)
                
                # Create chart
                title = f"{chart_type.title()} Chart - Sample Data"
                fig = viz_engine.create_chart(chart_type, df, title)
                
                # Display chart
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{len(st.session_state.messages)}")
                
                # Response text
                response = f"""
I've created a sample {chart_type} chart for you! 

**Chart Details:**
- Type: {chart_type.title()}
- Data Points: {len(df)} rows
- Columns: {list(df.columns)}

**To use with your own data:**
1. Upload a CSV file using the file uploader below
2. Or paste your data in the chat
3. Or describe what kind of data you want to visualize

This chart uses sample data for demonstration. In a full system, it would connect to your actual data sources.
                """
                
                st.success("✅ Chart created successfully!")
                st.write(response)
                
                # Add to history
                st.session_state.chart_history.append({
                    'type': chart_type,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'data_rows': len(df)
                })
                
                # Store message
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "chart_type": chart_type,
                    "has_chart": True
                })
        
        else:
            # Regular text response
            if "help" in prompt.lower():
                response = """
I'm your MIDAS visualization assistant! I can help you create interactive charts and graphs.

**What I can do:**
• Create bar charts, line graphs, scatter plots, pie charts, histograms, and heatmaps
• Process CSV data uploads
• Generate sample data for testing
• Provide interactive, downloadable charts

**How to use me:**
• Just ask! "Show me a bar chart" or "Create a line graph"
• Upload CSV files for real data visualization
• Ask questions about data visualization best practices

**Example requests:**
• "Create a sales chart by quarter"
• "Show me customer data as a scatter plot"
• "Make a pie chart of product categories"

What would you like to visualize today?
                """
            elif "data" in prompt.lower():
                response = """
I can work with various types of data:

**Sample Data (built-in):**
• Sales data by quarter
• Time series data
• Customer analytics
• Product categories

**Your Data:**
• Upload CSV files using the file uploader
• Paste data directly in our conversation
• Describe your data and I'll create sample data

**Supported Formats:**
• CSV files with headers
• Tab-separated values
• JSON data
• Simple text tables

Would you like me to create a chart with sample data, or do you have specific data to visualize?
                """
            else:
                response = """
Hello! I'm your MIDAS data visualization assistant. I can help you create beautiful, interactive charts and graphs.

**Quick Start:**
• Say "show me a bar chart" to see a sample visualization
• Type "help" for more detailed instructions
• Upload a CSV file to visualize your own data

**Popular Chart Types:**
• Bar charts for comparisons
• Line graphs for trends over time
• Scatter plots for relationships
• Pie charts for proportions
• Histograms for distributions

What kind of visualization would you like to create?
                """
            
            st.write(response)
            
            # Store message
            st.session_state.messages.append({
                "role": "assistant",
                "content": response
            })

def render_file_uploader():
    """Render CSV file upload section"""
    st.subheader("📁 Upload Your Data")
    
    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=['csv'],
        help="Upload a CSV file to create visualizations with your data"
    )
    
    if uploaded_file is not None:
        try:
            # Read CSV
            df = pd.read_csv(uploaded_file)
            
            st.success(f"✅ File uploaded: {uploaded_file.name}")
            st.write(f"**Shape:** {df.shape[0]} rows × {df.shape[1]} columns")
            st.write(f"**Columns:** {list(df.columns)}")
            
            # Show preview
            with st.expander("👁️ Data Preview", expanded=False):
                st.dataframe(df.head(10))
            
            # Quick visualization options
            st.write("**Quick Charts:**")
            col1, col2, col3, col4 = st.columns(4)
            
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            categorical_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
            
            if numeric_cols and categorical_cols:
                with col1:
                    if st.button("📊 Bar Chart", key="quick_bar"):
                        fig = px.bar(df, x=categorical_cols[0], y=numeric_cols[0],
                                   title=f"{numeric_cols[0]} by {categorical_cols[0]}")
                        st.plotly_chart(fig, use_container_width=True, key="uploaded_bar")
                
                with col2:
                    if st.button("📈 Line Chart", key="quick_line"):
                        fig = px.line(df, x=categorical_cols[0], y=numeric_cols[0],
                                    title=f"{numeric_cols[0]} Trend")
                        st.plotly_chart(fig, use_container_width=True, key="uploaded_line")
            
            if len(numeric_cols) >= 2:
                with col3:
                    if st.button("🔵 Scatter Plot", key="quick_scatter"):
                        color_col = categorical_cols[0] if categorical_cols else None
                        fig = px.scatter(df, x=numeric_cols[0], y=numeric_cols[1], 
                                       color=color_col, title=f"{numeric_cols[0]} vs {numeric_cols[1]}")
                        st.plotly_chart(fig, use_container_width=True, key="uploaded_scatter")
            
            if categorical_cols and numeric_cols:
                with col4:
                    if st.button("🥧 Pie Chart", key="quick_pie"):
                        # Aggregate data for pie chart
                        pie_data = df.groupby(categorical_cols[0])[numeric_cols[0]].sum().reset_index()
                        fig = px.pie(pie_data, values=numeric_cols[0], names=categorical_cols[0],
                                   title=f"{numeric_cols[0]} Distribution by {categorical_cols[0]}")
                        st.plotly_chart(fig, use_container_width=True, key="uploaded_pie")
            
        except Exception as e:
            st.error(f"❌ Error reading file: {str(e)}")
            st.info("Please make sure your file is a valid CSV with headers.")

def main():
    """Main application function"""
    st.set_page_config(
        page_title="MIDAS Visualization",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar
    render_sidebar()
    
    # Main interface
    st.title("📊 MIDAS Standalone Visualization")
    st.markdown("*Create interactive charts and graphs with simple commands*")
    
    # Show current status
    st.info("✅ **Ready to create visualizations!** Ask me to create any type of chart, or upload your CSV data.")
    
    # File uploader
    render_file_uploader()
    
    st.markdown("---")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Replay charts if they exist
            if message["role"] == "assistant" and message.get("has_chart"):
                chart_type = message.get("chart_type", "bar")
                df = st.session_state.viz_engine.create_sample_data(chart_type)
                fig = st.session_state.viz_engine.create_chart(chart_type, df)
                st.plotly_chart(fig, use_container_width=True, key=f"replay_{hash(message['content'])}")
    
    # Chat input
    if prompt := st.chat_input("Ask me to create a chart, upload data, or ask for help..."):
        process_chat_message(prompt)

if __name__ == "__main__":
    main()