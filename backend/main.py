"""
MIDAS FastAPI Backend
Production-ready API server with WebSocket support for Windows 11
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware

# Windows-specific imports
try:
    import winreg
    from win32api import GetUserName
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    GetUserName = lambda: "user"

# Local imports
from backend.core.config import settings
from backend.core.database import engine, create_tables
from backend.core.security import create_access_token, verify_token
from backend.api.routes import chat, documents, dashboards, users, tasks
from backend.services.websocket_manager import ConnectionManager
from backend.services.background_tasks import task_manager
from backend.middleware.windows_auth import WindowsAuthMiddleware
from backend.middleware.security import SecurityHeadersMiddleware

# Configure logging for Windows
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/midas_backend.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Global WebSocket manager
websocket_manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting MIDAS FastAPI Backend...")
    
    # Create database tables
    await create_tables()
    
    # Start background task manager
    await task_manager.start()
    
    # Initialize Windows-specific services
    await initialize_windows_services()
    
    logger.info("MIDAS Backend startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down MIDAS Backend...")
    await task_manager.stop()
    logger.info("MIDAS Backend shutdown complete")

async def initialize_windows_services():
    """Initialize Windows-specific services"""
    try:
        # Check Windows version compatibility
        import platform
        if platform.system() != "Windows":
            logger.warning("Running on non-Windows system - some features may be limited")
            return
            
        # Initialize Windows authentication if available
        current_user = GetUserName()
        display_name = GetUserNameEx(NameDisplay)
        logger.info(f"Windows user: {current_user} ({display_name})")
        
        # Check for Windows services (Ollama, etc.)
        await check_windows_services()
        
    except Exception as e:
        logger.error(f"Windows service initialization error: {e}")

async def check_windows_services():
    """Check status of required Windows services"""
    import aiohttp
    services_status = {}
    
    # Check Ollama
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:11434/api/tags", timeout=5) as response:
                if response.status == 200:
                    services_status['ollama'] = 'running'
                else:
                    services_status['ollama'] = 'error'
    except:
        services_status['ollama'] = 'stopped'
    
    # Check Qdrant
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:6333/health", timeout=5) as response:
                if response.status == 200:
                    services_status['qdrant'] = 'running'
                else:
                    services_status['qdrant'] = 'error'
    except:
        services_status['qdrant'] = 'stopped'
    
    logger.info(f"Services status: {services_status}")
    return services_status

# Create FastAPI app
app = FastAPI(
    title="MIDAS API",
    description="Modular Intelligence & Data Analysis System - Production API",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)

# Security middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(WindowsAuthMiddleware)

# Session middleware for Windows auth
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=86400,  # 24 hours
    same_site="lax",
    https_only=False  # Set to True in production with HTTPS
)

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "*.local"]
)

# CORS middleware for Windows development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:8000",  # FastAPI
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
app.include_router(dashboards.router, prefix="/api/v1", tags=["dashboards"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])

# WebSocket endpoint for real-time communication
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """WebSocket endpoint for real-time updates"""
    await websocket_manager.connect(websocket, client_id)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            
            # Handle different message types
            import json
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "ping":
                    await websocket_manager.send_personal_message("pong", client_id)
                elif message_type == "chat_message":
                    # Handle chat message with streaming
                    await handle_chat_websocket(message, client_id)
                elif message_type == "task_status":
                    # Send task status updates
                    await handle_task_status(message, client_id)
                    
            except json.JSONDecodeError:
                await websocket_manager.send_personal_message(
                    json.dumps({"type": "error", "message": "Invalid JSON format"}),
                    client_id
                )
                
    except WebSocketDisconnect:
        websocket_manager.disconnect(client_id)
        logger.info(f"WebSocket client {client_id} disconnected")

async def handle_chat_websocket(message: Dict[str, Any], client_id: str):
    """Handle chat messages with streaming responses"""
    try:
        from backend.services.chat_service import ChatService
        chat_service = ChatService()
        
        prompt = message.get("prompt", "")
        use_rag = message.get("use_rag", True)
        model = message.get("model", "llama2")
        
        # Stream response
        async for chunk in chat_service.stream_chat_response(prompt, use_rag, model):
            await websocket_manager.send_personal_message(
                json.dumps({
                    "type": "chat_chunk",
                    "content": chunk,
                    "message_id": message.get("message_id")
                }),
                client_id
            )
            
        # Send completion signal
        await websocket_manager.send_personal_message(
            json.dumps({
                "type": "chat_complete",
                "message_id": message.get("message_id")
            }),
            client_id
        )
        
    except Exception as e:
        await websocket_manager.send_personal_message(
            json.dumps({
                "type": "error",
                "message": str(e),
                "message_id": message.get("message_id")
            }),
            client_id
        )

async def handle_task_status(message: Dict[str, Any], client_id: str):
    """Handle task status requests"""
    try:
        task_id = message.get("task_id")
        status = await task_manager.get_task_status(task_id)
        
        await websocket_manager.send_personal_message(
            json.dumps({
                "type": "task_status",
                "task_id": task_id,
                "status": status
            }),
            client_id
        )
        
    except Exception as e:
        await websocket_manager.send_personal_message(
            json.dumps({
                "type": "error",
                "message": str(e)
            }),
            client_id
        )

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    services = await check_windows_services()
    return {
        "status": "healthy",
        "services": services,
        "user": GetUserName() if os.name == 'nt' else "unknown"
    }

# Windows authentication endpoint
@app.get("/api/auth/windows")
async def windows_auth():
    """Windows authentication endpoint"""
    if os.name != 'nt':
        raise HTTPException(status_code=501, detail="Windows authentication not available")
    
    try:
        username = GetUserName()
        display_name = GetUserNameEx(NameDisplay)
        
        # Create JWT token
        access_token = create_access_token(data={"sub": username})
        refresh_token = create_access_token(data={"sub": username, "type": "refresh"})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "username": username,
                "display_name": display_name
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Windows authentication failed: {e}")

# Serve React static files (production)
if settings.ENVIRONMENT == "production":
    # Mount static files
    static_path = Path(__file__).parent.parent / "frontend" / "build"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=static_path / "static"), name="static")
        
        @app.get("/", response_class=HTMLResponse)
        async def serve_react_app():
            """Serve React app index.html"""
            return FileResponse(static_path / "index.html")
        
        @app.get("/{path:path}", response_class=HTMLResponse)
        async def serve_react_routes(path: str):
            """Serve React app for all routes (SPA routing)"""
            # Check if it's an API route
            if path.startswith("api/") or path.startswith("ws"):
                raise HTTPException(status_code=404, detail="Not found")
            
            # Serve index.html for React routes
            return FileResponse(static_path / "index.html")

if __name__ == "__main__":
    # Windows-specific server configuration
    import multiprocessing
    
    # Set the number of workers based on CPU cores
    workers = min(4, multiprocessing.cpu_count())
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=1 if settings.ENVIRONMENT == "development" else workers,
        reload=settings.ENVIRONMENT == "development",
        log_level="info",
        access_log=True,
        loop="asyncio",
        # Windows-specific settings
        lifespan="on"
    )