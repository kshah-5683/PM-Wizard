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

