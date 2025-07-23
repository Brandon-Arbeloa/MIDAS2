# MIDAS RAG Chat Application Usage Guide

## Overview

The MIDAS RAG Chat Application is a Streamlit-based interface that combines:
- **Local LLM inference** via Ollama
- **Document retrieval** from Qdrant vector database
- **Structured data search** across multiple collections
- **Windows-optimized file handling**

## Quick Start

### 1. Start Required Services

```powershell
# Start Ollama (if not running as service)
ollama serve

# Start Qdrant (Docker method)
.\Setup-Qdrant.ps1 -Method Docker

# Or manage existing Qdrant container
.\QdrantData\Manage-Qdrant.ps1 -Action start
```

### 2. Launch Chat Application

```powershell
# Standard launch
.\Start-Chat.ps1

# Custom port and debug mode
.\Start-Chat.ps1 -Port 8502 -Debug

# Specify host (for network access)
.\Start-Chat.ps1 -Host 0.0.0.0 -Port 8501
```

### 3. Access the Interface

- **Local URL**: http://localhost:8501
- **Network URL**: http://[your-ip]:8501 (if host set to 0.0.0.0)

## Interface Overview

### Main Chat Area
- **Message History**: Persistent conversation with the AI
- **Streaming Responses**: Real-time response generation
- **Context Sources**: Expandable sections showing retrieved documents
- **Input Field**: Type questions and press Enter

### Sidebar Features

#### Service Status
- **Ollama Connection**: Green ✅ if connected, Red ❌ if not
- **Available Models**: Dropdown to select LLM model
- **RAG System**: Shows document index status and collection sizes

#### Settings
- **Enable RAG**: Toggle document search on/off
- **Max Search Results**: Control how many documents to retrieve (1-10)
- **Response Creativity**: Temperature slider (0.0-2.0)
  - 0.0 = Very focused, deterministic
  - 1.0 = Balanced creativity
  - 2.0 = Highly creative, varied

#### Conversation Management
- **Clear Chat History**: Reset conversation
- **Save Configuration**: Persist settings to disk

## RAG (Retrieval-Augmented Generation) Features

### Document Search
The system searches through indexed documents using:
- **Vector Similarity**: Semantic search using embeddings
- **Multiple Collections**: Documents, structured data, summaries
- **Relevance Scoring**: Results ranked by similarity score
- **Context Injection**: Retrieved content added to AI prompt

### Supported Content Types
- **Text Documents**: .txt, .md files
- **Structured Data**: .csv, .xlsx files with schema awareness
- **Configuration Files**: .json, .yaml files
- **Document Metadata**: File paths, creation dates, sizes

### Search Result Display
Each retrieved document shows:
- **Source File**: Original filename
- **Relevance Score**: 0.0-1.0 similarity rating
- **Text Preview**: First 300 characters
- **Full Context**: Available in expandable sections

## Configuration

### Local Configuration File
Settings are stored in: `C:\MIDAS\config\chat_config.json`

```json
{
  "default_model": "llama3.2:3b",
  "system_prompt": "You are a helpful AI assistant...",
  "max_tokens": 2000,
  "temperature": 0.7,
  "enable_rag": true,
  "rag_max_results": 5,
  "theme": "auto"
}
```

### Model Management
```powershell
# List available models
ollama list

# Pull new models
ollama pull llama3.2:3b
ollama pull phi3:mini

# Remove models
ollama rm model_name
```

## Troubleshooting

### Common Issues

#### "Ollama Not Connected"
```powershell
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama service
ollama serve

# Check Windows services
Get-Service -Name "*ollama*"
```

#### "RAG System Not Initialized"
```powershell
# Check Qdrant status
curl http://localhost:6333/collections

# Restart Qdrant container
docker restart qdrant-midas

# Check Qdrant logs
docker logs qdrant-midas
```

#### "No Models Available"
```powershell
# Pull recommended models
ollama pull llama3.2:3b
ollama pull phi3:mini

# Verify model installation
ollama list
```

### Performance Optimization

#### For 8-16GB RAM Systems
- Use smaller models: `llama3.2:3b`, `phi3:mini`
- Reduce `rag_max_results` to 3-5
- Lower `temperature` for more focused responses
- Limit conversation history (automatic after 5 messages)

#### For Higher-End Systems
- Use larger models: `llama3.1:8b`, `codellama:13b`
- Increase `rag_max_results` to 7-10
- Enable more collections for structured data search

### Windows-Specific Optimizations

#### File Handling
- Uses `pathlib.Path` for cross-platform compatibility
- Handles Windows path separators correctly
- Respects Windows file locking mechanisms

#### Service Configuration
- Streamlit configured with `fileWatcherType: none`
- Environment variables set for headless operation
- Proper Windows service integration

## Advanced Usage

### Custom System Prompts
Modify the system prompt in configuration to change AI behavior:

```json
{
  "system_prompt": "You are a technical documentation assistant. Focus on providing code examples and step-by-step instructions. Use the knowledge base to give accurate, implementation-focused answers."
}
```

### API Integration
The chat system can be extended with additional APIs:
```python
# Add to chat_app.py
class CustomAPI:
    def search_external(self, query: str):
        # Implement external API calls
        pass
```

### Multi-Modal Extensions
Future enhancements could include:
- **PDF Parsing**: Direct PDF content extraction
- **Image Analysis**: Screenshot and diagram processing
- **Code Execution**: Interactive Python code blocks
- **Web Scraping**: Real-time web content retrieval

## Data Privacy & Security

### Local-Only Processing
- **No Cloud Dependencies**: All processing happens locally
- **Data Stays On-Premises**: Documents never leave your machine
- **Network Isolation**: Can run completely offline
- **Encryption**: Qdrant collections can be encrypted at rest

### Access Control
```powershell
# Restrict network access (localhost only)
.\Start-Chat.ps1 -Host 127.0.0.1

# Enable authentication (manual implementation needed)
# Add to chat_app.py: st.secrets for authentication
```

## Monitoring & Logging

### Application Logs
- **Location**: `C:\MIDAS\logs\`
- **Files**: 
  - `chat_app_YYYY-MM-DD.log`
  - `document_indexer_YYYY-MM-DD.log`
  - `structured_indexer_YYYY-MM-DD.log`

### Performance Metrics
```powershell
# Monitor resource usage
Get-Counter "\Process(python)\% Processor Time"
Get-Counter "\Process(python)\Working Set"

# Check service status
.\QdrantData\Test-Qdrant.ps1
.\Test-Ollama.ps1
```

### Usage Analytics
The system can track:
- **Query Frequency**: Most common search terms
- **Response Times**: Average generation speed
- **Document Usage**: Most frequently retrieved content
- **Model Performance**: Success rates per model

## Best Practices

### Conversation Management
- **Clear History**: Start fresh for unrelated topics
- **Specific Questions**: More focused queries yield better results
- **Context Building**: Reference previous responses for continuity
- **Source Verification**: Check retrieved document sources

### Document Organization
- **Structured Folders**: Organize documents by topic/project
- **Consistent Naming**: Use descriptive filenames
- **Regular Updates**: Re-index when content changes
- **Metadata Enrichment**: Include relevant keywords in documents

### Performance Monitoring
- **Resource Usage**: Monitor RAM/CPU during heavy use
- **Response Quality**: Evaluate AI response accuracy
- **Search Relevance**: Check if retrieved documents are helpful
- **System Stability**: Watch for memory leaks or crashes

## Support & Maintenance

### Regular Maintenance
```powershell
# Update models monthly
ollama pull llama3.2:3b

# Clean up old logs (optional)
Remove-Item "C:\MIDAS\logs\*" -Older (Get-Date).AddDays(-30)

# Restart services weekly
docker restart qdrant-midas
Restart-Service ollama  # If running as Windows service
```

### Backup Strategy
```powershell
# Backup Qdrant data
Copy-Item "C:\QdrantData\storage" "C:\Backup\qdrant-$(Get-Date -Format 'yyyy-MM-dd')" -Recurse

# Backup configuration
Copy-Item "C:\MIDAS\config" "C:\Backup\midas-config-$(Get-Date -Format 'yyyy-MM-dd')" -Recurse
```

### Getting Help
1. **Check Logs**: Review log files in `C:\MIDAS\logs\`
2. **Test Services**: Run `.\Test-Ollama.ps1` and `.\QdrantData\Test-Qdrant.ps1`
3. **Restart Services**: Use management scripts to restart components
4. **Update Dependencies**: Ensure all Python packages are current
5. **Documentation**: Refer to component-specific documentation

---

**Version**: 1.0  
**Last Updated**: 2025-01-22  
**Platform**: Windows 11  
**Dependencies**: Python 3.10+, Streamlit 1.47+, Ollama, Qdrant