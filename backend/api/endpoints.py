import os
import time
import json
import redis
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from loguru import logger
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.config import settings
from api.deps import get_db, get_current_user, UserCreate, Token, QueryRequest, WorkflowRunRequest
from api.security import verify_password, get_password_hash, create_access_token
from database.models import User, Document, Conversation, WorkflowExecution
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
    # Ping to check connection
    redis_client.ping()
    logger.info("Successfully connected to Redis cache.")
except Exception as e:
    logger.warning(f"Could not connect to Redis. Caching will be bypassed. Error: {e}")
    redis_client = None


@router.post("/register", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user_in.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    hashed_password = get_password_hash(user_in.password)
    role = "admin" if user_in.username.lower() == "admin" or user_in.role == "admin" else "user"
    user = User(username=user_in.username, hashed_password=hashed_password, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "User registered successfully", "id": str(user.id)}


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(subject=user.username)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/upload", response_model=Dict[str, Any])
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Accepts file uploads, chunks content, and adds vectors to ChromaDB.
    """
    start_time = time.time()
    logger.info(f"Uploading file: {file.filename} for user: {current_user.username}")
    
    # Create uploads directory if not exists
    os.makedirs("./uploads", exist_ok=True)
    file_path = os.path.join("./uploads", f"{current_user.id}_{int(time.time())}_{file.filename}")
    
    # Save file locally
    try:
        with open(file_path, "wb") as f:
            f.write(file.file.read())
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Could not save file payload.")
        
    try:
        # Extract text content
        raw_text = extract_text(file_path)
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="Uploaded file is empty or text extraction failed.")
            
        # Insert metadata in PostgreSQL
        doc_record = Document(
            filename=file.filename,
            file_path=file_path,
            content_type=file.content_type,
            user_id=current_user.id
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)
        
        # Chunk text
        chunks = chunk_text(raw_text)
        
        # Generate metadata and IDs for vector store insertion
        metadatas = []
        ids = []
        for idx, chunk in enumerate(chunks):
            metadatas.append({
                "document_id": doc_record.id,
                "user_id": current_user.id,
                "filename": file.filename
            })
            ids.append(f"doc_{doc_record.id}_chunk_{idx}")
            
        # Index in ChromaDB
        chroma_service.add_chunks(texts=chunks, metadatas=metadatas, ids=ids)
        
        # Record metrics
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/upload", status="200").inc()
        
        return {
            "message": "File indexed successfully",
            "document_id": doc_record.id,
            "filename": file.filename,
            "chunks_count": len(chunks),
            "latency_ms": round((time.time() - start_time) * 1000, 2)
        }
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}")
        # Clean up file on failure
        if os.path.exists(file_path):
            os.remove(file_path)
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/upload", status="500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=Dict[str, Any])
def execute_query(
    req: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Executes the multi-agent LangGraph workflow.
    Utilizes Redis cache for repeated queries.
    """
    from agents.providers import is_mocked_execution
    is_mocked_execution.set(False)
    
    start_time = time.time()
    query = req.query
    
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
        conv = Conversation(title=f"Chat: {query[:30]}...", user_id=current_user.id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id
    else:
        # Verify conversation belongs to user
        conv = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

    # 3. Initialize Agent State
    initial_state = {
        "query": query,
        "user_id": current_user.id,
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
        "final_response": None
    }

    # 4. Invoke LangGraph Workflow
    try:
        logger.info(f"Invoking multi-agent workflow for user {current_user.username}")
        # Graph execution is synchronous
        final_state = app_graph.invoke(initial_state)
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        status_flag = "success"
        if final_state.get("hallucination_detected", False) or not final_state.get("validation_passed", False):
            status_flag = "validation_failed"
            AIFLOW_AGENT_FAILURES.inc()
            
        final_response = final_state.get("final_response") or {
            "structured_answer": {"error": "Failed to compile response"},
            "explanation": final_state.get("reasoning_output", "No response generated."),
            "citations": [],
            "recommendations": []
        }
        
        prompt_tokens = final_state.get("prompt_tokens", 0)
        completion_tokens = final_state.get("completion_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens
        
        # 5. Persist workflow execution log in Postgres
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

        # Compile final payload
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
        
        # 6. Store in Redis Cache (only for non-mocked execution)
        if redis_client and status_flag == "success" and not is_mocked_execution.get():
            try:
                # Cache for 10 minutes (600 seconds)
                redis_client.setex(cache_key, 600, json.dumps(payload))
            except Exception as e:
                logger.warning(f"Failed to write to Redis cache: {e}")

        # 6.5 Store in ChromaDB Semantic Cache (bypassed during mock testing/fallback)
        if status_flag == "success" and settings.EMBEDDING_PROVIDER != "mock" and not is_mocked_execution.get():
            try:
                chroma_service.set_semantic_cache(query, payload, current_user.id)
            except Exception as e:
                logger.warning(f"Failed to write to semantic cache: {e}")

        # Update telemetry
        AIFLOW_WORKFLOW_EXECUTION.labels(status=status_flag).inc()
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/query", status="200").inc()
        
        return payload

    except Exception as e:
        logger.error(f"Workflow execution crashed: {e}")
        AIFLOW_WORKFLOW_EXECUTION.labels(status="failed").inc()
        HTTP_REQUESTS_TOTAL.labels(method="POST", handler="/query", status="500").inc()
        raise HTTPException(status_code=500, detail=f"Workflow run crashed: {str(e)}")


@router.post("/workflow", response_model=Dict[str, Any])
def custom_workflow(
    req: WorkflowRunRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Initiates custom agent sequence setups.
    """
    logger.info(f"Custom workflow request: run nodes {req.agent_nodes}")
    return {
        "status": "custom_nodes_simulated",
        "nodes_requested": req.agent_nodes,
        "query": req.query
    }


@router.post("/agent/run", response_model=Dict[str, Any])
def run_agent_node(
    node_name: str = Form(...),
    query: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """
    Directly invokes a single agent node in isolation (useful for evaluation/debugging).
    """
    from agents.nodes import planner_node, retriever_node, researcher_node, tool_node, reasoner_node, validator_node, responder_node
    
    mock_state = {
        "query": query,
        "user_id": current_user.id,
        "plan": ["Retrieve context"],
        "current_step_index": 0,
        "needs_rag": True,
        "retrieved_documents": [{"id": 1, "document": "Mock context content", "metadata": {}}],
        "research_summary": "Mock context content summary.",
        "next_tool": None,
        "tool_inputs": {},
        "tool_outputs": {},
        "reasoning_output": "Mock reasoning statement.",
        "validation_passed": True,
        "validation_feedback": "Looks good.",
        "confidence_score": 0.95,
        "hallucination_detected": False,
        "validation_attempts": 0,
        "history": [],
        "final_response": None
    }
    
    node_map = {
        "planner": planner_node,
        "retriever": retriever_node,
        "researcher": researcher_node,
        "tool": tool_node,
        "reasoner": reasoner_node,
        "validator": validator_node,
        "responder": responder_node
    }
    
    selected_node = node_name.lower().strip()
    if selected_node not in node_map:
        raise HTTPException(status_code=400, detail=f"Unknown node name: {node_name}")
        
    try:
        node_result = node_map[selected_node](mock_state)
        return {
            "node_executed": selected_node,
            "result_state": node_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow/history", response_model=List[Dict[str, Any]])
def get_workflow_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves workflow history and state traces for the authenticated user.
    """
    logger.info(f"Retrieving execution history for user: {current_user.username}")
    
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
            # Truncate history traces to reduce size if requested, or send full dump
            "steps_taken": [h.get("node") for h in exe.state_dump.get("history", [])] if exe.state_dump else []
        })
    return history_list


@router.get("/analytics", response_model=Dict[str, Any])
def get_usage_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns usage analytics. 
    Admin role can see global platform statistics + breakdown per user.
    Regular role can only see their own usage summary.
    """
    from sqlalchemy import func
    
    is_admin = current_user.role == "admin"
    
    if is_admin:
        # 1. Global statistics across all users
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
        
        # Calculate estimated billing cost ($0.075/1M input, $0.30/1M output)
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
        
        # 2. Detailed statistics breakdown per user
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
            
            last_active = last_exe[0].isoformat() if last_exe else u.created_at.isoformat()
            
            users_stats.append({
                "user_id": u.id,
                "username": u.username,
                "role": u.role,
                "query_count": q_count,
                "document_count": d_count,
                "prompt_tokens": u_prompt,
                "completion_tokens": u_completion,
                "total_tokens": u_total,
                "last_active": last_active
            })
            
        return {
            "role": "admin",
            "global_stats": global_stats,
            "users_stats": users_stats
        }
        
    else:
        # Regular user view
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
        
        # User query log history
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
    """
    Prometheus metrics scraping endpoint.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health")
def get_health(db: Session = Depends(get_db)):
    """
    Health check. Checks db status.
    """
    from sqlalchemy import text
    try:
        # Try a simple DB query
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
        
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "timestamp": time.time()
    }
