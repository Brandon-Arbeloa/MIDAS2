"""
Dashboard model for MIDAS backend
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from backend.core.database import Base

class Dashboard(Base):
    """Dashboard model for visualization storage"""
    __tablename__ = "dashboards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # Dashboard configuration
    layout_config = Column(JSON, default=dict)  # Grid layout configuration
    chart_configs = Column(JSON, default=list)  # Chart configurations
    filter_configs = Column(JSON, default=list)  # Global filter configurations
    theme_config = Column(JSON, default=dict)  # Theme settings
    
    # Dashboard settings
    auto_refresh = Column(Boolean, default=False)
    refresh_interval = Column(Integer, default=300)  # seconds
    is_public = Column(Boolean, default=False)
    
    # Sharing settings
    shared_with = Column(JSON, default=list)  # List of user IDs or emails
    share_token = Column(String(100), unique=True)  # For public sharing
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_accessed = Column(DateTime(timezone=True))
    
    # Relationships
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="dashboards")

    def __repr__(self):
        return f"<Dashboard(name='{self.name}', owner='{self.owner.username if self.owner else 'Unknown'}')>"

class DashboardTemplate(Base):
    """Template model for dashboard creation"""
    __tablename__ = "dashboard_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50), default="general")
    
    # Template configuration
    template_config = Column(JSON, nullable=False)
    preview_image = Column(String(255))  # Path to preview image
    
    # Template metadata
    is_system = Column(Boolean, default=False)  # System vs user templates
    usage_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_by = relationship("User")

    def __repr__(self):
        return f"<DashboardTemplate(name='{self.name}', category='{self.category}')>"