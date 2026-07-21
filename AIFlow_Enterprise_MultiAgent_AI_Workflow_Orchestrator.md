# NexusFlow -- Enterprise Multi-Agent AI Workflow Orchestrator

## Overview

NexusFlow is a production-oriented enterprise AI orchestration platform inspired by professional consulting environments. Rather than a simple chatbot, it provides reusable AI workflows built with Python, FastAPI, LangGraph, Retrieval-Augmented Generation (RAG), tool calling, structured outputs, security clearances, department isolation, approval workflows, self-service settings, observability, and evaluation.

## Objectives

- Build reusable AI backend services.
- Orchestrate multiple AI agents with LangGraph.
- Support enterprise RAG over uploaded documents with strict role-based and department-based isolation.
- Provide secure REST APIs with JWT claims.
- Enable employee self-service settings (profile edits, password resets).
- Enable administrator user control panels (username changes, deletion, role assignment).
- Persist workflow history and security audit logs.
- Monitor latency, cost, and reliability.
- Containerized deployment.

## High-Level Architecture

``` text
React Frontend
      |
   FastAPI
      |
+-------------------------------+
| Authentication (JWT Claims)   |
| Permission Engine (RBAC)      |
| Document Approval Workflow    |
| Self-Service Profile & Pwd    |
| Admin User Control Panel      |
| Workflow & Agent APIs         |
+-------------------------------+
      |
+-------------------------------+
| LangGraph Workflow Engine     |
+-------------------------------+
      |
 Planner -> Retriever (RBAC Filter) -> Tools -> Reasoner -> Validator -> Responder
      |
RAG (ChromaDB + Embeddings)
      |
PostgreSQL/SQLite + Redis + AuditLog DB
      |
Prometheus + Grafana + OpenTelemetry
```

## Workflow

``` text
User Query
 ↓
Planner Agent
 ↓
Retriever Agent (Strict pre-filtering by Department & Clearance level)
 ↓
Research / Context Builder
 ↓
Tool Calling (Python sandbox, SQL, REST, Calculator)
 ↓
Reasoning Agent
 ↓
Validator Agent (Hallucination check)
 ↓
Response Agent
 ↓
Structured JSON (citations & recommendations)
 ↓
Database (Trace logs & Audit trails)
```

## Folder Structure

``` text
backend/
├── api/             # REST endpoints, config, JWT security, auth dependencies
├── agents/          # AgentState, LangGraph orchestrator, node handlers
├── database/        # Database setup and SQLAlchemy User, Document, AuditLog schemas
├── services/        # Permission Engine (clearance ranks & role rules)
├── rag/             # ChromaDB vector store services & document processors
├── static/          # Enterprise glassmorphic dark theme browser UI
├── tools/           # Custom sandboxed tools (Python, SQL, REST, Calc)
├── tests/           # Full Pytest unit and integration test suite
├── Dockerfile
└── docker-compose.yml
```

## Agents

### Planner

Determines workflow, required tools, and whether RAG is needed.

### Retriever

Queries vector database and returns ranked context, utilizing strict RBAC metadata filters (`approved = True`, `department`, `classification <= user clearance`, `visibility`).

### Researcher

Summarizes retrieved evidence.

### Tool Agent

Invokes SQL, Python, APIs, calculator, or search tools.

### Reasoner

Synthesizes all available information.

### Validator

Checks confidence, schema compliance, and hallucination risk.

### Response Agent

Returns structured JSON with citations and recommendations.

## RAG Pipeline

``` text
Upload Documents (with Department, Classification, Visibility metadata)
      ↓
Check Approval Status (Super Admin / Manager auto-approves; Employee pending)
      ↓
Approve Document (Manager / Admin approval indices text into ChromaDB)
      ↓
Chunk & Embed
      ↓
ChromaDB
      ↓
Similarity Search (with strict Department & Clearance pre-filtering)
      ↓
Reranking & Context Assembly
      ↓
LLM Reasoner
```

## REST APIs

-   POST /register (with department and role parameters)
-   POST /login (returns JWT with role and clearance claims)
-   GET /me (returns profile details)
-   PUT /me/profile (self-service name, email, contact details update)
-   PUT /me/password (self-service password reset)
-   POST /upload (with department, classification, visibility parameters)
-   GET /documents (access-controlled document library list)
-   GET /documents/pending (manager pending approval list)
-   POST /documents/{id}/approve (approve and index vector chunks)
-   DELETE /documents/{id} (delete file and vector chunks)
-   POST /query (multi-agent RAG workflow query run)
-   GET /api/admin/dashboard (admin metric cards)
-   GET /api/audit-logs (immutable audit log trail)
-   GET /admin/users (admin user listing)
-   PUT /admin/users/{id} (admin username, role, and clearance management)
-   DELETE /admin/users/{id} (admin user deletion)
-   GET /metrics & /health

## Database Tables

-   `users` (username, hashed_password, role, department, clearance_level, full_name, email, contact_details, is_active)
-   `documents` (filename, file_path, department, owner_id, classification, visibility, approved, approved_by, approved_at)
-   `audit_logs` (timestamp, user_username, department, action, status, target_document_title, ip_address, details)
-   `conversations` & `workflow_executions`

## Enterprise Features

-   JWT Authentication with Custom Claims
-   Clearance Matrix & Role Permissions
-   Department-Isolated Document RAG
-   Document Approval Pipelines
-   Self-Service Profile Customization
-   Admin User Control Center
-   Prometheus & Grafana Observability
-   Immutable Audit Trailing
-   Redis Caching & Semantic Caching
-   Pytest Integration Suite

## Tech Stack

  Layer        Technology
  ------------ ----------------------
  Language     Python
  Backend      FastAPI
  Workflow     LangGraph
  LLM          Gemini
  Vector DB    ChromaDB
  Database     PostgreSQL / SQLite
  Cache        Redis & ChromaDB Cache
  Monitoring   Prometheus + Grafana
  Deployment   Docker
