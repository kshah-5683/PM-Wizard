import unittest
from unittest.mock import patch
from middleware.state import JiraTicket
from middleware.graph import should_continue, route_after_resolution
from middleware.nodes.human_approval import human_approval_node

class TestWorkflowCircuitBreaker(unittest.IsolatedAsyncioTestCase):
    def test_jira_ticket_schema_extensions(self):
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
        self.assertEqual(ticket.parent_key, "EPIC-1")
        self.assertEqual(ticket.blocked_by, ["TICKET-0"])
        self.assertEqual(ticket.jira_issue_id, "PROJ-101")
        self.assertEqual(ticket.confidence_level, "HIGH")

    def test_circuit_breaker_max_revisions(self):
        # Attempt count under 3 allows revision
        state_revise_2 = {
            "em_approval_status": "REVISE",
            "attempt_count": 2
        }
        self.assertEqual(should_continue(state_revise_2), "estimator")

        # Attempt count 3 or higher triggers circuit breaker halt (END)
        state_revise_3 = {
            "em_approval_status": "REVISE",
            "attempt_count": 3
        }
        self.assertEqual(should_continue(state_revise_3), "__end__")

        state_resolution_3 = {
            "critic_resolved": False,
            "attempt_count": 3
        }
        self.assertEqual(route_after_resolution(state_resolution_3), "__end__")

    @patch("middleware.nodes.human_approval.interrupt")
    async def test_human_approval_edit_and_approve_crud(self, mock_interrupt):
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
        
        mock_interrupt.return_value = {
            "decision": "edit_and_approve",
            "tickets": edited_tickets
        }
        
        initial_state = {
            "jira_tickets": [
                {"key": "TICKET-1", "type": "Story", "title": "Original Title", "description": "Original", "estimation": 5, "priority": "Medium"}
            ],
            "attempt_count": 1
        }
        
        res = await human_approval_node(initial_state)
        self.assertEqual(res["em_approval_status"], "APPROVED")
        self.assertEqual(len(res["jira_tickets"]), 2)
        self.assertEqual(res["jira_tickets"][0]["title"], "EM Edited Title")
        self.assertEqual(res["jira_tickets"][1]["title"], "Newly Added Ticket by EM")

if __name__ == "__main__":
    unittest.main()
