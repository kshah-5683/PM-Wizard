import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.nodes.sync import push_to_jira_node

class TestChangeRequests(unittest.IsolatedAsyncioTestCase):
    @patch("middleware.nodes.sync.db_manager")
    @patch("middleware.nodes.sync.store_approved_tickets")
    async def test_push_to_jira_node_applies_approved_changes(self, mock_store, mock_db):
        # Setup mock database responses
        mock_db.get_change_requests = AsyncMock(return_value=[
            {
                "id": 1,
                "ticket_key": "TICKET-1",
                "developer_name": "Dev Alice",
                "original_points": 3,
                "original_description": "Old desc",
                "requested_points": 5,
                "requested_description": "New desc",
                "status": "APPROVED"
            },
            {
                "id": 2,
                "ticket_key": "TICKET-2",
                "developer_name": "Dev Bob",
                "original_points": 2,
                "original_description": "Old desc 2",
                "requested_points": 8,
                "requested_description": "New desc 2",
                "status": "PENDING"  # NOT approved, should be ignored!
            }
        ])

        state = {
            "jira_tickets": [
                {"ticket_key": "TICKET-1", "title": "Ticket One", "description": "Old desc", "estimation": 3, "priority": "MEDIUM"},
                {"ticket_key": "TICKET-2", "title": "Ticket Two", "description": "Old desc 2", "estimation": 2, "priority": "LOW"}
            ],
            "em_approval_status": "APPROVED"
        }
        
        config = {"configurable": {"thread_id": "test-thread-123"}}
        
        res = await push_to_jira_node(state, config)
        
        # Verify tickets have been modified
        self.assertEqual(res["em_approval_status"], "COMPLETED")
        self.assertIn("jira_tickets", res)
        
        updated_tickets = res["jira_tickets"]
        self.assertEqual(len(updated_tickets), 2)
        
        # TICKET-1 should be updated (points=5, desc="New desc")
        ticket1 = next(t for t in updated_tickets if t["ticket_key"] == "TICKET-1")
        self.assertEqual(ticket1["estimation"], 5)
        self.assertEqual(ticket1["description"], "New desc")
        
        # TICKET-2 should be unchanged since its change request is PENDING
        ticket2 = next(t for t in updated_tickets if t["ticket_key"] == "TICKET-2")
        self.assertEqual(ticket2["estimation"], 2)
        self.assertEqual(ticket2["description"], "Old desc 2")

        # Assert store_approved_tickets is called with updated tickets list
        mock_store.assert_called_once_with(mock_db, updated_tickets, sprint_plan_id="test-thread-123", org_id="default-org")

if __name__ == "__main__":
    unittest.main()
