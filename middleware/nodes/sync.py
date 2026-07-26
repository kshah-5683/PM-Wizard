from middleware.state import AgentState
from middleware.database import db_manager
from middleware.rag import store_approved_tickets
from langgraph.types import RunnableConfig

async def push_to_jira_node(state: AgentState, config: RunnableConfig):
    print("\n--- [Push to Jira Node] Synchronizing Backlog ---")
    tickets = state.get("jira_tickets", []) or []
    thread_id = config.get("configurable", {}).get("thread_id")
    
    # Fetch approved Developer change requests to apply
    approved_changes = []
    if thread_id:
        try:
            all_changes = await db_manager.get_change_requests(thread_id)
            approved_changes = [c for c in all_changes if c.get("status") == "APPROVED"]
            if approved_changes:
                print(f"[Push to Jira] Found {len(approved_changes)} APPROVED developer change requests. Merging into plan...")
        except Exception as e:
            print(f"[Push to Jira] Failed to fetch change requests from DB: {e}")

    # Merge changes into the tickets
    synced_tickets = []
    for ticket in tickets:
        ticket_copy = dict(ticket)
        # Handle key lookup since pydantic models or DB schema could use key/ticket_key
        ticket_key = ticket_copy.get("key") or ticket_copy.get("ticket_key")
        
        # Look for a matching approved change request
        for cr in approved_changes:
            if cr.get("ticket_key") == ticket_key:
                print(f"  Applying change request for {ticket_key}:")
                if cr.get("requested_points") is not None:
                    print(f"    Est story points: {ticket_copy.get('estimation')} -> {cr.get('requested_points')}")
                    ticket_copy["estimation"] = cr["requested_points"]
                if cr.get("requested_description") is not None:
                    print(f"    Description: Updated to developer request")
                    ticket_copy["description"] = cr["requested_description"]
                break
        synced_tickets.append(ticket_copy)

    print(f"[OK] Successfully pushed {len(synced_tickets)} tickets to the Jira board!")
    
    # RAG feedback loop: Store approved/merged tickets in Postgres historical_tickets
    try:
        org_id = state.get("org_id", "default-org")
        await store_approved_tickets(db_manager, synced_tickets, sprint_plan_id=thread_id, org_id=org_id)
    except Exception as e:
        print(f"[Push to Jira] Failed to store approved tickets in RAG history ({e}).")
        
    return {
        "jira_tickets": synced_tickets,
        "em_approval_status": "COMPLETED"
    }
