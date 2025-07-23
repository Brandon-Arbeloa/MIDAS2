"""
Chat API routes with streaming support
"""

import json
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.database import get_db
from backend.core.security import verify_token
from backend.models import User, ChatSession, ChatMessage
from backend.services.chat_service import ChatService
from backend.services.auth_service import get_current_user

router = APIRouter()

# Pydantic models
class ChatSessionCreate(BaseModel):
    title: Optional[str] = None
    model_name: str = "llama2"
    temperature: int = 70
    use_rag: bool = True

class ChatSessionResponse(BaseModel):
    id: UUID
    title: Optional[str]
    model_name: str
    temperature: int
    use_rag: bool
    created_at: str
    updated_at: str
    message_count: int

class ChatMessageCreate(BaseModel):
    content: str
    session_id: UUID

class ChatMessageResponse(BaseModel):
    id: UUID
    content: str
    role: str
    sources: List[str] = []
    confidence_score: Optional[int] = None
    created_at: str
    token_count: Optional[int] = None
    processing_time: Optional[int] = None

class ChatResponse(BaseModel):
    message: ChatMessageResponse
    session: ChatSessionResponse

@router.post("/chat/sessions", response_model=ChatSessionResponse)
async def create_chat_session(
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new chat session"""
    chat_service = ChatService(db)
    session = await chat_service.create_session(
        user_id=current_user.id,
        title=session_data.title,
        model_name=session_data.model_name,
        temperature=session_data.temperature,
        use_rag=session_data.use_rag
    )
    return session

@router.get("/chat/sessions", response_model=List[ChatSessionResponse])
async def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all chat sessions for the current user"""
    chat_service = ChatService(db)
    sessions = await chat_service.get_user_sessions(current_user.id)
    return sessions

@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific chat session"""
    chat_service = ChatService(db)
    session = await chat_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session

@router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_chat_messages(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get messages for a chat session"""
    chat_service = ChatService(db)
    
    # Verify session belongs to user
    session = await chat_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    messages = await chat_service.get_session_messages(session_id)
    return messages

@router.post("/chat/message", response_model=ChatResponse)
async def send_chat_message(
    message_data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send a chat message and get response"""
    chat_service = ChatService(db)
    
    # Verify session belongs to user
    session = await chat_service.get_session(message_data.session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Create user message
    user_message = await chat_service.add_message(
        session_id=message_data.session_id,
        content=message_data.content,
        role="user"
    )
    
    # Generate AI response
    try:
        response_content, sources, confidence = await chat_service.generate_response(
            message_data.content,
            session.model_name,
            session.use_rag,
            session.temperature / 100.0  # Convert to 0-1 scale
        )
        
        # Create assistant message
        assistant_message = await chat_service.add_message(
            session_id=message_data.session_id,
            content=response_content,
            role="assistant",
            sources=sources,
            confidence_score=confidence
        )
        
        # Update session
        updated_session = await chat_service.get_session(message_data.session_id, current_user.id)
        
        return ChatResponse(
            message=assistant_message,
            session=updated_session
        )
        
    except Exception as e:
        # Create error message
        error_message = await chat_service.add_message(
            session_id=message_data.session_id,
            content=f"Error: {str(e)}",
            role="assistant"
        )
        
        updated_session = await chat_service.get_session(message_data.session_id, current_user.id)
        
        return ChatResponse(
            message=error_message,
            session=updated_session
        )

@router.post("/chat/stream")
async def stream_chat_message(
    message_data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Stream a chat message response"""
    chat_service = ChatService(db)
    
    # Verify session belongs to user
    session = await chat_service.get_session(message_data.session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Create user message
    await chat_service.add_message(
        session_id=message_data.session_id,
        content=message_data.content,
        role="user"
    )
    
    async def generate_response():
        """Generate streaming response"""
        full_response = ""
        sources = []
        confidence = None
        
        try:
            async for chunk in chat_service.stream_chat_response(
                message_data.content,
                session.use_rag,
                session.model_name,
                session.temperature / 100.0
            ):
                full_response += chunk
                
                # Send chunk as Server-Sent Event
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            
            # Create assistant message with full response
            await chat_service.add_message(
                session_id=message_data.session_id,
                content=full_response,
                role="assistant",
                sources=sources,
                confidence_score=confidence
            )
            
            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"
            
        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a chat session"""
    chat_service = ChatService(db)
    
    # Verify session belongs to user
    session = await chat_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    await chat_service.delete_session(session_id)
    return {"message": "Chat session deleted"}

@router.put("/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: UUID,
    session_data: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update chat session settings"""
    chat_service = ChatService(db)
    
    # Verify session belongs to user
    session = await chat_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    updated_session = await chat_service.update_session(
        session_id=session_id,
        title=session_data.title,
        model_name=session_data.model_name,
        temperature=session_data.temperature,
        use_rag=session_data.use_rag
    )
    
    return updated_session