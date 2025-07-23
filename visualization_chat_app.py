"""
MIDAS Visualization-Enhanced RAG Chat Application
Streamlit chat interface with intelligent data visualization using Plotly
Includes natural language chart requests and Windows-native data processing
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import our enhanced modules
from enhanced_chat_app import (
    initialize_enhanced_session_state,
    enhanced_sidebar_configuration,
    create_enhanced_search_results_display,
    construct_enhanced_context_prompt,
    WindowsSystemInfo,
    ConversationMemory,
    EnhancedRAGSystem,
    WindowsFileHandler
)

from data_visualization_engine import (
    DataVisualizationEngine,
    WindowsDataLoader,
    PlotlyChartGenerator
)

from chat_app import OllamaChat, ConfigManager

class VisualizationRequestDetector:
    """Detects if user request is asking for data visualization"""
    
    def __init__(self):
        self.visualization_keywords = [
            'chart', 'graph', 'plot', 'visualize', 'show me', 'display',
            'histogram', 'bar chart', 'line chart', 'scatter plot', 'pie chart',
            'heatmap', 'box plot', 'trend', 'distribution', 'correlation',
            'compare', 'analysis', 'breakdown', 'over time', 'by category'
        ]
        
        self.data_keywords = [
            'data', 'dataset', 'table', 'csv', 'excel', 'spreadsheet',
            'numbers', 'statistics', 'metrics', 'values', 'records'
        ]
    
    def is_visualization_request(self, text: str) -> bool:
        """Check if text contains visualization intent"""
        text_lower = text.lower()
        
        # Check for direct visualization keywords
        has_viz_keyword = any(keyword in text_lower for keyword in self.visualization_keywords)
        
        # Check for data + action patterns
        has_data_keyword = any(keyword in text_lower for keyword in self.data_keywords)
        action_words = ['show', 'create', 'make', 'generate', 'build', 'draw']
        has_action = any(action in text_lower for action in action_words)
        
        return has_viz_keyword or (has_data_keyword and has_action)
    
    def extract_visualization_intent(self, text: str) -> Dict[str, Any]:
        """Extract detailed visualization intent"""
        return {
            'is_visualization': self.is_visualization_request(text),
            'confidence': self._calculate_confidence(text),
            'suggested_approach': 'automatic' if self.is_visualization_request(text) else 'text_only'
        }
    
    def _calculate_confidence(self, text: str) -> float:
        """Calculate confidence score for visualization intent"""
        text_lower = text.lower()
        score = 0.0
        
        # Count visualization keywords
        viz_matches = sum(1 for keyword in self.visualization_keywords if keyword in text_lower)
        score += viz_matches * 0.3
        
        # Count data keywords
        data_matches = sum(1 for keyword in self.data_keywords if keyword in text_lower)
        score += data_matches * 0.2
        
        # Boost for specific chart types
        chart_types = ['bar', 'line', 'scatter', 'pie', 'heatmap', 'histogram', 'box']
        chart_matches = sum(1 for chart_type in chart_types if chart_type in text_lower)
        score += chart_matches * 0.5
        
        return min(1.0, score)

def initialize_visualization_session_state():
    """Initialize session state for visualization features"""
    # Initialize enhanced session state first
    initialize_enhanced_session_state()
    
    # Add visualization-specific state
    if "visualization_engine" not in st.session_state:
        st.session_state.visualization_engine = DataVisualizationEngine(
            qdrant_indexer=st.session_state.enhanced_rag_system.structured_indexer,
            ollama_client=st.session_state.ollama_chat
        )
    
    if "visualization_detector" not in st.session_state:
        st.session_state.visualization_detector = VisualizationRequestDetector()
    
    if "visualization_history" not in st.session_state:
        st.session_state.visualization_history = []
    
    if "show_data_panel" not in st.session_state:
        st.session_state.show_data_panel = False

def enhanced_visualization_sidebar():
    """Enhanced sidebar with visualization controls"""
    with st.sidebar:
        st.title("🤖 MIDAS Visualization Chat")
        
        # System Information (from enhanced_chat_app)
        st.subheader("💻 System Status")
        rag_system = st.session_state.enhanced_rag_system
        
        with st.expander("System Specs", expanded=False):
            specs = rag_system.specs
            st.write(f"**Device**: {rag_system.device}")
            st.write(f"**CPU**: {specs.get('cpu_cores', 'Unknown')} cores")
            st.write(f"**RAM**: {specs.get('memory_gb', 'Unknown')} GB")
        
        # Visualization-specific settings
        st.subheader("📊 Visualization Settings")
        
        # Auto-detection toggle
        auto_detect_viz = st.checkbox(
            "Auto-detect visualization requests",
            value=True,
            help="Automatically generate charts when visualization intent is detected"
        )
        st.session_state.config["auto_detect_visualization"] = auto_detect_viz
        
        # Chart style preferences
        chart_style = st.selectbox(
            "Chart Style",
            ["professional", "vibrant", "pastel", "default"],
            index=0
        )
        st.session_state.config["chart_style"] = chart_style
        
        # Data panel toggle
        st.session_state.show_data_panel = st.checkbox(
            "Show Data Panel",
            value=st.session_state.show_data_panel,
            help="Show data analysis and preview alongside charts"
        )
        
        # Services status
        st.subheader("🔧 Services")
        
        # Ollama status
        if st.session_state.ollama_chat.is_available():
            st.success("✅ Ollama Connected")
            
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
        
        # Enhanced RAG status
        if rag_system.doc_indexer:
            try:
                status = rag_system.doc_indexer.get_system_status()
                if status.get('status') == 'connected':
                    st.success("✅ RAG System Ready")
                    
                    # Show visualization history
                    if st.session_state.visualization_history:
                        with st.expander("📈 Recent Visualizations", expanded=False):
                            for i, viz in enumerate(reversed(st.session_state.visualization_history[-5:])):
                                st.write(f"• {viz['request'][:50]}...")
            except Exception:
                st.warning("⚠️ RAG System Issues")
        
        # Configuration
        st.subheader("⚙️ Settings")
        
        enable_rag = st.checkbox(
            "Enable RAG Search",
            value=st.session_state.config.get("enable_rag", True)
        )
        st.session_state.config["enable_rag"] = enable_rag
        
        if enable_rag:
            rag_max_results = st.slider(
                "Max Search Results",
                min_value=1,
                max_value=15,
                value=st.session_state.config.get("rag_max_results", 5)
            )
            st.session_state.config["rag_max_results"] = rag_max_results
        
        temperature = st.slider(
            "Response Creativity",
            min_value=0.0,
            max_value=2.0,
            value=st.session_state.config.get("temperature", 0.7),
            step=0.1
        )
        st.session_state.config["temperature"] = temperature
        
        # Conversation Management
        st.subheader("💬 Management")
        
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.session_state.conversation_memory.clear_memory()
            st.session_state.visualization_history = []
            st.rerun()
        
        if st.button("💾 Save Config"):
            config_manager = ConfigManager()
            config_manager.save_config(st.session_state.config)
            st.success("Settings saved!")

def display_visualization_result(viz_result: Dict[str, Any], query: str):
    """Display visualization result with data panels"""
    if not viz_result['success']:
        st.error(f"❌ Visualization Error: {viz_result['error']}")
        return
    
    # Main chart display
    st.plotly_chart(
        viz_result['chart'], 
        use_container_width=True, 
        key=f"chart_{len(st.session_state.visualization_history)}"
    )
    
    # Data analysis panel
    if st.session_state.show_data_panel:
        with st.expander("📊 Data Analysis", expanded=False):
            dataset_info = viz_result['dataset_info']
            analysis = dataset_info['analysis']
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Dataset Info:**")
                st.write(f"• File: {Path(dataset_info['file_path']).name}")
                st.write(f"• Shape: {analysis['shape'][0]:,} rows × {analysis['shape'][1]} columns")
                st.write(f"• Numeric columns: {len(analysis['numeric_columns'])}")
                st.write(f"• Categorical columns: {len(analysis['categorical_columns'])}")
            
            with col2:
                st.write("**Data Quality:**")
                quality = analysis['data_quality']
                null_count = sum(quality['null_counts'].values())
                st.write(f"• Null values: {null_count:,}")
                st.write(f"• Duplicate rows: {quality['duplicate_rows']:,}")
                
                # Memory usage in MB
                memory_mb = quality['memory_usage'] / 1024 / 1024
                st.write(f"• Memory: {memory_mb:.1f} MB")
            
            # Show data preview
            if st.checkbox("Show Data Preview", key=f"preview_{len(st.session_state.visualization_history)}"):
                st.dataframe(
                    dataset_info['dataframe'].head(10), 
                    use_container_width=True
                )
            
            # LLM insights if available
            if 'llm_insights' in analysis:
                st.write("**AI Analysis:**")
                st.write(analysis['llm_insights'])
    
    # Chart suggestions
    suggestions = viz_result.get('suggestions', [])
    if suggestions:
        with st.expander("💡 Other Chart Suggestions", expanded=False):
            for suggestion in suggestions[:5]:
                chart_type = suggestion['type'].title()
                title = suggestion.get('title', f'{chart_type} Chart')
                priority = suggestion.get('priority', 'medium')
                
                priority_icon = {"high": "🔥", "medium": "⭐", "low": "💡"}.get(priority, "💡")
                st.write(f"{priority_icon} **{chart_type}**: {title}")

def process_chat_with_visualization(prompt: str):
    """Process chat message with potential visualization generation"""
    # Detect visualization intent
    viz_intent = st.session_state.visualization_detector.extract_visualization_intent(prompt)
    
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.write(prompt)
    
    # Generate response
    with st.chat_message("assistant"):
        if viz_intent['is_visualization'] and st.session_state.config.get("auto_detect_visualization", True):
            # Handle visualization request
            with st.spinner("🎨 Generating visualization..."):
                # Try to create visualization first
                viz_result = st.session_state.visualization_engine.process_visualization_request(prompt)
                
                if viz_result['success']:
                    st.success("📊 Generated visualization based on your request!")
                    display_visualization_result(viz_result, prompt)
                    
                    # Add to visualization history
                    st.session_state.visualization_history.append({
                        'request': prompt,
                        'timestamp': datetime.now(),
                        'chart_type': viz_result['chart_config']['type'],
                        'success': True
                    })
                    
                    # Generate explanatory text about the visualization
                    explanation_prompt = f"""
                    I created a {viz_result['chart_config']['type']} chart based on your request: "{prompt}"
                    
                    The visualization shows data from {Path(viz_result['dataset_info']['file_path']).name} with {viz_result['dataset_info']['analysis']['shape'][0]} rows.
                    
                    Please provide a brief explanation of what this chart shows and any insights that might be relevant.
                    """
                    
                    try:
                        explanation = st.session_state.ollama_chat.chat(
                            model=st.session_state.config["default_model"],
                            messages=[{"role": "user", "content": explanation_prompt}]
                        )
                        st.write(explanation)
                        
                        # Add assistant message with both chart and explanation
                        assistant_message = {
                            "role": "assistant",
                            "content": explanation,
                            "visualization_result": viz_result,
                            "chart_generated": True
                        }
                        st.session_state.messages.append(assistant_message)
                        
                    except Exception as e:
                        st.write("Chart generated successfully. Use the data panel below for more details.")
                        assistant_message = {
                            "role": "assistant", 
                            "content": "Chart generated successfully.",
                            "visualization_result": viz_result,
                            "chart_generated": True
                        }
                        st.session_state.messages.append(assistant_message)
                    
                else:
                    # Visualization failed, fall back to regular RAG
                    st.warning(f"⚠️ Could not generate visualization: {viz_result['error']}")
                    st.info("💭 Providing text-based response instead...")
                    
                    process_regular_rag_response(prompt)
        else:
            # Regular RAG response
            process_regular_rag_response(prompt)

def process_regular_rag_response(prompt: str):
    """Process regular RAG response without visualization"""
    with st.spinner("🧠 Thinking..."):
        search_results = []
        debug_info = {}
        
        # Enhanced RAG search
        if st.session_state.config.get("enable_rag", True):
            search_results, debug_info = st.session_state.enhanced_rag_system.search_with_debug(
                prompt,
                limit=st.session_state.config.get("rag_max_results", 5),
                enable_debug=st.session_state.debug_mode
            )
        
        # Construct enhanced context-aware prompt
        enhanced_prompt = construct_enhanced_context_prompt(
            prompt, 
            search_results, 
            st.session_state.conversation_memory
        )
        
        # Generate response
        response_placeholder = st.empty()
        full_response = ""
        
        try:
            for chunk in st.session_state.ollama_chat.stream_chat(
                model=st.session_state.config["default_model"],
                messages=[{"role": "user", "content": enhanced_prompt}]
            ):
                full_response += chunk
                response_placeholder.write(full_response + "▊")
            
            response_placeholder.write(full_response)
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            response_placeholder.error(error_msg)
            full_response = error_msg
    
    # Show search results if available
    if search_results:
        create_enhanced_search_results_display(search_results, debug_info)
    
    # Add to conversation memory
    st.session_state.conversation_memory.add_interaction(
        prompt, full_response, search_results
    )
    
    # Add assistant message
    assistant_message = {
        "role": "assistant",
        "content": full_response,
        "search_results": search_results,
        "debug_info": debug_info if st.session_state.debug_mode else None
    }
    
    st.session_state.messages.append(assistant_message)

def display_chat_messages():
    """Display chat messages with visualization support"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Display visualization if present
            if message["role"] == "assistant" and message.get("chart_generated"):
                viz_result = message.get("visualization_result")
                if viz_result:
                    display_visualization_result(viz_result, "Previous request")
            
            # Display regular search results
            elif message["role"] == "assistant" and "search_results" in message:
                create_enhanced_search_results_display(
                    message["search_results"], 
                    message.get("debug_info")
                )

def main():
    """Main visualization-enhanced chat application"""
    st.set_page_config(
        page_title="MIDAS Visualization Chat",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_visualization_session_state()
    
    # Sidebar
    enhanced_visualization_sidebar()
    
    # Main interface
    st.title("📊 MIDAS Visualization Chat")
    st.markdown("*Chat with your data and get instant visualizations*")
    
    # Quick help
    with st.expander("💡 How to use visualization features", expanded=False):
        st.markdown("""
        **Examples of visualization requests:**
        - "Show me a bar chart of sales by region"
        - "Create a line chart showing trends over time"  
        - "Plot a scatter plot comparing price vs quantity"
        - "Generate a histogram of customer ages"
        - "Show correlation between different metrics"
        
        **Supported chart types:** Bar, Line, Scatter, Pie, Histogram, Heatmap, Box Plot
        
        **Data sources:** Automatically searches your indexed CSV and Excel files
        """)
    
    # Display chat messages
    display_chat_messages()
    
    # Chat input
    if prompt := st.chat_input("Ask about your data or request visualizations..."):
        if not st.session_state.ollama_chat.is_available():
            st.error("❌ Ollama service not available")
            st.stop()
        
        if not st.session_state.available_models:
            st.error("❌ No models available")
            st.stop()
        
        # Process the chat message
        process_chat_with_visualization(prompt)

if __name__ == "__main__":
    main()