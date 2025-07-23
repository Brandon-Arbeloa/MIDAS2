"""
MIDAS Enhanced RAG Chat Application
Advanced Streamlit chat interface with full RAG integration for Windows 11
Enhanced with conversation memory, debugging panel, and Windows optimizations
"""

import streamlit as st
import ollama
import requests
import json
import time
import os
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Generator, Tuple
import sys
import torch
import platform

# Add the current directory to the Python path
sys.path.append(str(Path(__file__).parent))

from document_indexer import DocumentIndexingSystem
from structured_data_indexer import MultiCollectionQdrantIndexer

class WindowsSystemInfo:
    """Detects Windows system capabilities and optimizes accordingly"""
    
    @staticmethod
    def detect_compute_device() -> str:
        """Detect optimal compute device (CUDA/CPU) for Windows"""
        try:
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                memory_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
                return f"CUDA ({device_name}, {memory_gb:.1f}GB)"
            else:
                return "CPU"
        except Exception:
            return "CPU"
    
    @staticmethod
    def get_system_specs() -> Dict:
        """Get Windows system specifications"""
        try:
            import psutil
            cpu_count = psutil.cpu_count()
            memory_gb = psutil.virtual_memory().total / 1024**3
            cpu_freq = psutil.cpu_freq()
            
            return {
                "cpu_cores": cpu_count,
                "memory_gb": round(memory_gb, 1),
                "cpu_freq_ghz": round(cpu_freq.current / 1000, 2) if cpu_freq else "Unknown",
                "platform": platform.platform(),
                "python_version": platform.python_version()
            }
        except ImportError:
            return {
                "cpu_cores": "Unknown",
                "memory_gb": "Unknown", 
                "cpu_freq_ghz": "Unknown",
                "platform": platform.platform(),
                "python_version": platform.python_version()
            }
    
    @staticmethod
    def optimize_for_system(memory_gb: float) -> Dict:
        """Return optimized settings based on system specs"""
        if memory_gb >= 16:
            return {
                "chunk_size": 1000,
                "chunk_overlap": 150,
                "max_search_results": 8,
                "context_window": 4000,
                "concurrent_searches": 3
            }
        elif memory_gb >= 8:
            return {
                "chunk_size": 800,
                "chunk_overlap": 100,
                "max_search_results": 5,
                "context_window": 2048,
                "concurrent_searches": 2
            }
        else:
            return {
                "chunk_size": 600,
                "chunk_overlap": 75,
                "max_search_results": 3,
                "context_window": 1024,
                "concurrent_searches": 1
            }

class ConversationMemory:
    """Manages conversation context and memory across queries"""
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        self.conversations = []
        self.context_summaries = []
        self.relevant_documents = {}
        
    def add_interaction(self, user_query: str, ai_response: str, search_results: List[Dict], timestamp: datetime = None):
        """Add a new interaction to memory"""
        if timestamp is None:
            timestamp = datetime.now()
            
        interaction = {
            "timestamp": timestamp,
            "user_query": user_query,
            "ai_response": ai_response,
            "search_results": search_results,
            "document_sources": [result.get('file_path', '') for result in search_results]
        }
        
        self.conversations.append(interaction)
        
        # Update relevant documents tracking
        for result in search_results:
            file_path = result.get('file_path', '')
            if file_path:
                self.relevant_documents[file_path] = self.relevant_documents.get(file_path, 0) + 1
        
        # Maintain max history
        if len(self.conversations) > self.max_history:
            self.conversations.pop(0)
    
    def get_conversation_context(self, last_n: int = 3) -> str:
        """Get formatted conversation context for prompt"""
        if not self.conversations:
            return ""
        
        recent_conversations = self.conversations[-last_n:]
        context_parts = []
        
        for conv in recent_conversations:
            context_parts.append(f"User: {conv['user_query']}")
            # Only include first 200 chars of AI response for context
            ai_summary = conv['ai_response'][:200] + "..." if len(conv['ai_response']) > 200 else conv['ai_response']
            context_parts.append(f"Assistant: {ai_summary}")
        
        return "\n".join(context_parts)
    
    def get_document_frequency(self) -> List[Tuple[str, int]]:
        """Get documents sorted by frequency of reference"""
        return sorted(self.relevant_documents.items(), key=lambda x: x[1], reverse=True)
    
    def clear_memory(self):
        """Clear all conversation memory"""
        self.conversations = []
        self.context_summaries = []
        self.relevant_documents = {}

class EnhancedRAGSystem:
    """Enhanced RAG system with Windows optimizations and debugging"""
    
    def __init__(self):
        self.doc_indexer = None
        self.structured_indexer = None
        self.system_info = WindowsSystemInfo()
        self.device = self.system_info.detect_compute_device()
        self.specs = self.system_info.get_system_specs()
        self.optimized_settings = self.system_info.optimize_for_system(
            self.specs.get("memory_gb", 8)
        )
        self.search_debug_info = []
        self._initialize_indexers()
    
    def _initialize_indexers(self):
        """Initialize document and structured data indexers with optimized settings"""
        try:
            self.doc_indexer = DocumentIndexingSystem(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="documents",
                chunk_size=self.optimized_settings["chunk_size"],
                chunk_overlap=self.optimized_settings["chunk_overlap"]
            )
            
            self.structured_indexer = MultiCollectionQdrantIndexer(
                host="localhost",
                port=6333
            )
            
            st.success(f"RAG system initialized (Device: {self.device})")
        except Exception as e:
            st.error(f"Failed to initialize RAG system: {e}")
    
    def search_with_debug(self, query: str, limit: int = 5, enable_debug: bool = False) -> Tuple[List[Dict], Dict]:
        """Enhanced search with debugging information"""
        debug_info = {
            "query": query,
            "timestamp": datetime.now(),
            "device": self.device,
            "collections_searched": [],
            "total_results": 0,
            "search_times": {},
            "errors": []
        }
        
        all_results = []
        
        # Search document collection
        if self.doc_indexer:
            try:
                start_time = time.time()
                doc_results = self.doc_indexer.search(query, limit=limit, score_threshold=0.6)
                search_time = time.time() - start_time
                
                debug_info["collections_searched"].append("documents")
                debug_info["search_times"]["documents"] = round(search_time * 1000, 2)
                
                if doc_results:
                    all_results.extend(doc_results)
                    
            except Exception as e:
                debug_info["errors"].append(f"Document search error: {str(e)}")
        
        # Search structured data collections
        if self.structured_indexer:
            structured_collections = ["structured_data", "structured_rows", "structured_summaries"]
            
            for collection in structured_collections:
                try:
                    start_time = time.time()
                    results = self.structured_indexer.search_collection(
                        collection, query, limit=max(1, limit//3), score_threshold=0.6
                    )
                    search_time = time.time() - start_time
                    
                    debug_info["collections_searched"].append(collection)
                    debug_info["search_times"][collection] = round(search_time * 1000, 2)
                    
                    if results:
                        all_results.extend(results)
                        
                except Exception as e:
                    debug_info["errors"].append(f"{collection} search error: {str(e)}")
        
        # Sort by relevance and limit results
        all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        final_results = all_results[:limit]
        
        debug_info["total_results"] = len(final_results)
        
        if enable_debug:
            self.search_debug_info.append(debug_info)
            # Keep only last 10 debug entries
            self.search_debug_info = self.search_debug_info[-10:]
        
        return final_results, debug_info

class WindowsFileHandler:
    """Enhanced Windows file path handling with special character support"""
    
    @staticmethod
    def normalize_windows_path(path_str: str) -> str:
        """Normalize Windows path handling special characters"""
        try:
            path = Path(path_str)
            return str(path.resolve())
        except Exception:
            return path_str
    
    @staticmethod
    def create_clickable_path(file_path: str) -> str:
        """Create clickable file path for Windows Explorer"""
        normalized_path = WindowsFileHandler.normalize_windows_path(file_path)
        if Path(normalized_path).exists():
            return f"file:///{normalized_path.replace(chr(92), '/')}"
        return normalized_path
    
    @staticmethod
    def open_file_explorer(file_path: str) -> bool:
        """Open Windows Explorer to file location"""
        try:
            normalized_path = WindowsFileHandler.normalize_windows_path(file_path)
            if Path(normalized_path).exists():
                subprocess.run(['explorer', '/select,', normalized_path], check=True)
                return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def get_file_icon(file_path: str) -> str:
        """Get appropriate emoji icon for file type"""
        try:
            suffix = Path(file_path).suffix.lower()
            icons = {
                '.txt': '📄', '.md': '📝', '.pdf': '📕', 
                '.docx': '📘', '.doc': '📘', '.csv': '📊', 
                '.xlsx': '📈', '.xls': '📈', '.json': '⚙️',
                '.yaml': '⚙️', '.yml': '⚙️', '.py': '🐍'
            }
            return icons.get(suffix, '📎')
        except Exception:
            return '📎'

def initialize_enhanced_session_state():
    """Initialize enhanced session state with conversation memory"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "conversation_memory" not in st.session_state:
        st.session_state.conversation_memory = ConversationMemory()
    
    if "config" not in st.session_state:
        from chat_app import ConfigManager
        config_manager = ConfigManager()
        st.session_state.config = config_manager.load_config()
    
    if "ollama_chat" not in st.session_state:
        from chat_app import OllamaChat
        st.session_state.ollama_chat = OllamaChat()
    
    if "enhanced_rag_system" not in st.session_state:
        st.session_state.enhanced_rag_system = EnhancedRAGSystem()
    
    if "available_models" not in st.session_state:
        st.session_state.available_models = []
    
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = False
    
    if "show_debug_panel" not in st.session_state:
        st.session_state.show_debug_panel = False

def enhanced_sidebar_configuration():
    """Enhanced sidebar with system info and debugging options"""
    with st.sidebar:
        st.title("🤖 MIDAS Enhanced Chat")
        
        # System Information
        st.subheader("💻 System Status")
        rag_system = st.session_state.enhanced_rag_system
        
        with st.expander("System Specs", expanded=False):
            specs = rag_system.specs
            st.write(f"**Device**: {rag_system.device}")
            st.write(f"**CPU**: {specs.get('cpu_cores', 'Unknown')} cores @ {specs.get('cpu_freq_ghz', 'Unknown')} GHz")
            st.write(f"**RAM**: {specs.get('memory_gb', 'Unknown')} GB")
            st.write(f"**Platform**: {specs.get('platform', 'Unknown')}")
            st.write(f"**Python**: {specs.get('python_version', 'Unknown')}")
        
        # Optimized Settings Display
        st.write("**Optimized Settings**:")
        settings = rag_system.optimized_settings
        st.write(f"• Chunk Size: {settings['chunk_size']}")
        st.write(f"• Max Results: {settings['max_search_results']}")
        st.write(f"• Context Window: {settings['context_window']}")
        
        # Service Status
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
        
        # RAG System status with enhanced info
        if rag_system.doc_indexer:
            try:
                status = rag_system.doc_indexer.get_system_status()
                if status.get('status') == 'connected':
                    st.success("✅ RAG System Ready")
                    if 'collection' in status:
                        collection = status['collection']
                        st.write(f"📄 Documents: {collection.get('points_count', 0)}")
                        
                        # Show document frequency from memory
                        doc_freq = st.session_state.conversation_memory.get_document_frequency()
                        if doc_freq:
                            with st.expander("📊 Most Referenced", expanded=False):
                                for doc_path, freq in doc_freq[:5]:
                                    file_name = Path(doc_path).name if doc_path else "Unknown"
                                    st.write(f"• {file_name} ({freq}x)")
            except Exception as e:
                st.warning(f"⚠️ RAG System Issues: {str(e)[:50]}...")
        
        # Enhanced Configuration
        st.subheader("⚙️ Enhanced Settings")
        
        enable_rag = st.checkbox(
            "Enable RAG Search",
            value=st.session_state.config["enable_rag"]
        )
        st.session_state.config["enable_rag"] = enable_rag
        
        if enable_rag:
            rag_max_results = st.slider(
                "Max Search Results",
                min_value=1,
                max_value=15,
                value=min(st.session_state.config["rag_max_results"], 
                         settings["max_search_results"])
            )
            st.session_state.config["rag_max_results"] = rag_max_results
            
            # Conversation memory settings
            memory_length = st.slider(
                "Conversation Memory",
                min_value=0,
                max_value=10,
                value=3,
                help="Number of previous interactions to include in context"
            )
            st.session_state.config["memory_length"] = memory_length
        
        # Debugging options
        st.subheader("🐛 Debug Options")
        
        st.session_state.debug_mode = st.checkbox(
            "Enable Debug Mode",
            value=st.session_state.debug_mode
        )
        
        st.session_state.show_debug_panel = st.checkbox(
            "Show Debug Panel",
            value=st.session_state.show_debug_panel
        )
        
        temperature = st.slider(
            "Response Creativity",
            min_value=0.0,
            max_value=2.0,
            value=st.session_state.config["temperature"],
            step=0.1
        )
        st.session_state.config["temperature"] = temperature
        
        # Conversation Management
        st.subheader("💬 Conversation")
        
        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.session_state.conversation_memory.clear_memory()
            st.rerun()
        
        if st.button("💾 Save Config"):
            from chat_app import ConfigManager
            config_manager = ConfigManager()
            config_manager.save_config(st.session_state.config)
            st.success("Settings saved!")
        
        # Memory stats
        memory = st.session_state.conversation_memory
        st.write(f"**Memory**: {len(memory.conversations)} interactions")
        st.write(f"**Documents**: {len(memory.relevant_documents)} referenced")

def create_enhanced_search_results_display(results: List[Dict], debug_info: Dict = None):
    """Enhanced display of search results with Windows file handling"""
    if not results:
        return
    
    st.subheader("📚 Retrieved Context")
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["📄 Documents", "🔍 Debug Info"])
    
    with tab1:
        for i, result in enumerate(results, 1):
            score = result.get('score', 0)
            text = result.get('text', '')
            file_path = result.get('file_path', 'Unknown')
            file_name = Path(file_path).name if file_path != 'Unknown' else 'Unknown'
            
            # Create collapsible section for each result
            with st.expander(f"{WindowsFileHandler.get_file_icon(file_path)} {file_name} (Score: {score:.3f})", expanded=i<=2):
                # File path with Windows handling
                if file_path != 'Unknown':
                    normalized_path = WindowsFileHandler.normalize_windows_path(file_path)
                    clickable_url = WindowsFileHandler.create_clickable_path(file_path)
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.code(normalized_path, language=None)
                    with col2:
                        if st.button(f"📂 Open {i}", help="Open in Windows Explorer"):
                            if WindowsFileHandler.open_file_explorer(file_path):
                                st.success("Opened!")
                            else:
                                st.error("Failed to open")
                
                # Text content with proper formatting
                st.markdown("**Content:**")
                st.write(text)
                
                # Additional metadata if available
                if 'metadata' in result:
                    metadata = result['metadata']
                    with st.expander("Metadata", expanded=False):
                        st.json(metadata)
    
    with tab2:
        if debug_info and st.session_state.show_debug_panel:
            st.json(debug_info)

def construct_enhanced_context_prompt(query: str, search_results: List[Dict], conversation_memory: ConversationMemory) -> str:
    """Construct enhanced context-aware prompt with conversation memory"""
    
    # Get conversation context
    memory_length = st.session_state.config.get("memory_length", 3)
    conversation_context = conversation_memory.get_conversation_context(memory_length) if memory_length > 0 else ""
    
    # Format search results with Windows paths
    context_parts = []
    for i, result in enumerate(search_results, 1):
        score = result.get('score', 0)
        text = result.get('text', '')
        file_path = result.get('file_path', 'Unknown')
        
        # Handle Windows path display
        if file_path != 'Unknown':
            display_path = str(Path(file_path).name)
        else:
            display_path = 'Unknown Source'
        
        context_parts.append(
            f"[Source {i}: {display_path} (Relevance: {score:.2f})]:\n{text}\n"
        )
    
    context_text = "\n".join(context_parts) if context_parts else ""
    
    # Construct the full prompt
    base_prompt = st.session_state.config["system_prompt"]
    
    enhanced_prompt = f"""{base_prompt}

CONVERSATION CONTEXT (Previous interactions):
{conversation_context}

CURRENT KNOWLEDGE BASE INFORMATION:
{context_text}

Please use this information to provide accurate, helpful responses. When referencing sources, mention the source file names. If the information comes from previous conversation context, acknowledge that continuity.

Current user query: {query}"""

    return enhanced_prompt

def main():
    """Enhanced main application function"""
    st.set_page_config(
        page_title="MIDAS Enhanced RAG Chat",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    initialize_enhanced_session_state()
    enhanced_sidebar_configuration()
    
    # Main interface
    st.title("🤖 MIDAS Enhanced RAG Chat")
    st.markdown("*Advanced chat with conversation memory, debugging, and Windows optimizations*")
    
    # Show system optimization info
    if st.session_state.debug_mode:
        rag_system = st.session_state.enhanced_rag_system
        st.info(f"🔧 System optimized for {rag_system.specs.get('memory_gb', 'Unknown')} GB RAM | Device: {rag_system.device}")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Enhanced search results display
            if message["role"] == "assistant" and "search_results" in message:
                create_enhanced_search_results_display(
                    message["search_results"], 
                    message.get("debug_info")
                )
    
    # Debug panel at bottom
    if st.session_state.show_debug_panel and st.session_state.enhanced_rag_system.search_debug_info:
        with st.expander("🔍 Search Debug History", expanded=False):
            for i, debug_info in enumerate(reversed(st.session_state.enhanced_rag_system.search_debug_info[-3:])):
                st.write(f"**Search {len(st.session_state.enhanced_rag_system.search_debug_info) - i}**: {debug_info['query']}")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"Collections: {len(debug_info['collections_searched'])}")
                with col2:
                    st.write(f"Results: {debug_info['total_results']}")
                with col3:
                    total_time = sum(debug_info['search_times'].values())
                    st.write(f"Time: {total_time:.2f}ms")
    
    # Enhanced chat input processing
    if prompt := st.chat_input("Ask about your documents with enhanced context..."):
        if not st.session_state.ollama_chat.is_available():
            st.error("❌ Ollama service not available")
            st.stop()
        
        if not st.session_state.available_models:
            st.error("❌ No models available")
            st.stop()
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Generate enhanced assistant response
        with st.chat_message("assistant"):
            with st.spinner("🧠 Thinking with enhanced context..."):
                search_results = []
                debug_info = {}
                
                # Enhanced RAG search with debugging
                if st.session_state.config["enable_rag"]:
                    search_results, debug_info = st.session_state.enhanced_rag_system.search_with_debug(
                        prompt,
                        limit=st.session_state.config["rag_max_results"],
                        enable_debug=st.session_state.debug_mode
                    )
                
                # Construct enhanced context-aware prompt
                enhanced_prompt = construct_enhanced_context_prompt(
                    prompt, 
                    search_results, 
                    st.session_state.conversation_memory
                )
                
                # Prepare messages for Ollama
                messages = [{"role": "user", "content": enhanced_prompt}]
                
                # Stream response
                response_placeholder = st.empty()
                full_response = ""
                
                try:
                    for chunk in st.session_state.ollama_chat.stream_chat(
                        model=st.session_state.config["default_model"],
                        messages=messages
                    ):
                        full_response += chunk
                        response_placeholder.write(full_response + "▊")
                    
                    response_placeholder.write(full_response)
                    
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    response_placeholder.error(error_msg)
                    full_response = error_msg
            
            # Enhanced search results display
            if search_results:
                create_enhanced_search_results_display(search_results, debug_info)
            
            # Add to conversation memory
            st.session_state.conversation_memory.add_interaction(
                prompt, full_response, search_results
            )
            
            # Add assistant message with enhanced data
            assistant_message = {
                "role": "assistant",
                "content": full_response,
                "search_results": search_results,
                "debug_info": debug_info if st.session_state.debug_mode else None
            }
            
            st.session_state.messages.append(assistant_message)

if __name__ == "__main__":
    main()