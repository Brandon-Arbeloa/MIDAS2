"""
Background task model for MIDAS backend
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from backend.core.database import Base

class BackgroundTask(Base):
    """Background task model for Celery task tracking"""
    __tablename__ = "background_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    celery_task_id = Column(String(100), unique=True, index=True)
    task_name = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False)  # document_processing, analysis, etc.
    
    # Task parameters
    parameters = Column(JSON, default=dict)
    
    # Task status
    status = Column(String(20), default='pending')  # pending, running, completed, failed, cancelled
    progress = Column(Integer, default=0)  # 0-100
    current_step = Column(String(100))
    total_steps = Column(Integer, default=1)
    
    # Results and errors
    result = Column(JSON)
    error_message = Column(Text)
    traceback = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    # Priority and retry
    priority = Column(Integer, default=0)  # Higher number = higher priority
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User")

    def __repr__(self):
        return f"<BackgroundTask(task_name='{self.task_name}', status='{self.status}')>"

class TaskLog(Base):
    """Task execution log entries"""
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("background_tasks.id"), nullable=False)
    level = Column(String(10), nullable=False)  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Additional context
    context = Column(JSON, default=dict)
    
    # Relationships
    task = relationship("BackgroundTask")

    def __repr__(self):
        return f"<TaskLog(level='{self.level}', message='{self.message[:50]}...')>"