import pytest
from middleware.state import AgentState, JiraTicket, SprintPlan
from middleware.graph import should_continue, route_after_resolution
from middleware.nodes.human_approval import human_approval_node
from middleware.nodes.sync import publish_tickets_to_jira

def test_jira_ticket_schema_extensions():
    ticket = JiraTicket(
        key="TICKET-1",
        type="Story",
        title="Test Story Title",
        description="Detailed description",
        estimation=5,
        priority="High",
        parent_key="EPIC-1",
        blocked_by=["TICKET-0"],
        jira_issue_id="PROJ-101",
        confidence_level="HIGH",
        estimation_rationale="Low technical complexity"
    )
    assert ticket.parent_key == "EPIC-1"
    assert ticket.blocked_by == ["TICKET-0"]
    assert ticket.jira_issue_id == "PROJ-101"
    assert ticket.confidence_level == "HIGH"

def test_circuit_breaker_max_revisions():
    # Attempt count under 3 allows revision
    state_revise_2 = {
        "em_approval_status": "REVISE",
        "attempt_count": 2
    }
    assert should_continue(state_revise_2) == "estimator"

    # Attempt count 3 or higher triggers circuit breaker halt (END)
    state_revise_3 = {
        "em_approval_status": "REVISE",
        "attempt_count": 3
    }
    assert should_continue(state_revise_3) == "__end__"

    state_resolution_3 = {
        "critic_resolved": False,
        "attempt_count": 3
    }
    assert route_after_resolution(state_resolution_3) == "__end__"

@pytest.mark.asyncio
async def test_human_approval_edit_and_approve_crud(monkeypatch):
    # Mock interrupt to simulate EM providing edited tickets directly
    edited_tickets = [
        {
            "key": "TICKET-1",
            "type": "Story",
            "title": "EM Edited Title",
            "description": "EM edited description",
            "estimation": 3,
            "priority": "High"
        },
        {
            "key": "TICKET-2",
            "type": "Story",
            "title": "Newly Added Ticket by EM",
            "description": "Created directly in HITL UI",
            "estimation": 2,
            "priority": "Medium"
        }
    ]
    
    def mock_interrupt(payload):
        return {
            "decision": "edit_and_approve",
            "tickets": edited_tickets
        }
        
    import middleware.nodes.human_approval as ha_mod
    monkeypatch.setattr(ha_mod, "interrupt", mock_interrupt)
    
    initial_state = {
        "jira_tickets": [
            {"key": "TICKET-1", "type": "Story", "title": "Original Title", "description": "Original", "estimation": 5, "priority": "Medium"}
        ],
        "attempt_count": 1
    }
    
    res = await human_approval_node(initial_state)
    assert res["em_approval_status"] == "APPROVED"
    assert len(res["jira_tickets"]) == 2
    assert res["jira_tickets"][0]["title"] == "EM Edited Title"
    assert res["jira_tickets"][1]["title"] == "Newly Added Ticket by EM"
