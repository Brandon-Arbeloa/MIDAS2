"""
MIDAS Simple Visualization Chat Application
Streamlit chat interface with basic visualization using Plotly
Works without heavy dependencies like torch
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import sys
import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import tempfile

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import basic modules that work
from chat_app import ConfigManager, OllamaChat

class SimpleVisualizationDetector:
    """Simple visualization request detection"""
    
    def __init__(self):
        self.viz_keywords = [
            'chart', 'graph', 'plot', 'visualize', 'show me', 'display',
            'histogram', 'bar chart', 'line chart', 'scatter plot', 'pie chart'
        ]
    
    def is_visualization_request(self, text: str) -> bool:
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.viz_keywords)

class SimpleChartGenerator:
    """Simple chart generator using sample data"""
    
    def create_sample_chart(self, chart_type: str = "bar") -> go.Figure:
        """Create a sample chart for demonstration"""
        
        # Sample data
        categories = ['A', 'B', 'C', 'D', 'E']
        values = np.random.randint(10, 100, 5)
        
        if chart_type == "bar":
            fig = px.bar(x=categories, y=values, title="Sample Bar Chart")
        elif chart_type == "line":
            dates = pd.date_range('2024-01-01', periods=10, freq='D')
            values = np.random.randint(50, 150, 10)
            fig = px.line(x=dates, y=values, title="Sample Line Chart")
        elif chart_type == "scatter":
            x_vals = np.random.randint(1, 50, 20)
            y_vals = np.random.randint(1, 50, 20)
            fig = px.scatter(x=x_vals, y=y_vals, title="Sample Scatter Plot")
        elif chart_type == "pie":
            fig = px.pie(values=values, names=categories, title="Sample Pie Chart")
        else:
            fig = px.bar(x=categories, y=values, title="Default Chart")
        
        # Windows-compatible styling
        fig.update_layout(
            font=dict(family="Segoe UI, Arial, sans-serif", size=12),
            plot_bgcolor='white',
            paper_bgcolor='white',
            title_font_size=16
        )
        
        return fig

def initialize_simple_session_state():
    """Initialize simple session state"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "config" not in st.session_state:
        config_manager = ConfigManager()
        st.session_state.config = config_manager.load_config()
    
    if "ollama_chat" not in st.session_state:
        st.session_state.ollama_chat = OllamaChat()
    
    if "viz_detector" not in st.session_state:
        st.session_state.viz_detector = SimpleVisualizationDetector()
    
    if "chart_generator" not in st.session_state:
        st.session_state.chart_generator = SimpleChartGenerator()
    
    if "available_models" not in st.session_state:
        st.session_state.available_models = []

def render_simple_sidebar():
    """Render simplified sidebar"""
    with st.sidebar:
        st.title("📊 MIDAS Simple Visualization")
        
        # System Status
        st.subheader("🔧 Services")
        
        # Ollama status
        if st.session_state.ollama_chat.is_available():
            st.success("✅ Ollama Connected")
            
            if st.button("🔄 Refresh Models"):
                st.session_state.available_models = st.session_state.ollama_chat.get_available_models()
            
            if not st.session_state.available_models:
                st.session_state.available_models = st.session_state.ollama_chat.get_available_models()
            
            if st.session_state.available_models:
                selected_model = st.selectbox(
                    "Model",
                    st.session_state.available_models,
                    index=0 if st.session_state.config["default_model"] not in st.session_state.available_models 
                    else st.session_state.available_models.index(st.session_state.config["default_model"])
                )
                st.session_state.config["default_model"] = selected_model
        else:
            st.error("❌ Ollama Disconnected")
            st.info("Visualization will work with sample data")
        
        # Settings
        st.subheader("⚙️ Settings")
        
        auto_viz = st.checkbox(
            "Auto-detect visualizations",
            value=True,
            help="Automatically create charts when visualization is requested"
        )
        st.session_state.config["auto_viz"] = auto_viz
        
        chart_style = st.selectbox(
            "Chart Style",
            ["default", "professional", "colorful"],
            index=0
        )
        st.session_state.config["chart_style"] = chart_style
        
        # Clear chat
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()
        
        # Help
        st.subheader("💡 Try These Commands")
        st.info("""
        • "Show me a bar chart"
        • "Create a line graph"
        • "Make a scatter plot"
        • "Generate a pie chart"
        • "Display a histogram"
        """)

def process_simple_chat_message(prompt: str):
    """Process chat message with simple visualization"""
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.write(prompt)
    
    # Check for visualization request
    is_viz_request = st.session_state.viz_detector.is_visualization_request(prompt)
    
    with st.chat_message("assistant"):
        if is_viz_request and st.session_state.config.get("auto_viz", True):
            # Create visualization
            st.info("🎨 Creating visualization based on your request...")
            
            # Determine chart type
            chart_type = "bar"
            prompt_lower = prompt.lower()
            if "line" in prompt_lower:
                chart_type = "line"
            elif "scatter" in prompt_lower:
                chart_type = "scatter"
            elif "pie" in prompt_lower:
                chart_type = "pie"
            elif "histogram" in prompt_lower:
                chart_type = "bar"
            
            # Generate sample chart
            fig = st.session_state.chart_generator.create_sample_chart(chart_type)
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{len(st.session_state.messages)}")
            
            response = f"I've created a sample {chart_type} chart for you! In a full system with data connections, this would show your actual data. Try uploading a CSV file or connecting to a database to see real data visualizations."
            
            # Add assistant message
            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
                "chart_type": chart_type,
                "has_chart": True
            })
            
            st.write(response)
            
        else:
            # Regular text response
            if st.session_state.ollama_chat.is_available():
                try:
                    response_placeholder = st.empty()
                    full_response = ""
                    
                    # Stream response from Ollama
                    for chunk in st.session_state.ollama_chat.stream_chat(
                        model=st.session_state.config["default_model"],
                        messages=[{"role": "user", "content": prompt}]
                    ):
                        full_response += chunk
                        response_placeholder.write(full_response + "▊")
                    
                    response_placeholder.write(full_response)
                    
                except Exception as e:
                    full_response = f"I'm a MIDAS visualization system. I can help you create charts and graphs. Try asking me to 'show you a bar chart' or 'create a line graph'!"
                    st.write(full_response)
            else:
                full_response = "I'm a MIDAS visualization system. I can help you create charts and graphs. Try asking me to 'show you a bar chart' or 'create a line graph'!"
                st.write(full_response)
            
            # Add assistant message
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response
            })

def main():
    """Main simple visualization app"""
    st.set_page_config(
        page_title="MIDAS Simple Visualization",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_simple_session_state()
    
    # Sidebar
    render_simple_sidebar()
    
    # Main interface
    st.title("📊 MIDAS Simple Visualization Chat")
    st.markdown("*Create charts and visualizations with simple commands*")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Show chart if it was generated
            if message["role"] == "assistant" and message.get("has_chart"):
                chart_type = message.get("chart_type", "bar")
                fig = st.session_state.chart_generator.create_sample_chart(chart_type)
                st.plotly_chart(fig, use_container_width=True, key=f"replay_chart_{hash(message['content'])}")
    
    # Chat input
    if prompt := st.chat_input("Ask me to create a chart or ask any question..."):
        process_simple_chat_message(prompt)

if __name__ == "__main__":
    main()