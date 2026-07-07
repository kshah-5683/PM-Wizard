from langgraph.types import interrupt
from middleware.state import AgentState

def human_approval_node(state: AgentState):
    print("\n--- [Human-in-the-Loop Node] Awaiting EM Review ---")
    print("Draft Tickets Proposed:")
    for ticket in state.get("jira_tickets", []):
        print(f"[{ticket['key']}] ({ticket['type']}) {ticket['title']} - Est: {ticket['estimation']} pts, Priority: {ticket['priority']}")
        print(f"  Description: {ticket['description']}")
    
    # Freeze the graph execution here and await external inputs
    em_feedback = interrupt({
        "status": "AWAITING_EM_APPROVAL",
        "draft_tickets": state["jira_tickets"]
    })
    
    decision = em_feedback.get("decision", "approve")
    comments = em_feedback.get("comments", "")
    
    if decision == "approve":
        print("[Human-in-the-Loop] EM Approved the plan!")
        return {
            "em_approval_status": "APPROVED",
            "em_feedback_comments": None
        }
    else:
        print(f"[Human-in-the-Loop] EM Requested Revisions: {comments}")
        return {
            "em_approval_status": "REVISE",
            "em_feedback_comments": comments,
            "attempt_count": state.get("attempt_count", 0) + 1
        }
