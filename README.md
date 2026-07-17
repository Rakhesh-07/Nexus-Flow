# NexusFlow -- Enterprise Multi-Agent AI Workflow Orchestrator

NexusFlow is a production-grade enterprise AI orchestration platform inspired by corporate consulting workflows. It implements reusable backend services utilizing **FastAPI**, **LangGraph**, **ChromaDB** for RAG, **PostgreSQL** for persistence, **Redis** for caching, and **OpenTelemetry + Prometheus + Grafana** for monitoring and observability.

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
          Redis Cache                           PostgreSQL (Auth & Trace DB)
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
                   │                   │                                    │
                   ▼                   ▼                                    ▼
               ChromaDB          Tool Executions:                      (Hallucination
              Vector DB          - Python, SQL, REST, Calc              & Compliance Check)
```

### Multi-Agent Workflow State Machine
1. **Planner Agent**: Analyzes user prompt and generates a step-by-step plan, deciding if RAG context retrieval is required.
2. **Retriever Agent (RAG)**: Fetches relevant text chunks from the vector database using similarity searches (supporting tenant isolation via user ID).
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
│   ├── deps.py             # Auth dependencies & Pydantic request models
│   ├── endpoints.py        # REST API endpoints (register, upload, query, health, etc.)
│   └── security.py         # Password hashing (bcrypt) & JWT generation
├── database/
│   ├── database.py         # SQLAlchemy connection engine
│   └── models.py           # Tables for User, Document, Conversation, and Workflow
├── agents/
│   ├── graph.py            # LangGraph StateGraph compilation
│   ├── nodes.py            # Individual node execution handlers
│   ├── providers.py        # Gemini 2.0 & Mock LLM providers
│   └── state.py            # AgentState and output schemas
├── rag/
│   ├── chroma_service.py   # Vector collection search, insert, and semantic caching
│   └── document_processor.py # PDF/TXT file parser and chunk splitters
├── static/
│   ├── index.html          # Dark Theme UI Dashboard
│   ├── style.css           # Glowing glassmorphic styling
│   └── app.js              # Frontend controller (Auth, Uploads, Chat, Analytics)
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

### 1. Professional Dark UI Dashboard (`/` & `/ui/`)
* **Interactive Chat Swarm:** Send queries and watch real-time steps progress. Chat bubbles show formatted response answers, citations, execution times, and precise token calculations.
* **Multi-File Uploader:** Drag-and-drop zone supporting bulk ingestion of `.pdf`, `.txt`, and `.md` documents, detailing file status and indexing completion confirmations.

### 2. Role-Based Usage Analytics
* **Admins/Managers View:** Gain global visibility over system operations, displaying total queries, files ingested, average execution latencies, total token consumption, and estimated platform billing ($0.075/1M input, $0.30/1M output tokens). Includes an individual breakdown table showing every registered user's query count, token usage, and last-active timestamp.
* **Standard Users View:** Private dashboard showing personal stats, queries executed, and a chronologically detailed personal query history table.

### 3. Industry-Level Security Implementations
* **Multi-Tenant RAG Isolation:** All vector indexing and similarity searches filter strictly by the user's authenticated `user_id`. Users can never query or view files uploaded by other accounts.
* **Secure Auth Gateway:** Implements JSON Web Tokens (JWT) for session management with hashing of passwords using `bcrypt` and salt factors.
* **Auto-Fill & Credential Protection:** Forms use specific input configuration attributes (`autocomplete="off"` and `autocomplete="new-password"`) and programmatic DOM `.reset()` triggers on authentication events (logout, login, register) to prevent browser credential retention.
* **SQL Injection & AST Sandboxing:** Safe querying via SQLAlchemy ORM parameterization and sandboxed Python AST code execution.

### 4. Low-Cost Semantic Caching
* **Local Similarity Storage:** Utilizes local ChromaDB persistence collection `aiflow_cache` to store user queries and response payloads.
* **Cosine Similarity Checks:** If a question matching a similarity distance `< 0.15` is submitted, it returns the cached response in **under 50ms at $0 cost**, bypassing LLM and agent runs.
* **Mock-Aware Bypassing:** Integrated async-safe context variable indicators that prevent mocked/fallback outputs (e.g., when the key hits rate limits) from contaminating cache collections.

### 5. Gemini 2.0 & Schema Compliance
* Pre-configured for `gemini-2.0-flash` models.
* Strips invalid default schema fields recursively from Pydantic structures to avoid `Unknown field for Schema: default` errors on Google Generative Language API calls.

---

## Technology Stack

* **Language**: Python 3.11 / 3.13
* **API Layer**: FastAPI
* **Orchestration**: LangGraph
* **Relational DB**: PostgreSQL / SQLite
* **Caching**: Redis
* **Vector DB**: ChromaDB
* **Observability**: OpenTelemetry + Prometheus + Grafana
* **Environment**: Docker & Docker Compose

---

## Setup & Run Local Services

### Prerequisites
* Python 3.11 / 3.13
* Docker & Docker Compose

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

### 2. Standup Containers (Docker Compose)
From the `backend/` directory, launch Postgres, Redis, Prometheus, Grafana, and AIFlow:
```bash
docker compose up --build -d
```
Once run:
* **FastAPI Server**: `http://localhost:8000` (UI Dashboard at `http://localhost:8000/ui/`)
* **Prometheus Dashboard**: `http://localhost:9090`
* **Grafana Dashboard**: `http://localhost:3000` (Default credentials: `admin` / `admin`)

### 3. Run Backend Locally (Without Containers)
To develop and run Python code directly:
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Start local dev server
python main.py
```

---

## Running Tests
Run backend tests using Pytest (SQLite in-memory overrides are loaded automatically to run tests in isolation):
```bash
$env:PYTHONPATH="backend"
python -m pytest backend/tests/ -v
```
