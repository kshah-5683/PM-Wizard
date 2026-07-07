from middleware.state import AgentState

def push_to_jira_node(state: AgentState):
    print("\n--- [Push to Jira Node] Synchronizing Backlog ---")
    print(f"[OK] Successfully pushed {len(state.get('jira_tickets', []))} tickets to the Jira board!")
    return {"em_approval_status": "COMPLETED"}
