# NexusFlow -- Enterprise Multi-Agent AI Workflow Orchestrator

NexusFlow is a production-grade enterprise AI orchestration platform inspired by corporate consulting workflows. It implements reusable backend services utilizing **FastAPI**, **LangGraph**, **ChromaDB** for RAG, **PostgreSQL** (or SQLite) for persistence, **Redis** for caching, and **OpenTelemetry + Prometheus + Grafana** for monitoring and observability.

The platform is upgraded with **Enterprise Role-Based Access Control (RBAC)**, **Department-Based Document Isolation**, **Clearance Level Matrices**, **Document Approval Workflows**, **Self-Service Employee Settings**, **Admin Employee Control Panels**, and **Security Audit Logging**.

---

## Architecture Diagram

```
                       React Frontend / REST Client
                                    │
                                    ▼
                                 FastAPI
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
          Redis Cache                           PostgreSQL (Auth, Trace & Audit DB)
                │                                       │
                └───────────────────┬───────────────────┘
                                    │
                                    ▼
                        LangGraph Multi-Agent Engine
                                    │
    ┌──────────────┬────────────────┴──┬───────────────────┬────────────────┐
    │              │                   │                   │                │
    ▼              ▼                   ▼                   ▼                ▼
Planner   ──►  Retriever   ──►   Tool Agent   ──►       Reasoner  ──►   Validator
Node           Node              Node                   Node            Node
               (RBAC Metadata                           (Math, SQL,     (Hallucination &
                Pre-Filtering)                           REST, Python)   Compliance Check)
                    │
                    ▼
                ChromaDB
               Vector DB
```

### Multi-Agent Workflow State Machine
1. **Planner Agent**: Analyzes user prompt and generates a step-by-step plan, deciding if RAG context retrieval is required.
2. **Retriever Agent (RAG)**: Fetches relevant text chunks from the vector database using similarity searches (supporting strict department and clearance metadata pre-filtering).
3. **Researcher Agent**: Synthesizes and condenses the raw retrieved passages into structured context.
4. **Tool Agent**: Safely executes specialized tools (Python Code Execution, SQL Querying, REST HTTP calls, and Mathematical calculations) according to plan directives.
5. **Reasoner Agent**: Integrates facts, tool results, and plan milestones to compose a comprehensive draft answer.
6. **Validator Agent**: Inspects the response for hallucinations, compliance issues, and correctness. On failure, triggers a loop to correct errors.
7. **Response Agent**: Formulates a clean JSON output containing structured results, citations, and actionable recommendations.

---

## Directory Structure

```text
backend/
├── api/
│   ├── config.py           # Settings configuration loading from .env
│   ├── deps.py             # Auth dependencies, Pydantic request models & require_roles
│   ├── endpoints.py        # REST API endpoints (register, upload, query, approvals, profile, etc.)
│   └── security.py         # Password hashing (bcrypt) & JWT claims generation
├── database/
│   ├── database.py         # SQLAlchemy connection engine
│   └── models.py           # Tables for User, Document, AuditLog, Conversation, and Workflow
├── services/
│   └── permission_service.py # [NEW] Centralized Authorization Engine & Clearance matrices
├── agents/
│   ├── graph.py            # LangGraph StateGraph compilation
│   ├── nodes.py            # Individual node execution handlers (RBAC Retriever filter integration)
│   ├── providers.py        # Gemini 2.0 & Mock LLM providers
│   └── state.py            # AgentState and output schemas
├── rag/
│   ├── chroma_service.py   # Vector collection search, insert, and semantic caching
│   └── document_processor.py # PDF/TXT file parser and chunk splitters
├── static/
│   ├── index.html          # Dark Theme UI Dashboard (forms for RBAC parameters)
│   ├── style.css           # Glowing glassmorphic styling & classification pills
│   └── app.js              # Frontend controller (Auth, Uploads, Chat, Profile, Approvals, Admin)
├── tools/
│   ├── __init__.py         # Tools exports registry
│   ├── base_tool.py        # Tool base definition class
│   ├── calculator.py       # AST expression math evaluator
│   ├── python_executor.py  # Sandboxed Python executor
│   ├── rest_client.py      # HTTP request tool
│   └── sql_runner.py       # Read-only database query tool
├── monitoring/
│   ├── telemetry.py        # OpenTelemetry setup and Prometheus gauges
│   ├── prometheus.yml      # Prometheus scraper rules
│   ├── grafana_datasources.yml # Grafana Prometheus configuration
│   ├── grafana_dashboards.yml  # Grafana dashboard provider
│   └── dashboards/
│       └── dashboard.json  # Pre-built monitoring metrics layout
├── tests/                  # Pytest unit and integration test suite
├── Dockerfile              # Container specifications
├── docker-compose.yml      # Orchestration compose file
└── requirements.txt        # Backend dependencies
```

---

## Key Features & Security Enhancements

### 1. Enterprise Role-Based Access Control (RBAC) & Clearance Matrix
*   **Security Clearance Levels (5):** `PUBLIC` (1) < `INTERNAL` (2) < `CONFIDENTIAL` (3) < `RESTRICTED` (4) < `HIGHLY_CONFIDENTIAL` (5).
*   **Corporate Role Privileges (5):**
    *   `super_admin`: Full clearance (`HIGHLY_CONFIDENTIAL`). Complete platform, audit, and user management.
    *   `department_manager`: Clearance up to `RESTRICTED`. Approves department employee documents and manages department users.
    *   `team_lead`: Clearance up to `CONFIDENTIAL`. Manages team uploads and approves team-level documents.
    *   `employee`: Clearance up to `INTERNAL`. Can upload documents (requires approval) and run queries.
    *   `guest`: Clearance limited to `PUBLIC`. Read-only access to public organization documents (cannot upload).

### 2. Department-Based Document Isolation
*   Vector similarity searches filter out unauthorized chunks *before* similarity score calculations based on the user's department, role clearance level, and the document's classification.
*   If a search query fails to retrieve authorized documents, the system returns a secure fallback: `"No accessible documents found."` without revealing the existence of restricted documents.

### 3. Document Ingestion Approval Pipeline
*   Documents uploaded by `employee` and `team_lead` users are flagged as `approved = False` (Pending Approval) and **are skipped from ChromaDB vector indexing**.
*   Department Managers and Super Admins can review pending department uploads on their **Pending Approvals** dashboard and click **Approve** to extract text, chunk, and index them into ChromaDB.

### 4. Self-Service Settings & Profile Customizations
*   Every user can manage their profile: edit **Full Name**, **Work Email**, **Contact Details**, and change their account **Password** directly from the portal.

### 5. Higher Administration Control Panel
*   Only **Super Admins** and **Department Managers** can edit other employees' usernames, roles, department associations, clearance levels, active status, or delete employee accounts.

### 6. Immutable Security Audit Trail
*   All user registrations, logins, file uploads, document approvals, deletion requests, and query executions are tracked in the database `AuditLog` table, complete with timestamps, statuses, and client IP addresses.

---

## Setup & Run Local Services

### Prerequisites
*   Python 3.11 / 3.13
*   Docker & Docker Compose

### 1. Configure Environment Variables
Create a `.env` file in the `backend/` directory:
```env
DATABASE_URL=sqlite:///./aiflow.db
REDIS_URL=redis://localhost:6379/0
CHROMA_DB_PATH=./chroma_db
JWT_SECRET=supersecretjwtsignkeyvalue1122334455
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.0-flash
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
EMBEDDING_PROVIDER=local # Toggle: local / gemini
```

### 2. Reset Database & Seed Corporate Accounts
Run the seed script locally to recreate database tables, seed the 33 corporate role accounts, and index 24 department documents:
```bash
cd backend
python seed.py
```
> [NOTE]
> All seeded accounts share the universal password: `Password123!` (e.g. `finance.manager@nexusflow.ai`, `eng.employee@nexusflow.ai`, `admin@nexusflow.ai`). Refer to [corporate_credentials.md](./corporate_credentials.md) for the complete list.

### 3. Run Backend Locally
```bash
# Install requirements
pip install -r requirements.txt

# Start local server
python main.py
```
*   **FastAPI Dashboard UI:** `http://localhost:8000/ui/`
*   **Swagger API Specs:** `http://localhost:8000/docs`

---

## Running Tests
Run backend tests using Pytest (SQLite in-memory overrides are loaded automatically to run tests in isolation):
```bash
$env:PYTHONPATH="backend"
python -m pytest backend/tests/ -v
```
