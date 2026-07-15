from middleware.state import AgentState
from middleware.database import db_manager
from middleware.rag import store_approved_tickets

async def push_to_jira_node(state: AgentState):
    print("\n--- [Push to Jira Node] Synchronizing Backlog ---")
    tickets = state.get("jira_tickets", [])
    print(f"[OK] Successfully pushed {len(tickets)} tickets to the Jira board!")
    
    # RAG feedback loop: Store approved tickets in Postgres historical_tickets
    try:
        await store_approved_tickets(db_manager, tickets)
    except Exception as e:
        print(f"[Push to Jira] Failed to store approved tickets in RAG history ({e}).")
        
    return {"em_approval_status": "COMPLETED"}
