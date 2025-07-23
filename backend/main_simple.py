"""
Simplified MIDAS FastAPI Backend for testing
"""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="MIDAS RAG System",
    description="Document Management and RAG System for Windows 11",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to MIDAS RAG System",
        "version": "1.0.0",
        "status": "online"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "MIDAS Backend",
        "timestamp": "2025-07-22T14:30:00"
    }

@app.get("/api/v1/test")
async def test_endpoint():
    """Test API endpoint"""
    return {
        "status": "success",
        "message": "API is working correctly",
        "data": {
            "backend": "FastAPI",
            "database": "PostgreSQL (configured)",
            "vector_db": "Qdrant (configured)",
            "llm": "Ollama (configured)"
        }
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting MIDAS FastAPI server...")
    uvicorn.run(app, host="0.0.0.0", port=8001)