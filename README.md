# AI-Driven Product Management & Engineering Middleware

An intelligent middleware layer designed to bridge the gap between business planning and engineering execution. This tool natively connects upstream requirement documents (**Notion, Confluence, Google Docs**) with downstream developer backlogs (**Jira, Linear, GitHub**), translating high-level PRDs into codebase-aware, estimated sprint plans.

---

## 🚀 Key Architectural Patterns

* **The Stateful Loop (Human-in-the-Loop):** Built using **LangGraph (v3+)** state persistence. Workflows leverage the `interrupt()` mechanism to freeze execution, awaiting human feedback (e.g., Engineering Manager capacity reviews) before writing to external systems.
* **Modularity:** Isolated, single-responsibility Python modules representing independent graph nodes (`ingester`, `critic`, `estimator`, `human_approval`, `sync`).
* **Zero-Cost Infrastructure:** Routes heavy inference to high-performance open-weights models (`groq/llama-3.3-70b-versatile` and `groq/llama-3.1-8b-instant`) via **LiteLLM**.
* **Structured Output Validation:** Enforces strict compliance to Jira schemas by passing Pydantic JSON schemas directly to LiteLLM's `response_format` endpoint.

---

## 📁 File Structure

```
PM-Tool/
├── middleware/              # Core state machine package
│   ├── config.py            # Global settings & model identifiers
│   ├── state.py             # AgentState TypedDict & Pydantic validation schemas
│   ├── graph.py             # Graph compiler & routing edges definition
│   └── nodes/               # Single-responsibility worker nodes
│       ├── ingester.py      # Mock upstream PRD parsing
│       ├── critic.py        # Gaps & Edge-cases critic node
│       ├── estimator.py     # Structured sprint task estimator
│       ├── human_approval.py# Freezes execution awaiting EM feedback
│       └── sync.py          # Backlog sync executor
├── run_sandbox.py           # CLI driver for interactive EM feedback loop
├── test_connection.py       # API key and connectivity tester
├── CHANGELOG.md             # Automated log of implemented changes
└── .gitignore               # Configured to protect secrets, guidelines, and cache
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in the required keys. Below are the key configuration variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | LiteLLM embedding model for RAG |
| `EMBEDDING_DIMENSION` | `1536` | Must match `EMBEDDING_MODEL` output dims |
| `PROJECT_ROOT` | Auto-detected from `middleware/` | Root directory for codebase inspector |
| `FALLBACK_PRIMARY_MODEL` | `github/meta-llama-3.3-70b-instruct` | Fallback when `PRIMARY_MODEL` fails |
| `FALLBACK_CRITIC_MODEL` | `github/meta-llama-3.1-8b-instruct` | Fallback when `CRITIC_MODEL` fails |
| `MODEL_MAX_TOKENS` | `128000` | Context window limit for token guard |
| `LLM_CACHE_ENABLED` | `false` | Enable disk caching (development only) |
| `LANGCHAIN_TRACING_V2` | `false` | Set to `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | *(unset)* | LangSmith API key for tracing |

---

## 🎮 How to Run

### 1. Test LLM Connectivity
To verify your API credentials and ensure the Groq endpoints are responsive:
```bash
python test_connection.py
```

### 2. Run the Interactive Sandbox
To execute the modular stateful loop and act as the Engineering Manager reviewing the draft sprint plan:
```bash
python run_sandbox.py
```

---

