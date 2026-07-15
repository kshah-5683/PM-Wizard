from middleware.state import AgentState
from middleware.nodes.codebase_inspector import inspect_codebase

def ingestion_node(state: AgentState):
    print("\n--- [Ingestion Node] Ingesting Upstream PRD ---")
    print("Ingested PRD Content successfully.")
    
    # JIT codebase inspection
    try:
        raw_prd = state.get("raw_prd", "")
        codebase_summary = inspect_codebase(raw_prd)
        print(f"[Ingestion] Codebase scan complete.")
    except Exception as e:
        print(f"[Ingestion] Codebase scan failed ({e}), continuing without codebase context.")
        codebase_summary = None
        
    return {
        "attempt_count": state.get("attempt_count", 0),
        "codebase_summary": codebase_summary
    }
