import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float, Boolean
from sqlalchemy.orm import relationship
from database.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    department = Column(String, default="Engineering", nullable=False)
    role = Column(String, default="employee", nullable=False)  # super_admin, department_manager, team_lead, employee, guest
    team = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    clearance_level = Column(String, default="INTERNAL", nullable=False)  # PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, HIGHLY_CONFIDENTIAL
    full_name = Column(String, nullable=True)
    contact_details = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    documents = relationship("Document", foreign_keys="[Document.user_id]", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    department = Column(String, default="Engineering", nullable=False)
    team = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Backward compatible owner reference
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    classification = Column(String, default="INTERNAL", nullable=False)  # PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, HIGHLY_CONFIDENTIAL
    visibility = Column(String, default="Department", nullable=False)  # Private, Team, Department, Organization, Custom Users
    approved = Column(Boolean, default=False, nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    version = Column(String, default="1.0", nullable=False)
    tags = Column(JSON, nullable=True)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id], back_populates="documents")
    owner = relationship("User", foreign_keys=[owner_id])
    uploader = relationship("User", foreign_keys=[uploaded_by])
    approver = relationship("User", foreign_keys=[approved_by])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_username = Column(String, nullable=False)
    department = Column(String, nullable=True)
    action = Column(String, nullable=False)  # Login, Logout, Upload, Delete, Search, Query, Permission Denied, Role Changes, Department Changes, Approval, Download
    target_document_id = Column(Integer, nullable=True)
    target_document_title = Column(String, nullable=True)
    status = Column(String, nullable=False)  # SUCCESS, FAILED, DENIED
    ip_address = Column(String, nullable=True)
    details = Column(JSON, nullable=True)

    user = relationship("User", back_populates="audit_logs")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="conversations")
    workflow_executions = relationship("WorkflowExecution", back_populates="conversation", cascade="all, delete-orphan")


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(Text, nullable=False)
    status = Column(String, nullable=False)  # success, failed, validation_failed
    execution_time_ms = Column(Float, default=0.0)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    state_dump = Column(JSON, nullable=True)  # JSON representation of final State
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)

    conversation = relationship("Conversation", back_populates="workflow_executions")
