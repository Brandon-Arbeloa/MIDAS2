"""
MIDAS RAG Chat Application
Streamlit chat interface connecting to local Ollama server on Windows 11
"""

import streamlit as st
import ollama
import requests
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Generator
import sys

# Add the current directory to the Python path
sys.path.append(str(Path(__file__).parent))

from document_indexer import DocumentIndexingSystem
from structured_data_indexer import MultiCollectionQdrantIndexer

class OllamaChat:
    """Handles communication with local Ollama server"""
    
    def __init__(self, host: str = "localhost", port: int = 11434):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.client = ollama.Client(host=f"{host}:{port}")
    
    def is_available(self) -> bool:
        """Check if Ollama service is running"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                models_data = response.json()
                return [model['name'] for model in models_data.get('models', [])]
        except requests.exceptions.RequestException:
            pass
        return []
    
    def stream_chat(self, model: str, messages: List[Dict], system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        """Stream chat completion from Ollama"""
        try:
            # Prepare messages with system prompt if provided
            formatted_messages = []
            if system_prompt:
                formatted_messages.append({"role": "system", "content": system_prompt})
            formatted_messages.extend(messages)
            
            # Stream response
            stream = self.client.chat(
                model=model,
                messages=formatted_messages,
                stream=True
            )
            
            for chunk in stream:
                if 'message' in chunk and 'content' in chunk['message']:
                    yield chunk['message']['content']
                    
        except Exception as e:
            yield f"Error communicating with Ollama: {str(e)}"
    
    def chat(self, model: str, messages: List[Dict], system_prompt: Optional[str] = None) -> str:
        """Non-streaming chat completion"""
        try:
            formatted_messages = []
            if system_prompt:
                formatted_messages.append({"role": "system", "content": system_prompt})
            formatted_messages.extend(messages)
            
            response = self.client.chat(
                model=model,
                messages=formatted_messages,
                stream=False
            )
            
            return response['message']['content']
        except Exception as e:
            return f"Error: {str(e)}"

class RAGSystem:
    """Handles document search and retrieval"""
    
    def __init__(self):
        self.doc_indexer = None
        self.structured_indexer = None
        self._initialize_indexers()
    
    def _initialize_indexers(self):
        """Initialize document and structured data indexers"""
        try:
            self.doc_indexer = DocumentIndexingSystem(
                qdrant_host="localhost",
                qdrant_port=6333,
                collection_name="documents",
                chunk_size=800,
                chunk_overlap=100
            )
            
            self.structured_indexer = MultiCollectionQdrantIndexer(
                host="localhost",
                port=6333
            )
        except Exception as e:
            st.error(f"Failed to initialize RAG system: {e}")
    
    def search_documents(self, query: str, limit: int = 5) -> List[Dict]:
        """Search through indexed documents"""
        if not self.doc_indexer:
            return []
        
        try:
            results = self.doc_indexer.search(query, limit=limit, score_threshold=0.6)
            return results or []
        except Exception as e:
            st.error(f"Document search error: {e}")
            return []
    
    def search_structured_data(self, query: str, limit: int = 3) -> List[Dict]:
        """Search through structured data collections"""
        if not self.structured_indexer:
            return []
        
        try:
            results = []
            collections = ["structured_data", "structured_rows", "structured_summaries"]
            
            for collection in collections:
                try:
                    collection_results = self.structured_indexer.search_collection(
                        collection, query, limit=limit//len(collections) + 1, score_threshold=0.6
                    )
                    results.extend(collection_results or [])
                except:
                    continue
            
            # Sort by score and limit
            results.sort(key=lambda x: x.get('score', 0), reverse=True)
            return results[:limit]
        except Exception as e:
            st.error(f"Structured data search error: {e}")
            return []

class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self):
        self.config_dir = Path("C:/MIDAS/config")
        self.config_file = self.config_dir / "chat_config.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.default_config = {
            "default_model": "llama3.2:3b",
            "system_prompt": "You are a helpful AI assistant with access to a knowledge base. Use the provided context to answer questions accurately and concisely.",
            "max_tokens": 2000,
            "temperature": 0.7,
            "enable_rag": True,
            "rag_max_results": 5,
            "theme": "auto"
        }
    
    def load_config(self) -> Dict:
        """Load configuration from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Merge with defaults for any missing keys
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
        except Exception as e:
            st.error(f"Failed to load config: {e}")
        
        return self.default_config.copy()
    
    def save_config(self, config: Dict):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            st.error(f"Failed to save config: {e}")

def initialize_session_state():
    """Initialize Streamlit session state"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "config" not in st.session_state:
        config_manager = ConfigManager()
        st.session_state.config = config_manager.load_config()
    
    if "ollama_chat" not in st.session_state:
        st.session_state.ollama_chat = OllamaChat()
    
    if "rag_system" not in st.session_state:
        st.session_state.rag_system = RAGSystem()
    
    if "available_models" not in st.session_state:
        st.session_state.available_models = []

def format_search_results(results: List[Dict]) -> str:
    """Format search results for context"""
    if not results:
        return ""
    
    context_parts = []
    for i, result in enumerate(results, 1):
        score = result.get('score', 0)
        text = result.get('text', '')
        file_path = result.get('file_path', 'Unknown')
        
        file_name = Path(file_path).name if file_path != 'Unknown' else 'Unknown'
        
        context_parts.append(f"[Source {i} - {file_name} (relevance: {score:.2f})]:\n{text}\n")
    
    return "\n".join(context_parts)

def sidebar_configuration():
    """Render sidebar with configuration options"""
    with st.sidebar:
        st.title("🤖 MIDAS Chat")
        
        # Ollama status
        st.subheader("🔧 Service Status")
        if st.session_state.ollama_chat.is_available():
            st.success("✅ Ollama Connected")
            
            # Get available models
            if st.button("🔄 Refresh Models"):
                st.session_state.available_models = st.session_state.ollama_chat.get_available_models()
            
            if not st.session_state.available_models:
                st.session_state.available_models = st.session_state.ollama_chat.get_available_models()
            
            if st.session_state.available_models:
                selected_model = st.selectbox(
                    "Select Model",
                    st.session_state.available_models,
                    index=0 if st.session_state.config["default_model"] not in st.session_state.available_models 
                    else st.session_state.available_models.index(st.session_state.config["default_model"])
                )
                st.session_state.config["default_model"] = selected_model
            else:
                st.warning("⚠️ No models available")
        else:
            st.error("❌ Ollama Not Connected")
            st.markdown("""
            **To start Ollama:**
            1. Run Setup-Ollama.ps1
            2. Or: `ollama serve` in terminal
            3. Ensure port 11434 is open
            """)
        
        # RAG system status
        st.subheader("📚 RAG System")
        if st.session_state.rag_system.doc_indexer:
            try:
                status = st.session_state.rag_system.doc_indexer.get_system_status()
                if status.get('status') == 'connected':
                    st.success("✅ Document Index Ready")
                    if 'collection' in status:
                        collection = status['collection']
                        st.write(f"📄 Documents: {collection.get('points_count', 0)}")
                else:
                    st.warning("⚠️ Document Index Issues")
            except:
                st.warning("⚠️ Document Index Unavailable")
        else:
            st.error("❌ RAG System Not Initialized")
        
        # Configuration
        st.subheader("⚙️ Settings")
        
        enable_rag = st.checkbox(
            "Enable RAG (Document Search)",
            value=st.session_state.config["enable_rag"]
        )
        st.session_state.config["enable_rag"] = enable_rag
        
        if enable_rag:
            rag_max_results = st.slider(
                "Max Search Results",
                min_value=1,
                max_value=10,
                value=st.session_state.config["rag_max_results"]
            )
            st.session_state.config["rag_max_results"] = rag_max_results
        
        temperature = st.slider(
            "Response Creativity",
            min_value=0.0,
            max_value=2.0,
            value=st.session_state.config["temperature"],
            step=0.1
        )
        st.session_state.config["temperature"] = temperature
        
        # Conversation management
        st.subheader("💬 Conversation")
        
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.rerun()
        
        if st.button("💾 Save Configuration"):
            config_manager = ConfigManager()
            config_manager.save_config(st.session_state.config)
            st.success("Configuration saved!")
        
        # System info
        st.subheader("ℹ️ System Info")
        st.write(f"**Messages:** {len(st.session_state.messages)}")
        st.write(f"**Timestamp:** {datetime.now().strftime('%H:%M:%S')}")

def main():
    """Main application function"""
    st.set_page_config(
        page_title="MIDAS RAG Chat",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize session state
    initialize_session_state()
    
    # Render sidebar
    sidebar_configuration()
    
    # Main chat interface
    st.title("🤖 MIDAS RAG Chat Interface")
    st.markdown("*Chat with your documents using local AI*")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            # Show search results if available
            if message["role"] == "assistant" and "search_results" in message:
                with st.expander("📚 Retrieved Context", expanded=False):
                    results = message["search_results"]
                    for i, result in enumerate(results, 1):
                        score = result.get('score', 0)
                        text = result.get('text', '')
                        file_path = result.get('file_path', 'Unknown')
                        file_name = Path(file_path).name if file_path != 'Unknown' else 'Unknown'
                        
                        st.write(f"**Source {i}:** {file_name} (Score: {score:.3f})")
                        st.write(text[:300] + "..." if len(text) > 300 else text)
                        st.divider()
    
    # Chat input
    if prompt := st.chat_input("Ask a question about your documents..."):
        # Check if Ollama is available
        if not st.session_state.ollama_chat.is_available():
            st.error("❌ Ollama service is not available. Please start Ollama first.")
            st.stop()
        
        # Check if model is selected
        if not st.session_state.available_models:
            st.error("❌ No models available. Please pull a model first using: `ollama pull llama3.2:3b`")
            st.stop()
        
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.write(prompt)
        
        # Generate assistant response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                search_results = []
                context = ""
                
                # Perform RAG search if enabled
                if st.session_state.config["enable_rag"]:
                    doc_results = st.session_state.rag_system.search_documents(
                        prompt, 
                        limit=st.session_state.config["rag_max_results"]
                    )
                    
                    struct_results = st.session_state.rag_system.search_structured_data(
                        prompt, 
                        limit=2
                    )
                    
                    search_results = doc_results + struct_results
                    
                    if search_results:
                        context = format_search_results(search_results)
                
                # Prepare messages for Ollama
                messages = []
                for msg in st.session_state.messages[-5:]:  # Last 5 messages for context
                    if msg["role"] != "system":
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                
                # Create system prompt with context
                system_prompt = st.session_state.config["system_prompt"]
                if context:
                    system_prompt += f"\n\nRelevant information from the knowledge base:\n{context}\n\nPlease use this information to provide accurate and helpful responses."
                
                # Stream response
                response_placeholder = st.empty()
                full_response = ""
                
                try:
                    for chunk in st.session_state.ollama_chat.stream_chat(
                        model=st.session_state.config["default_model"],
                        messages=messages,
                        system_prompt=system_prompt
                    ):
                        full_response += chunk
                        response_placeholder.write(full_response + "▊")
                    
                    response_placeholder.write(full_response)
                    
                except Exception as e:
                    error_msg = f"Error generating response: {str(e)}"
                    response_placeholder.error(error_msg)
                    full_response = error_msg
            
            # Add assistant message with search results
            assistant_message = {
                "role": "assistant", 
                "content": full_response
            }
            
            if search_results:
                assistant_message["search_results"] = search_results
                
                # Show search results
                with st.expander("📚 Retrieved Context", expanded=False):
                    for i, result in enumerate(search_results, 1):
                        score = result.get('score', 0)
                        text = result.get('text', '')
                        file_path = result.get('file_path', 'Unknown')
                        file_name = Path(file_path).name if file_path != 'Unknown' else 'Unknown'
                        
                        st.write(f"**Source {i}:** {file_name} (Score: {score:.3f})")
                        st.write(text[:300] + "..." if len(text) > 300 else text)
                        st.divider()
            
            st.session_state.messages.append(assistant_message)

if __name__ == "__main__":
    main()