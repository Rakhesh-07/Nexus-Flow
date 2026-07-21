import os
import time
import json
import datetime
import redis
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.config import settings
from api.deps import (
    get_db, get_current_user, UserCreate, UserResponse, Token, QueryRequest,
    WorkflowRunRequest, require_roles, ProfileUpdate, PasswordChange, AdminUserUpdate
)
from api.security import verify_password, get_password_hash, create_access_token
from database.models import User, Document, Conversation, WorkflowExecution, AuditLog
from services.permission_service import PermissionService, DEPARTMENTS, ROLES, CLASSIFICATIONS, CLASSIFICATION_RANK
from rag.document_processor import extract_text, chunk_text
from rag.chroma_service import chroma_service
from agents.graph import app_graph
from monitoring.telemetry import (
    HTTP_REQUESTS_TOTAL,
    AIFLOW_AGENT_LATENCY,
    AIFLOW_WORKFLOW_EXECUTION,
    AIFLOW_AGENT_FAILURES,
    AIFLOW_REDIS_CACHE_HITS
)

router = APIRouter()

# Setup Redis connection safely
try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis cache.")
except Exception as e:
    logger.warning(f"Could not connect to Redis. Caching will be bypassed. Error: {e}")
    redis_client = None


@router.post("/register", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, request: Request, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_in.username).first()
    if existing_user:
        PermissionService.log_audit_event(
            db, None, "Registration", "FAILED",
            ip_address=request.client.host if request.client else "127.0.0.1",
            details={"username": user_in.username, "reason": "Username already registered"}
        )
        raise HTTPException(status_code=400, detail="Username already registered")
        
    hashed_password = get_password_hash(user_in.password)
    
    # Process department and role
    dept = user_in.department if user_in.department in DEPARTMENTS else "Engineering"
    role_raw = user_in.role.lower() if user_in.role else "employee"
    
    # Map special usernames or raw role values
    if user_in.username.lower() in ["admin", "admin@nexusflow.ai"]:
        role = "super_admin"
        dept = "Information Technology"
    elif role_raw in ["admin", "super_admin"]:
        role = "super_admin"
    elif role_raw in ROLES:
        role = role_raw
    else:
        role = "employee"
        
    # Default clearance levels based on role
    clearance_map = {
        "super_admin": "HIGHLY_CONFIDENTIAL",
        "department_manager": "RESTRICTED",
        "team_lead": "CONFIDENTIAL",
        "employee": "INTERNAL",
        "guest": "PUBLIC"
    }
    clearance = clearance_map.get(role, "INTERNAL")

    user = User(
        username=user_in.username,
        hashed_password=hashed_password,
        department=dept,
        role=role,
        team=user_in.team,
        designation=user_in.designation,
        clearance_level=clearance,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    PermissionService.log_audit_event(
        db, user, "Registration", "SUCCESS",
        ip_address=request.client.host if request.client else "127.0.0.1",
        details={"role": role, "department": dept, "clearance": clearance}
    )

    return {"message": "User registered successfully", "id": str(user.id), "role": role, "department": dept}


@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    ip = request.client.host if request.client else "127.0.0.1"

    if not user or not verify_password(form_data.password, user.hashed_password):
        PermissionService.log_audit_event(
            db, user, "Login", "FAILED",
            ip_address=ip,
            details={"attempted_username": form_data.username, "reason": "Invalid credentials"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        PermissionService.log_audit_event(
            db, user, "Login", "DENIED",
            ip_address=ip,
            details={"reason": "User account deactivated"}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact Administrator."
        )

    # Embed JWT Claims
    claims = {
        "user_id": user.id,
        "role": user.role,
        "department": user.department,
        "team": user.team,
        "clearance_level": user.clearance_level
    }
    access_token = create_access_token(subject=user.username, claims=claims)

    PermissionService.log_audit_event(
        db, user, "Login", "SUCCESS",
        ip_address=ip,
        details={"role": user.role, "department": user.department}
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_user_profile(current_user: User = Depends(get_current_user)):
    """
    Returns current authenticated user profile including RBAC claims.
    """
    return current_user


@router.put("/me/profile", response_model=UserResponse)
def update_own_profile(
    profile_in: ProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Self-service profile update: Allows any user to update their full_name, contact_details, and email.
    """
    ip = request.client.host if request.client else "127.0.0.1"
    if profile_in.full_name is not None:
        current_user.full_name = profile_in.full_name
    if profile_in.contact_details is not None:
        current_user.contact_details = profile_in.contact_details
    if profile_in.email is not None:
        current_user.email = profile_in.email

    current_user.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(current_user)

    PermissionService.log_audit_event(
        db, current_user, "Profile Update", "SUCCESS",
        ip_address=ip,
        details={"updated_fields": ["full_name", "contact_details", "email"]}
    )
    return current_user


@router.put("/me/password", response_model=Dict[str, str])
def change_own_password(
    pwd_in: PasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Self-service password change: Allows any user to update their password.
    """
    ip = request.client.host if request.client else "127.0.0.1"
    if not verify_password(pwd_in.current_password, current_user.hashed_password):
        PermissionService.log_audit_event(
            db, current_user, "Password Change", "FAILED",
            ip_address=ip,
            details={"reason": "Incorrect current password"}
        )
        raise HTTPException(status_code=400, detail="Incorrect current password.")

    current_user.hashed_password = get_password_hash(pwd_in.new_password)
    current_user.updated_at = datetime.datetime.utcnow()
    db.commit()

    PermissionService.log_audit_event(
        db, current_user, "Password Change", "SUCCESS",
        ip_address=ip
    )
    return {"message": "Password updated successfully."}


@router.post("/upload", response_model=Dict[str, Any])
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    department: Optional[str] = Form(None),
    classification: Optional[str] = Form("INTERNAL"),
    visibility: Optional[str] = Form("Department"),
    team: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Accepts file uploads, validates enterprise upload permissions, applies approval workflows,
    and indexes approved chunks into ChromaDB with rich security metadata.
    """
    start_time = time.time()
    ip = request.client.host if request.client else "127.0.0.1"

    # Check permission
    if not PermissionService.can_upload_document(current_user):
        PermissionService.log_audit_event(
            db, current_user, "Upload", "DENIED",
            ip_address=ip,
            details={"filename": file.filename, "reason": "Guest or inactive user cannot upload documents"}
        )
        raise HTTPException(status_code=403, detail="Upload forbidden for your role.")

    # Target department
    target_dept = department if department in DEPARTMENTS else current_user.department
    target_class = classification.upper() if classification and classification.upper() in CLASSIFICATIONS else "INTERNAL"
    target_vis = visibility.capitalize() if visibility else "Department"

    # Save file on disk
    os.makedirs("./uploads", exist_ok=True)
    file_path = os.path.join("./uploads", f"{current_user.id}_{int(time.time())}_{file.filename}")
    
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Could not save file payload.")
        
    try:
        raw_text = extract_text(file_path)
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="Uploaded file is empty or text extraction failed.")

        # Determine Approval Status (Managers and Super Admins auto-approve)
        role = current_user.role.lower()
        is_approved = role in ["super_admin", "department_manager"]
        approved_by = current_user.id if is_approved else None
        approved_at = datetime.datetime.utcnow() if is_approved else None

        # Parse tags
        parsed_tags = None
        if tags:
            try:
                parsed_tags = json.loads(tags)
            except Exception:
                parsed_tags = {"raw_tags": tags}

        # Create Database Record
        doc_record = Document(
            filename=file.filename,
            file_path=file_path,
            content_type=file.content_type,
            department=target_dept,
            team=team or current_user.team,
            user_id=current_user.id,
            owner_id=current_user.id,
            uploaded_by=current_user.id,
            classification=target_class,
            visibility=target_vis,
            approved=is_approved,
            approved_by=approved_by,
            approved_at=approved_at,
            tags=parsed_tags
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

        chunks_count = 0
        if is_approved:
            # Chunk and Index in ChromaDB with metadata
            chunks = chunk_text(raw_text)
            chunks_count = len(chunks)
            metadatas = []
            ids = []
            for idx, chunk in enumerate(chunks):
                metadatas.append({
                    "document_id": doc_record.id,
                    "tenant_id": current_user.id,
                    "user_id": current_user.id,
                    "owner_id": current_user.id,
                    "department": target_dept,
                    "team": team or "",
                    "filename": file.filename,
                    "classification": target_class,
                    "visibility": target_vis,
                    "approved": True
                })
                ids.append(f"doc_{doc_record.id}_chunk_{idx}")
                
            chroma_service.add_chunks(texts=chunks, metadatas=metadatas, ids=ids)
            status_str = "SUCCESS"
            msg = "File indexed successfully"
        else:
            status_str = "PENDING_APPROVAL"
            msg = "File uploaded successfully and submitted for Department Manager approval."

        PermissionService.log_audit_event(
            db, current_user, "Upload", status_str,
            target_document=doc_record,
            ip_address=ip,
            details={
                "department": target_dept,
                "classification": target_class,
                "visibility": target_vis,
                "approved": is_approved
            }
        )

        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/upload", status="200").inc()

        return {
            "message": msg,
            "document_id": doc_record.id,
            "filename": file.filename,
            "department": target_dept,
            "classification": target_class,
            "visibility": target_vis,
            "approved": is_approved,
            "chunks_count": chunks_count,
            "latency_ms": round((time.time() - start_time) * 1000, 2)
        }
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        PermissionService.log_audit_event(
            db, current_user, "Upload", "FAILED",
            ip_address=ip,
            details={"filename": file.filename, "error": str(e)}
        )
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/upload", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents", response_model=List[Dict[str, Any]])
def get_documents_library(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns Document Library listing containing only documents the user has permission to access.
    """
    all_docs = db.query(Document).order_by(Document.created_at.desc()).all()
    accessible_docs = []
    
    for doc in all_docs:
        if PermissionService.can_view_document(current_user, doc):
            accessible_docs.append({
                "id": doc.id,
                "filename": doc.filename,
                "department": doc.department,
                "classification": doc.classification,
                "visibility": doc.visibility,
                "approved": doc.approved,
                "owner_id": doc.owner_id,
                "owner_username": doc.owner.username if doc.owner else "Unknown",
                "upload_time": doc.created_at.isoformat() if doc.created_at else doc.upload_time.isoformat()
            })

    return accessible_docs


@router.get("/documents/pending", response_model=List[Dict[str, Any]])
def get_pending_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns list of unapproved documents requiring manager approval in the user's department.
    """
    role = current_user.role.lower()
    if role not in ["super_admin", "department_manager", "team_lead"]:
        raise HTTPException(status_code=403, detail="Only managers and admins can view pending approvals.")

    query_builder = db.query(Document).filter(Document.approved == False)
    if role != "super_admin":
        query_builder = query_builder.filter(Document.department == current_user.department)

    pending_docs = query_builder.order_by(Document.created_at.desc()).all()

    return [{
        "id": doc.id,
        "filename": doc.filename,
        "department": doc.department,
        "classification": doc.classification,
        "visibility": doc.visibility,
        "uploaded_by_username": doc.uploader.username if doc.uploader else "Unknown",
        "created_at": doc.created_at.isoformat()
    } for doc in pending_docs]


@router.post("/documents/{doc_id}/approve", response_model=Dict[str, Any])
def approve_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Approves a pending document, extracts text, chunks it, and indexes into ChromaDB.
    """
    ip = request.client.host if request.client else "127.0.0.1"
    doc = db.query(Document).filter(Document.id == doc_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not PermissionService.can_approve_document(current_user, doc):
        PermissionService.log_audit_event(
            db, current_user, "Approval", "DENIED",
            target_document=doc,
            ip_address=ip,
            details={"reason": "User lacks approval permission for target department"}
        )
        raise HTTPException(status_code=403, detail="Permission denied to approve this document.")

    if doc.approved:
        return {"message": "Document is already approved", "document_id": doc.id}

    # Mark as approved
    doc.approved = True
    doc.approved_by = current_user.id
    doc.approved_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(doc)

    # Chunk and Index into ChromaDB
    chunks_count = 0
    if os.path.exists(doc.file_path):
        raw_text = extract_text(doc.file_path)
        if raw_text.strip():
            chunks = chunk_text(raw_text)
            chunks_count = len(chunks)
            metadatas = []
            ids = []
            for idx, chunk in enumerate(chunks):
                metadatas.append({
                    "document_id": doc.id,
                    "tenant_id": doc.owner_id,
                    "user_id": doc.owner_id,
                    "owner_id": doc.owner_id,
                    "department": doc.department,
                    "team": doc.team or "",
                    "filename": doc.filename,
                    "classification": doc.classification,
                    "visibility": doc.visibility,
                    "approved": True
                })
                ids.append(f"doc_{doc.id}_chunk_{idx}")
            chroma_service.add_chunks(texts=chunks, metadatas=metadatas, ids=ids)

    PermissionService.log_audit_event(
        db, current_user, "Approval", "SUCCESS",
        target_document=doc,
        ip_address=ip,
        details={"chunks_indexed": chunks_count}
    )

    return {
        "message": "Document approved and indexed into ChromaDB successfully.",
        "document_id": doc.id,
        "filename": doc.filename,
        "chunks_indexed": chunks_count
    }


@router.delete("/documents/{doc_id}", response_model=Dict[str, Any])
def delete_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Deletes document record, vector chunks from ChromaDB, and local file.
    """
    ip = request.client.host if request.client else "127.0.0.1"
    doc = db.query(Document).filter(Document.id == doc_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if not PermissionService.can_delete_document(current_user, doc):
        PermissionService.log_audit_event(
            db, current_user, "Delete", "DENIED",
            target_document=doc,
            ip_address=ip
        )
        raise HTTPException(status_code=403, detail="Permission denied to delete this document.")

    # Remove vector chunks from ChromaDB
    chroma_service.delete_by_document(doc.id)

    # Remove file on disk
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not remove file on disk: {e}")

    doc_title = doc.filename
    db.delete(doc)
    db.commit()

    PermissionService.log_audit_event(
        db, current_user, "Delete", "SUCCESS",
        ip_address=ip,
        details={"deleted_document_title": doc_title}
    )

    return {"message": "Document deleted successfully", "document_id": doc_id}


@router.post("/query", response_model=Dict[str, Any])
def execute_query(
    req: QueryRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Executes the multi-agent LangGraph workflow with RBAC context filtering.
    """
    from agents.providers import is_mocked_execution
    is_mocked_execution.set(False)

    start_time = time.time()
    query = req.query
    ip = request.client.host if request.client else "127.0.0.1"
    
    # 1. Check Redis Cache
    cache_key = f"aiflow_cache:user_{current_user.id}:q_{hash(query)}"
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                logger.info(f"Redis cache hit for query: '{query}'")
                AIFLOW_REDIS_CACHE_HITS.inc()
                HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/query", status="200").inc()
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to read from Redis cache: {e}")

    # 1.5 Check ChromaDB Semantic Cache (bypassed during mock embedding testing)
    if settings.EMBEDDING_PROVIDER != "mock":
        try:
            semantic_cached = chroma_service.get_semantic_cache(query, current_user.id)
            if semantic_cached:
                logger.info(f"Serving semantic cache for query: '{query}'")
                return semantic_cached
        except Exception as e:
            logger.warning(f"Failed to read from semantic cache: {e}")

    # 2. Get or Create Conversation thread
    conversation_id = req.conversation_id
    if not conversation_id:
        conversation = Conversation(
            title=f"Chat {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            user_id=current_user.id
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        conversation_id = conversation.id

    # 3. Construct Initial LangGraph Agent State with User RBAC Claims
    initial_state = {
        "query": query,
        "final_response": None,
        "user_id": current_user.id,
        "user_name": current_user.username,
        "user_department": current_user.department,
        "user_role": current_user.role,
        "user_clearance": current_user.clearance_level,
        "plan": [],
        "current_step_index": 0,
        "needs_rag": False,
        "retrieved_documents": [],
        "research_summary": "",
        "next_tool": None,
        "tool_inputs": {},
        "tool_outputs": {},
        "reasoning_output": "",
        "validation_passed": False,
        "validation_feedback": "",
        "confidence_score": 0.0,
        "hallucination_detected": False,
        "validation_attempts": 0,
        "history": [],
        "prompt_tokens": 0,
        "completion_tokens": 0
    }

    try:
        # Run workflow
        final_state = app_graph.invoke(initial_state)
        execution_time_ms = (time.time() - start_time) * 1000

        # Status flag
        status_flag = "success"
        if final_state.get("hallucination_detected", False) or not final_state.get("validation_passed", False):
            status_flag = "validation_failed"

        # Token usage
        prompt_tokens = final_state.get("prompt_tokens", 0)
        completion_tokens = final_state.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens

        # Persist execution trace
        execution_record = WorkflowExecution(
            query=query,
            status=status_flag,
            execution_time_ms=execution_time_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            state_dump=final_state,
            conversation_id=conversation_id
        )
        db.add(execution_record)
        db.commit()
        db.refresh(execution_record)

        final_response = final_state.get("final_response", {})

        payload = {
            "conversation_id": conversation_id,
            "execution_id": execution_record.id,
            "status": status_flag,
            "response": final_response,
            "confidence_score": final_state.get("confidence_score", 1.0),
            "execution_time_ms": round(execution_time_ms, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens
        }

        # Cache only non-mocked executions
        if redis_client and status_flag == "success" and not is_mocked_execution.get():
            try:
                redis_client.setex(cache_key, 600, json.dumps(payload))
            except Exception as e:
                logger.warning(f"Failed to write to Redis cache: {e}")

        if status_flag == "success" and settings.EMBEDDING_PROVIDER != "mock" and not is_mocked_execution.get():
            try:
                chroma_service.set_semantic_cache(query, payload, current_user.id)
            except Exception as e:
                logger.warning(f"Failed to write to semantic cache: {e}")

        PermissionService.log_audit_event(
            db, current_user, "Query", "SUCCESS",
            ip_address=ip,
            details={"tokens": total_tokens, "latency_ms": round(execution_time_ms, 2)}
        )

        AIFLOW_WORKFLOW_EXECUTION.labels(status=status_flag).inc()
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/query", status="200").inc()
        
        return payload

    except Exception as e:
        logger.error(f"Workflow execution crashed: {e}")
        PermissionService.log_audit_event(
            db, current_user, "Query", "FAILED",
            ip_address=ip,
            details={"error": str(e)}
        )
        AIFLOW_WORKFLOW_EXECUTION.labels(status="failed").inc()
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/query", status="500").inc()
        raise HTTPException(status_code=500, detail=f"Workflow run crashed: {str(e)}")


@router.get("/api/admin/dashboard", response_model=Dict[str, Any])
def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Enterprise Admin Dashboard Metrics Cards & Statistics.
    """
    if current_user.role.lower() not in ["super_admin", "department_manager"]:
        raise HTTPException(status_code=403, detail="Admin dashboard restricted to Super Admins & Department Managers.")

    total_users = db.query(func.count(User.id)).scalar() or 0
    pending_approvals = db.query(func.count(Document.id)).filter(Document.approved == False).scalar() or 0
    restricted_docs = db.query(func.count(Document.id)).filter(
        Document.classification.in_(["RESTRICTED", "HIGHLY_CONFIDENTIAL"])
    ).scalar() or 0
    failed_permission_attempts = db.query(func.count(AuditLog.id)).filter(AuditLog.status == "DENIED").scalar() or 0

    # Users per department
    users_by_dept = db.query(User.department, func.count(User.id)).group_by(User.department).all()
    users_per_dept_dict = {dept: count for dept, count in users_by_dept}

    # Documents per department
    docs_by_dept = db.query(Document.department, func.count(Document.id)).group_by(Document.department).all()
    docs_per_dept_dict = {dept: count for dept, count in docs_by_dept}

    # Classification distribution
    class_dist = db.query(Document.classification, func.count(Document.id)).group_by(Document.classification).all()
    classification_dist_dict = {cls_name: count for cls_name, count in class_dist}

    # Recent uploads
    recent_docs = db.query(Document).order_by(Document.created_at.desc()).limit(5).all()
    recent_uploads = [{
        "id": d.id,
        "filename": d.filename,
        "department": d.department,
        "classification": d.classification,
        "uploaded_by": d.uploader.username if d.uploader else "Unknown",
        "created_at": d.created_at.isoformat()
    } for d in recent_docs]

    return {
        "total_users": total_users,
        "pending_approvals": pending_approvals,
        "restricted_documents": restricted_docs,
        "failed_permission_attempts": failed_permission_attempts,
        "users_per_department": users_per_dept_dict,
        "documents_per_department": docs_per_dept_dict,
        "classification_distribution": classification_dist_dict,
        "recent_uploads": recent_uploads
    }


@router.get("/api/audit-logs", response_model=List[Dict[str, Any]])
def get_audit_logs(
    action: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns enterprise audit logs. Restricted to Super Admin & Department Managers.
    """
    if current_user.role.lower() not in ["super_admin", "department_manager"]:
        raise HTTPException(status_code=403, detail="Audit log access restricted.")

    query_builder = db.query(AuditLog)
    if current_user.role.lower() != "super_admin":
        query_builder = query_builder.filter(AuditLog.department == current_user.department)

    if action:
        query_builder = query_builder.filter(AuditLog.action == action)
    if status_filter:
        query_builder = query_builder.filter(AuditLog.status == status_filter)

    logs = query_builder.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return [{
        "id": l.id,
        "timestamp": l.timestamp.isoformat(),
        "username": l.user_username,
        "department": l.department or "N/A",
        "action": l.action,
        "target_document_title": l.target_document_title or "N/A",
        "status": l.status,
        "ip_address": l.ip_address or "127.0.0.1",
        "details": l.details
    } for l in logs]


@router.get("/admin/users", response_model=List[Dict[str, Any]])
def get_users_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns list of users. Super Admin gets all users, Department Manager gets department users.
    """
    if not PermissionService.can_manage_users(current_user):
        raise HTTPException(status_code=403, detail="User management permission denied.")

    query_builder = db.query(User)
    if current_user.role.lower() != "super_admin":
        query_builder = query_builder.filter(User.department == current_user.department)

    users = query_builder.order_by(User.id.asc()).all()
    return [{
        "id": u.id,
        "username": u.username,
        "department": u.department,
        "role": u.role,
        "clearance_level": u.clearance_level,
        "full_name": u.full_name or "N/A",
        "contact_details": u.contact_details or "N/A",
        "email": u.email or "N/A",
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None
    } for u in users]


@router.put("/admin/users/{target_id}", response_model=Dict[str, Any])
def admin_update_user(
    target_id: int,
    user_in: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Admin/Manager function: Higher administration can change employee username, role, department, clearance level, full_name, email, contact details.
    """
    ip = request.client.host if request.client else "127.0.0.1"
    target = db.query(User).filter(User.id == target_id).first()

    if not target:
        raise HTTPException(status_code=404, detail="Target user not found.")

    if not PermissionService.can_manage_users(current_user, target):
        PermissionService.log_audit_event(
            db, current_user, "Admin User Edit", "DENIED",
            ip_address=ip,
            details={"target_id": target_id}
        )
        raise HTTPException(status_code=403, detail="Permission denied to manage target user.")

    # Username edit check
    if user_in.username and user_in.username != target.username:
        existing = db.query(User).filter(User.username == user_in.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Target username already taken.")
        target.username = user_in.username

    if user_in.role and user_in.role.lower() in ROLES:
        target.role = user_in.role.lower()
    if user_in.department and user_in.department in DEPARTMENTS:
        target.department = user_in.department
    if user_in.clearance_level and user_in.clearance_level.upper() in CLASSIFICATIONS:
        target.clearance_level = user_in.clearance_level.upper()
    if user_in.full_name is not None:
        target.full_name = user_in.full_name
    if user_in.contact_details is not None:
        target.contact_details = user_in.contact_details
    if user_in.email is not None:
        target.email = user_in.email
    if user_in.is_active is not None:
        target.is_active = user_in.is_active

    target.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(target)

    PermissionService.log_audit_event(
        db, current_user, "Admin User Edit", "SUCCESS",
        ip_address=ip,
        details={"target_username": target.username, "new_role": target.role}
    )

    return {
        "message": "Employee details updated successfully",
        "user_id": target.id,
        "username": target.username,
        "role": target.role,
        "department": target.department,
        "clearance_level": target.clearance_level,
        "full_name": target.full_name,
        "contact_details": target.contact_details,
        "email": target.email,
        "is_active": target.is_active
    }


@router.delete("/admin/users/{target_id}", response_model=Dict[str, Any])
def admin_delete_user(
    target_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Admin/Manager function: Delete employee account. Restricted strictly to higher administration.
    """
    ip = request.client.host if request.client else "127.0.0.1"
    target = db.query(User).filter(User.id == target_id).first()

    if not target:
        raise HTTPException(status_code=404, detail="Target user not found.")

    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own active admin account.")

    if not PermissionService.can_manage_users(current_user, target):
        PermissionService.log_audit_event(
            db, current_user, "Admin User Delete", "DENIED",
            ip_address=ip,
            details={"target_username": target.username}
        )
        raise HTTPException(status_code=403, detail="Permission denied to delete target user.")

    deleted_username = target.username
    db.delete(target)
    db.commit()

    PermissionService.log_audit_event(
        db, current_user, "Admin User Delete", "SUCCESS",
        ip_address=ip,
        details={"deleted_username": deleted_username}
    )

    return {"message": "User account deleted successfully.", "deleted_username": deleted_username}


@router.get("/workflow/history", response_model=List[Dict[str, Any]])
def get_workflow_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves workflow history and state traces for the authenticated user.
    """
    executions = db.query(WorkflowExecution).join(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(WorkflowExecution.created_at.desc()).all()
    
    history_list = []
    for exe in executions:
        history_list.append({
            "id": exe.id,
            "query": exe.query,
            "status": exe.status,
            "execution_time_ms": exe.execution_time_ms,
            "created_at": exe.created_at.isoformat(),
            "conversation_id": exe.conversation_id,
            "steps_taken": [h.get("node") for h in exe.state_dump.get("history", [])] if exe.state_dump else []
        })
    return history_list


@router.get("/analytics", response_model=Dict[str, Any])
def get_usage_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns role-based usage analytics.
    """
    is_admin = current_user.role.lower() in ["super_admin", "department_manager"]
    
    if is_admin:
        total_queries = db.query(func.count(WorkflowExecution.id)).scalar() or 0
        total_documents = db.query(func.count(Document.id)).scalar() or 0
        
        token_stats = db.query(
            func.sum(WorkflowExecution.prompt_tokens),
            func.sum(WorkflowExecution.completion_tokens),
            func.sum(WorkflowExecution.total_tokens),
            func.avg(WorkflowExecution.execution_time_ms)
        ).first()
        
        total_prompt_tokens = token_stats[0] or 0
        total_completion_tokens = token_stats[1] or 0
        total_tokens = token_stats[2] or 0
        avg_latency = token_stats[3] or 0.0
        
        estimated_cost = ((total_prompt_tokens / 1000000) * 0.075) + ((total_completion_tokens / 1000000) * 0.30)
        
        global_stats = {
            "total_queries": total_queries,
            "total_documents": total_documents,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
            "average_latency_ms": round(avg_latency, 2)
        }
        
        users = db.query(User).all()
        users_stats = []
        for u in users:
            q_count = db.query(func.count(WorkflowExecution.id)).join(Conversation).filter(Conversation.user_id == u.id).scalar() or 0
            d_count = db.query(func.count(Document.id)).filter(Document.user_id == u.id).scalar() or 0
            
            u_token_stats = db.query(
                func.sum(WorkflowExecution.prompt_tokens),
                func.sum(WorkflowExecution.completion_tokens),
                func.sum(WorkflowExecution.total_tokens)
            ).join(Conversation).filter(Conversation.user_id == u.id).first()
            
            u_prompt = u_token_stats[0] or 0
            u_completion = u_token_stats[1] or 0
            u_total = u_token_stats[2] or 0
            
            last_exe = db.query(WorkflowExecution.created_at).join(Conversation).filter(
                Conversation.user_id == u.id
            ).order_by(WorkflowExecution.created_at.desc()).first()
            
            last_active = last_exe[0].isoformat() if last_exe else (u.created_at.isoformat() if u.created_at else "N/A")
            
            users_stats.append({
                "user_id": u.id,
                "username": u.username,
                "role": u.role,
                "department": u.department,
                "query_count": q_count,
                "document_count": d_count,
                "prompt_tokens": u_prompt,
                "completion_tokens": u_completion,
                "total_tokens": u_total,
                "last_active": last_active
            })
            
        return {
            "role": current_user.role,
            "global_stats": global_stats,
            "users_stats": users_stats
        }
    else:
        q_count = db.query(func.count(WorkflowExecution.id)).join(Conversation).filter(Conversation.user_id == current_user.id).scalar() or 0
        d_count = db.query(func.count(Document.id)).filter(Document.user_id == current_user.id).scalar() or 0
        
        u_token_stats = db.query(
            func.sum(WorkflowExecution.prompt_tokens),
            func.sum(WorkflowExecution.completion_tokens),
            func.sum(WorkflowExecution.total_tokens)
        ).join(Conversation).filter(Conversation.user_id == current_user.id).first()
        
        u_prompt = u_token_stats[0] or 0
        u_completion = u_token_stats[1] or 0
        u_total = u_token_stats[2] or 0
        
        executions = db.query(WorkflowExecution).join(Conversation).filter(
            Conversation.user_id == current_user.id
        ).order_by(WorkflowExecution.created_at.desc()).all()
        
        history = [{
            "id": exe.id,
            "query": exe.query,
            "status": exe.status,
            "prompt_tokens": exe.prompt_tokens,
            "completion_tokens": exe.completion_tokens,
            "total_tokens": exe.total_tokens,
            "execution_time_ms": round(exe.execution_time_ms, 2),
            "created_at": exe.created_at.isoformat()
        } for exe in executions]
        
        return {
            "role": "user",
            "stats": {
                "query_count": q_count,
                "document_count": d_count,
                "prompt_tokens": u_prompt,
                "completion_tokens": u_completion,
                "total_tokens": u_total
            },
            "history": history
        }


@router.get("/metrics")
def get_metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health")
def get_health(db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
        
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": time.time()
    }
