from langgraph.types import interrupt
from middleware.state import AgentState

async def critic_resolution_node(state: AgentState):
    print("\n--- [Critic Resolution Node] Awaiting EM Decision on Critical Gaps ---")
    
    # LangGraph interrupt freezes the execution and returns user response
    user_input = interrupt({
        "status": "AWAITING_CRITIC_RESOLUTION",
        "critiques": state.get("critiques", []),
        "type": "critic_resolution_required",
        "attempt_count": state.get("attempt_count", 0)
    })
    
    action = user_input.get("action", "amend")
    
    if action == "bypass":
        print("[Critic Resolution] EM decided to BYPASS critical critiques.")
        return {
            "critic_resolved": True
        }
    else:
        # User amended the PRD - loop back to ingestion node
        amended_prd = user_input.get("amended_prd", state["raw_prd"])
        print("[Critic Resolution] EM amended the PRD. Re-routing to Ingestion Node.")
        return {
            "raw_prd": amended_prd,
            "critic_resolved": False,
            "critiques": None,
            "missing_edge_cases": None
        }
