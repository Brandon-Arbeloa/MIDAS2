# STARTUP INSTRUCTIONS - Context Recovery Guide

## Purpose
This document provides step-by-step instructions for recovering the MIDAS RAG System context and ensuring proper application startup. Use this when context is lost or when resuming development.

## Quick Status Check

### 1. Verify Current Application State
```bash
# Check if Streamlit is running
netstat -ano | findstr :8501

# If running, note the PID and access at http://localhost:8501
```

### 2. Read Current Context
Always start by reviewing these files in order:
1. **APPLICATION_CONTEXT.md** - Current state and recent changes
2. **EXTERNAL_SERVICES_REQUIREMENTS.md** - Dependencies needed
3. **This file** - Recovery procedures

## Complete Startup Procedure

### Step 1: Environment Verification
```bash
# Verify Python version
python --version  # Should be 3.11+

# Check if in correct directory
pwd  # Should show MIDAS project directory

# List key files
ls -la  # Verify all core files exist
```

### Step 2: Install Basic Dependencies
```bash
# Install Streamlit if not already installed
pip install streamlit pyyaml

# Test basic imports
python -c "import streamlit; import yaml; print('Basic dependencies OK')"
```

### Step 3: Stop Any Running Instances
```bash
# Check for running Streamlit instances
netstat -ano | findstr :850

# Kill any running processes (replace PID numbers as needed)
taskkill //PID [PID_NUMBER] //F

# Verify all ports are clear
netstat -ano | findstr :850  # Should return empty
```

### Step 4: Test Core Module Imports
```bash
# Test each module individually
python -c "from config import ConfigManager; print('Config OK')"
python -c "from document_processor_refactored import DocumentProcessor; print('DocProcessor OK')"
python -c "from file_utils_refactored import get_uploaded_files_dir; print('FileUtils OK')"
python -c "from storage_manager_refactored import StorageManager; print('StorageManager OK')"
```

### Step 5: Launch Application
```bash
# Launch with proper port specification
python -m streamlit run Streamlit_RAG_System.py --server.port 8501 --server.headless true

# Access at: http://localhost:8501
```

## Known Issues & Solutions

### Issue 1: Import Errors
**Symptoms**: ModuleNotFoundError, ImportError
**Solution**:
```bash
# Check if files were corrupted/modified
# Refer to APPLICATION_CONTEXT.md for recent fixes
# Common fixes:
# - Fix config.py line 228 parenthesis
# - Check document_processor_refactored.py structure
# - Verify file_utils_refactored.py Windows compatibility
```

### Issue 2: Syntax Errors
**Symptoms**: SyntaxError messages
**Solution**:
```bash
# Check specific error lines mentioned
# Common issues:
# - Unclosed strings/parentheses
# - Indentation problems
# - Mixed code fragments
```

### Issue 3: Port Conflicts
**Symptoms**: Address already in use
**Solution**:
```bash
# Kill all Streamlit processes
taskkill //IM python.exe //F
# Or use specific PIDs from netstat
```

### Issue 4: Missing Dependencies
**Symptoms**: Module not found for specific libraries
**Solution**:
```bash
# Install from requirements
pip install -r Requirements.txt
# Or install individually as needed
```

## Module Status Reference

### ✅ Working Modules
- `config.py` - Configuration management
- `document_processor_refactored.py` - Document processing
- `file_utils_refactored.py` - File operations
- `storage_manager_refactored.py` - Storage management
- `Streamlit_RAG_System.py` - Main application

### ⚠️ Placeholder Implementations
- OllamaClient class - Returns dummy responses
- VectorStore class - Empty implementation
- Service status checks - Returns hardcoded values

### ❌ Not Yet Implemented
- Actual LLM integration
- Vector database connection
- User authentication
- Document upload processing

## Development Context Recovery

### If Starting Fresh Development Session:
1. Read APPLICATION_CONTEXT.md for current state
2. Run through Step 1-5 above
3. Check EXTERNAL_SERVICES_REQUIREMENTS.md for next steps
4. Update APPLICATION_CONTEXT.md with any changes made

### If Debugging Issues:
1. Check error messages against known issues above
2. Verify file integrity of core modules
3. Test imports individually
4. Check git status for any uncommitted changes

### If Adding New Features:
1. Update APPLICATION_CONTEXT.md with new module status
2. Add any new external dependencies to EXTERNAL_SERVICES_REQUIREMENTS.md
3. Test new imports in Step 4 procedure
4. Update this file with new known issues if encountered

## File Structure Verification

Ensure these files exist and are not corrupted:
```
MIDAS/
├── APPLICATION_CONTEXT.md           ✅ Status tracking
├── EXTERNAL_SERVICES_REQUIREMENTS.md ✅ Deployment deps
├── STARTUP_INSTRUCTIONS.md          ✅ This file
├── Streamlit_RAG_System.py          ✅ Main app
├── config.py                        ✅ Config manager
├── constants_config.py              ✅ Constants
├── document_processor_refactored.py ✅ Doc processing
├── file_utils_refactored.py         ✅ File utils
├── storage_manager_refactored.py    ✅ Storage
├── Requirements.txt                 ✅ Dependencies
├── docker_compose_file.yaml         ✅ Docker config
├── original.env                     ✅ Env template
├── unified_compliance_doc.md        ✅ Compliance
└── Readme.md                        📝 Needs update
```

## Emergency Recovery Commands

If application is completely broken:
```bash
# 1. Kill everything
taskkill //IM python.exe //F

# 2. Restart clean
cd "C:\Users\Rolando Fender\MIDAS\MIDAS"

# 3. Test minimal import
python -c "import streamlit; print('Streamlit works')"

# 4. Launch basic Streamlit
python -c "import streamlit as st; st.write('Test'); st.stop()" | python -m streamlit run /dev/stdin
```

## Context Update Procedure

When making changes, always update:
1. APPLICATION_CONTEXT.md - Current state changes
2. This file - Any new issues or solutions discovered
3. EXTERNAL_SERVICES_REQUIREMENTS.md - New dependencies

## Last Known Good Configuration

- **Date**: 2025-07-22
- **Python**: 3.11+
- **Streamlit**: Latest
- **Port**: 8501
- **Status**: All core modules loading, UI functional with placeholder data
- **Next Steps**: External service integration required

---

**Always check APPLICATION_CONTEXT.md first for the most current status before making changes.**