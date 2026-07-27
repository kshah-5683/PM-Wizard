from langgraph.types import interrupt
from middleware.state import AgentState

async def human_approval_node(state: AgentState):
    print("\n--- [Human-in-the-Loop Node] Awaiting EM Review ---")
    print("Draft Tickets Proposed:")
    for ticket in state.get("jira_tickets", []):
        print(f"[{ticket['key']}] ({ticket['type']}) {ticket['title']} - Est: {ticket['estimation']} pts, Priority: {ticket['priority']}")
        print(f"  Description: {ticket['description']}")
    
    # Freeze the graph execution here and await external inputs
    em_feedback = interrupt({
        "status": "AWAITING_EM_APPROVAL",
        "draft_tickets": state["jira_tickets"],
        "type": "human_approval_required",
        "tickets": state["jira_tickets"],
        "attempt_count": state.get("attempt_count", 0),
        "historical_context": state.get("historical_context")
    })
    
    decision = em_feedback.get("decision", "approve")
    comments = em_feedback.get("comments", "")
    edited_tickets = em_feedback.get("tickets") or em_feedback.get("edited_tickets")
    
    if decision in ["approve", "edit_and_approve"] or edited_tickets:
        print("[Human-in-the-Loop] EM Approved the plan!")
        updates = {
            "em_approval_status": "APPROVED",
            "em_feedback_comments": None
        }
        if edited_tickets:
            print(f"[Human-in-the-Loop] EM updated {len(edited_tickets)} ticket(s) directly via in-place CRUD.")
            updates["jira_tickets"] = edited_tickets
        return updates
    else:
        print(f"[Human-in-the-Loop] EM Requested Revisions: {comments}")
        return {
            "em_approval_status": "REVISE",
            "em_feedback_comments": comments
        }

