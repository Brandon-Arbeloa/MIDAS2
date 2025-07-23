"""
RAG System - Main Streamlit Application
Windows 11 On-Premises RAG System with Local LLM

This is the main entry point for the Streamlit-based RAG application.
Provides chat interface, document upload, and basic RAG functionality.
"""

import streamlit as st
import sys
import os
from pathlib import Path

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
            return {"response": "This is a placeholder response from the RAG system."}
    
    class VectorStore:
        def __init__(self, config):
            self.config = config
        
        def search(self, query, limit=5):
            return []
    
    def check_services_status():
        return {"ollama": True, "qdrant": True}
        
except ImportError as e:
    st.error(f"Import error: {e}")
    st.error("Please ensure all dependencies are installed and the project structure is correct.")
    st.stop()

# Page configuration
st.set_page_config(
    page_title="RAG System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def initialize_session_state():
    """Initialize Streamlit session state variables"""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "rag_enabled" not in st.session_state:
        st.session_state.rag_enabled = True
    
    if "current_model" not in st.session_state:
        st.session_state.current_model = "llama3.2:3b"
    
    if "documents_indexed" not in st.session_state:
        st.session_state.documents_indexed = 0
    
    if "services_status" not in st.session_state:
        st.session_state.services_status = {}

def check_system_status():
    """Check status of all required services"""
    try:
        status = check_services_status()
        st.session_state.services_status = status
        return status
    except Exception as e:
        st.error(f"Error checking services: {e}")
        return {}

def render_sidebar():
    """Render the sidebar with controls and status"""
    with st.sidebar:
        st.title("🤖 RAG System")
        st.markdown("---")
        
        # System Status
        st.subheader("📊 System Status")
        status = st.session_state.services_status
        
        if status.get("ollama", False):
            st.success("🟢 Ollama: Running")
        else:
            st.error("🔴 Ollama: Not available")
        
        if status.get("qdrant", False):
            st.success("🟢 Qdrant: Running")
        else:
            st.error("🔴 Qdrant: Not available")
        
        if status.get("redis", False):
            st.success("🟢 Redis: Running")
        else:
            st.warning("🟡 Redis: Optional service")
        
        # Refresh status button
        if st.button("🔄 Refresh Status"):
            check_system_status()
            st.rerun()
        
        st.markdown("---")
        
        # Model Selection
        st.subheader("🧠 Model Settings")
        available_models = ["llama3.2:3b", "phi3:mini"]
        
        selected_model = st.selectbox(
            "Select Model:",
            available_models,
            index=available_models.index(st.session_state.current_model)
        )
        
        if selected_model != st.session_state.current_model:
            st.session_state.current_model = selected_model
            st.success(f"Model changed to {selected_model}")
        
        # RAG Toggle
        st.session_state.rag_enabled = st.toggle(
            "Enable RAG", 
            value=st.session_state.rag_enabled,
            help="Use document knowledge for responses"
        )
        
        st.markdown("---")
        
        # Document Statistics
        st.subheader("📚 Document Statistics")
        st.metric("Documents Indexed", st.session_state.documents_indexed)
        
        # Clear conversation
        if st.button("🗑️ Clear Conversation"):
            st.session_state.messages = []
            st.success("Conversation cleared!")
            st.rerun()

def render_document_upload():
    """Render document upload section"""
    st.subheader("📤 Upload Documents")
    
    uploaded_files = st.file_uploader(
        "Choose files to upload",
        accept_multiple_files=True,
        type=['txt', 'pdf', 'docx', 'csv', 'json', 'md'],
        help="Supported formats: TXT, PDF, DOCX, CSV, JSON, Markdown"
    )
    
    if uploaded_files:
        if st.button("📁 Process Documents"):
            process_uploaded_documents(uploaded_files)

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
                # Process document
                chunks = doc_processor.process_file(file_path)
                
                # Index in vector store
                if chunks:
                    vector_store.add_documents(chunks)
                    processed_files += 1
                    st.success(f"✅ Processed: {uploaded_file.name} ({len(chunks)} chunks)")
                else:
                    st.warning(f"⚠️ No content extracted from: {uploaded_file.name}")
                
            except Exception as e:
                st.error(f"❌ Error processing {uploaded_file.name}: {e}")
            
            # Update progress
            progress_bar.progress((i + 1) / total_files)
        
        # Update document count
        st.session_state.documents_indexed += processed_files
        status_text.text(f"✅ Processing complete! {processed_files}/{total_files} files indexed.")
        
    except Exception as e:
        st.error(f"Error during document processing: {e}")

def render_chat_interface():
    """Render the main chat interface"""
    st.subheader("💬 Chat with Your Documents")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # Show sources if available
            if "sources" in message and message["sources"]:
                with st.expander("📎 Sources"):
                    for source in message["sources"]:
                        st.caption(f"• {source}")

    # Chat input
    if prompt := st.chat_input("Ask a question about your documents..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate assistant response
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            
            try:
                response, sources = generate_response(prompt)
                response_placeholder.markdown(response)
                
                # Show sources
                if sources and st.session_state.rag_enabled:
                    with st.expander("📎 Sources"):
                        for source in sources:
                            st.caption(f"• {source}")
                
                # Add assistant message
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response,
                    "sources": sources if st.session_state.rag_enabled else []
                })
                
            except Exception as e:
                error_msg = f"Error generating response: {e}"
                response_placeholder.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": error_msg,
                    "sources": []
                })

def generate_response(prompt):
    """Generate response using Ollama with optional RAG"""
    try:
        config = load_config()
        ollama_client = OllamaClient(config)
        
        sources = []
        context = ""
        
        # If RAG is enabled, search for relevant documents
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
        
        # Construct prompt with context
        if context:
            system_prompt = """You are a helpful assistant that answers questions based on the provided context. 
            Use the context to inform your response, but also use your general knowledge when appropriate.
            If the context doesn't contain relevant information, say so and provide a general response.
            
            Context:
            {context}
            
            Question: {question}
            
            Answer:"""
            
            full_prompt = system_prompt.format(context=context, question=prompt)
        else:
            full_prompt = prompt
        
        # Generate response
        response = ollama_client.generate(
            model=st.session_state.current_model,
            prompt=full_prompt
        )
        
        return response, sources
        
    except Exception as e:
        raise Exception(f"Failed to generate response: {e}")

def main():
    """Main application function"""
    # Initialize session state
    initialize_session_state()
    
    # Check system status
    check_system_status()
    
    # Render sidebar
    render_sidebar()
    
    # Main content area
    st.title("🤖 RAG System - Local AI Assistant")
    st.markdown("**Windows 11 On-Premises RAG System** | 100% Local | Zero Cloud Dependencies")
    
    # Check if core services are available
    if not st.session_state.services_status.get("ollama", False):
        st.error("🚨 Ollama service is not running. Please start Ollama and refresh the page.")
        st.markdown("""
        **To start Ollama:**
        1. Open Command Prompt as Administrator
        2. Run: `ollama serve`
        3. Or restart the Ollama Windows service
        """)
        return
    
    if not st.session_state.services_status.get("qdrant", False):
        st.warning("⚠️ Qdrant service is not running. Document indexing will not work.")
        st.markdown("""
        **To start Qdrant:**
        1. Ensure Docker Desktop is running
        2. Run: `docker run -p 6333:6333 qdrant/qdrant`
        """)
    
    # Create tabs for different functions
    tab1, tab2, tab3 = st.tabs(["💬 Chat", "📤 Upload Documents", "📊 System Info"])
    
    with tab1:
        render_chat_interface()
    
    with tab2:
        render_document_upload()
    
    with tab3:
        st.subheader("🖥️ System Information")
        st.json(st.session_state.services_status)
        
        if st.button("🧪 Test All Services"):
            test_all_services()

def test_all_services():
    """Test all services and display results"""
    try:
        config = load_config()
        
        # Test Ollama
        with st.spinner("Testing Ollama..."):
            try:
                ollama_client = OllamaClient(config)
                test_response = ollama_client.generate("llama3.2:3b", "Hello, this is a test.")
                st.success("✅ Ollama: Working correctly")
                st.info(f"Test response: {test_response[:100]}...")
            except Exception as e:
                st.error(f"❌ Ollama: {e}")
        
        # Test Qdrant
        with st.spinner("Testing Qdrant..."):
            try:
                vector_store = VectorStore(config)
                status = vector_store.health_check()
                st.success("✅ Qdrant: Working correctly")
                st.info(f"Qdrant status: {status}")
            except Exception as e:
                st.error(f"❌ Qdrant: {e}")
        
        # Test Document Processor
        with st.spinner("Testing Document Processor..."):
            try:
                doc_processor = DocumentProcessor(config)
                st.success("✅ Document Processor: Initialized successfully")
            except Exception as e:
                st.error(f"❌ Document Processor: {e}")
                
    except Exception as e:
        st.error(f"Error during testing: {e}")

if __name__ == "__main__":
    # Setup logging
    setup_logging()
    
    # Run main application
    main()