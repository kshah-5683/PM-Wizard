# AI-Driven Product Management & Engineering Middleware (PM Wizard)

An intelligent, stateful middleware layer designed to bridge the gap between Product Managers and Developers. PM Wizard natively translates high-level Product Requirement Documents (**Notion, Confluence, PDFs, Word docs, images/wireframes**) into codebase-aware, estimated sprint plans synchronized directly to developer backlogs (**Atlassian Jira Cloud**).

---

## 🚀 Core Features & Agentic Architecture

* **Multi-Source Requirement Ingestion & Document Resolvers:**
  - Drag-and-drop file parser supporting `.pdf`, `.docx`, `.txt`, `.md`, and vision-based image/wireframe transcription ([middleware/document_parser.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/document_parser.py)).
  - Upstream URL auto-resolution with live markdown preview for **Notion** and **Confluence** pages ([middleware/integration_fetcher.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/integration_fetcher.py)).
* **Greenfield vs. Brownfield Planning Modes:**
  - Auto-detects Greenfield repositories (or empty codebases) to generate foundational architectural and database blueprints with variance guardrail banners.
* **Dual-Checklist Compliance Auditor (Critic Node):**
  - Audits PRDs against mandatory base rules and customizable optional compliance checklists ([middleware/critic_rules.json](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/critic_rules.json)).
  - Pauses execution via stateful LangGraph `interrupt()` on `CRITICAL` blockers until human PRD amendment or EM bypass.
* **Structured Scrum Master Estimator:**
  - Outputs Fibonacci story points, `parent_key` (Epic linking), `blocked_by` dependencies, estimation confidence levels (`HIGH`, `MEDIUM`, `LOW`), and rationales.
  - Leverages Vector-Time Graph RAG to retrieve historical reference tickets from Supabase `pgvector`.
* **DAG Dependency Validator & Cycle Pruning:**
  - Standalone DFS cycle-detection utility ([middleware/dag_validator.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/dag_validator.py)) that auto-prunes circular dependency loops and orphan ticket references.
* **Human-in-the-Loop Review Gate & Circuit Breakers:**
  - Stateful EM approval checkpoint supporting approval, a hard 3-revision turn circuit breaker ([middleware/graph.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/graph.py)), and in-place ticket CRUD (`"edit_and_approve"`).
* **Atlassian Jira Cloud Sync:**
  - Idempotent ticket publishing (`jira_issue_id`), dynamic parent Epic creation and linking, ADF document formatting, and developer change request merging ([middleware/nodes/sync.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/nodes/sync.py)).
* **Developer Technical Specification & Scaffolding Agent:**
  - Generates lightweight file-level target paths (`src/...`) and step-by-step developer checklists ([middleware/tech_spec_generator.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/tech_spec_generator.py)), auto-posting them as markdown comments on published Jira issues.
* **Retrospective Velocity Calibrator Agent:**
  - Computes actual vs. planned velocity multipliers from closed Jira sprints ([middleware/velocity_calibrator.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/middleware/velocity_calibrator.py)) and injects prompt callouts for self-learning estimation calibration.
* **Production Authentication & Role-Based Access Control:**
  - Supabase JWT authentication, multi-tenant role-based permissions (PM, EM, DEV), and optimistic HTTP 409 status locking on graph resumptions ([server.py](file:///C:/Users/Khushi%20Shah/Documents/GitHub/PM-Tool/server.py)).

---

## 📁 Repository Structure

```
PM-Tool/
├── middleware/                    # Core LangGraph state machine & AI agent engine
│   ├── config.py                  # Global settings, model identifiers & thresholds
│   ├── state.py                   # AgentState TypedDict & Pydantic schemas (JiraTicket, SprintPlan)
│   ├── graph.py                   # StateGraph compiler, routing logic & circuit breakers
│   ├── dag_validator.py           # DFS dependency cycle detection & orphan reference pruner
│   ├── tech_spec_generator.py     # Developer technical spec & scaffolding agent
│   ├── velocity_calibrator.py     # Closed sprint velocity calculator & prompt calibrator
│   ├── document_parser.py         # Multi-format document & vision diagram parser
│   ├── integration_fetcher.py     # Notion & Confluence upstream URL resolvers
│   ├── oauth.py                   # Encrypted OAuth connectivity (Notion, GitHub, Atlassian)
│   ├── rag.py                     # Supabase pgvector embedding search & blueprint retriever
│   ├── critic_rules.json          # Compliance audit checklists (Base + Optional)
│   └── nodes/                     # Modular async LangGraph worker nodes
│       ├── ingester.py            # Codebase profiling, stack scanning & Greenfield blueprinting
│       ├── critic.py              # Compliance auditor & gap evaluator
│       ├── critic_resolution.py   # Stateful PRD blocker resolution interrupt gate
│       ├── estimator.py           # Scrum Master estimator with Fibonacci guardrails & DAG checks
│       ├── human_approval.py      # EM review gate & in-place ticket CRUD handler
│       └── sync.py                # Idempotent Jira Cloud backlog publisher & comment sync
├── frontend/                      # Next.js 14 web application (Vercel ready)
│   └── src/app/                   # Role-tailored dashboards (PM, EM, DEV)
├── tests/                         # Comprehensive unit & integration test suite (68 tests)
│   ├── conftest.py                # Pytest path resolution helper
│   ├── test_workflow_circuit_breaker.py
│   ├── test_dag_validator.py
│   ├── test_tech_spec_generator.py
│   ├── test_velocity_calibrator.py
│   ├── test_critic_gating.py
│   ├── test_estimator_guardrails.py
│   ├── test_jira_publishing.py
│   ├── test_server_routes.py
│   └── ...
├── server.py                      # Production FastAPI REST backend server
├── run_sandbox.py                 # Interactive CLI driver for local testing
├── requirements.txt               # Backend Python dependencies
├── Changelog.md                   # Automated record of all feature releases
└── discussion_notes.md            # Technical design decision history
```

---

## ⚙️ Environment Configuration

Copy `.env.example` to `.env` and configure the required credentials:

```env
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
FERNET_ENCRYPTION_KEY=your_fernet_secret_key
ATLASSIAN_CLIENT_ID=your_atlassian_client_id
ATLASSIAN_CLIENT_SECRET=your_atlassian_client_secret
NOTION_CLIENT_ID=your_notion_client_id
NOTION_CLIENT_SECRET=your_notion_client_secret
```

---

## 🎮 How to Run

### 1. Run Backend Server (FastAPI)
```bash
uvicorn server:app --reload --port 8000
```

### 2. Run Frontend Dashboard (Next.js)
```bash
cd frontend
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### 3. Run Interactive CLI Sandbox
```bash
python run_sandbox.py
```

### 4. Run Test Suite
```bash
python -m unittest discover -s tests
# or
pytest tests/
```
