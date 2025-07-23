"""
Document model for MIDAS backend
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from backend.core.database import Base

class Document(Base):
    """Document model for file management"""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)  # Windows file path
    file_type = Column(String(50))
    file_size = Column(BigInteger)
    content_hash = Column(String(64))
    
    # Processing status
    status = Column(String(50), default='pending')  # pending, processing, completed, failed
    error_message = Column(Text)
    processing_progress = Column(Integer, default=0)  # 0-100
    
    # Metadata
    metadata = Column(JSON, default=dict)
    tags = Column(JSON, default=list)  # Array of tags
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True))
    
    # Relationships
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="documents")
    
    # Content analysis results
    extracted_text = Column(Text)
    summary = Column(Text)
    keywords = Column(JSON, default=list)
    
    # Vector storage reference
    vector_id = Column(String(100))  # Reference to Qdrant vector
    collection_name = Column(String(100), default="documents")

    def __repr__(self):
        return f"<Document(filename='{self.filename}', status='{self.status}')>"