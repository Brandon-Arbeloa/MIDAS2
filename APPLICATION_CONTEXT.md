# APPLICATION CONTEXT - MIDAS RAG System

## Current Application State
**Last Updated:** 2025-07-22
**Status:** Ready to run (moved to correct directory structure)
**Project Location:** C:\Users\Rolando Fender\MIDAS\

## Application Overview
MIDAS is a Windows 11 On-Premises RAG (Retrieval-Augmented Generation) System designed for secure, local document processing and AI-powered search capabilities.

## Current Configuration

### Core Components Status
1. **Streamlit Frontend**: ✅ Running (Fixed all import/syntax errors)
2. **Document Processor**: ✅ Configured (Cleaned up file structure)
3. **Storage Manager**: ✅ Configured (Fixed syntax errors)
4. **File Utils**: ✅ Configured (Fixed Windows compatibility)
5. **Config Manager**: ✅ Configured (Fixed missing parenthesis)

### Recent Fixes Applied
1. **config.py**: Fixed unclosed parenthesis on line 228
2. **document_processor_refactored.py**: Fixed indentation error and restructured file
3. **file_utils_refactored.py**: Fixed indentation error and added Windows compatibility for file locking
4. **storage_manager_refactored.py**: Fixed syntax error (passvalid") and import issues
5. **Streamlit_RAG_System.py**: Updated imports to match actual file structure

### Module Dependencies
- **streamlit**: UI framework (installed)
- **pyyaml**: Configuration management (installed)
- **Document Processing**: PyPDF2, python-docx, pandas (optional, not yet installed)
- **Vector Store**: Placeholder implementation (actual implementation pending)
- **LLM Client**: Placeholder implementation (Ollama integration pending)

### File Structure
```
C:\Users\Rolando Fender\MIDAS\
├── Streamlit_RAG_System.py       # Main application entry point
├── config.py                     # Configuration management  
├── constants_config.py           # Application constants
├── document_processor_refactored.py  # Document processing logic
├── file_utils_refactored.py     # File operations utilities
├── storage_manager_refactored.py # Storage and database management
├── rag_env\                      # Virtual environment with packages
├── data\                         # Data directories
│   ├── uploads\                  # Document uploads  
│   └── temp\                     # Temporary files
├── APPLICATION_CONTEXT.md         # Current application state
├── EXTERNAL_SERVICES_REQUIREMENTS.md # Deployment dependencies
├── STARTUP_INSTRUCTIONS.md       # Recovery procedures
├── WINDOWS_SETUP_GUIDE.md        # Complete setup guide
├── PROJECT_SETUP_COMPLETE.md     # Setup completion summary
├── docker_compose_file.yaml      # Docker configuration
├── Requirements.txt              # Python dependencies
├── original.env                  # Environment variables template
├── unified_compliance_doc.md     # Compliance documentation
└── Readme.md                     # Project documentation
```

### Current Limitations
1. **Vector Store**: Using placeholder implementation
2. **LLM Integration**: Using placeholder responses
3. **External Services**: Not yet connected to Ollama, Qdrant, or PostgreSQL
4. **Authentication**: Not implemented
5. **Document Processing**: Limited functionality without optional libraries

### Next Steps Required
1. Install remaining dependencies from Requirements.txt
2. Set up external services (Ollama, Qdrant, PostgreSQL, Redis)
3. Implement actual vector store functionality
4. Connect to Ollama for LLM capabilities
5. Set up authentication system
6. Configure document upload directory
7. Implement proper logging

### Environment Variables Needed
- `OLLAMA_BASE_URL`: Ollama API endpoint
- `QDRANT_HOST`: Qdrant vector database host
- `POSTGRES_CONNECTION`: PostgreSQL connection string
- `REDIS_HOST`: Redis cache host
- `SECRET_KEY`: Application secret key for security

### Known Issues
1. File locking uses different mechanisms on Windows vs Unix
2. Some PDF/DOCX processing libraries are not installed
3. No persistent storage configured yet
4. No user authentication implemented

### Port Management
- Application runs on port 8501 by default
- Previous instances must be killed before launching new ones
- Use `netstat -ano | findstr :850` to check active ports
- Use `taskkill //PID [process_id] //F` to kill processes on Windows