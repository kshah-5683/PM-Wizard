from middleware.state import AgentState

def ingestion_node(state: AgentState):
    print("\n--- [Ingestion Node] Ingesting Upstream PRD ---")
    print("Ingested PRD Content successfully.")
    return {"attempt_count": state.get("attempt_count", 0)}
