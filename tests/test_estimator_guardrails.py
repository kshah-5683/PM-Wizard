import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.nodes.estimator import estimator_node

class TestEstimatorGuardrails(unittest.IsolatedAsyncioTestCase):
    @patch("middleware.nodes.estimator.aresilient_completion")
    @patch("middleware.nodes.estimator.search_similar_tickets")
    async def test_estimator_guardrails_fibonacci_correction_and_greenfield(self, mock_search, mock_acomp):
        # 1. Mock similar tickets
        mock_search.return_value = []
        
        # 2. Mock structured response returning invalid Fibonacci point (e.g., 4 and 6)
        # and missing Greenfield banner
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"tickets": [{"key": "T-1", "type": "Story", "title": "Setup database", "description": "Need database schema.", "estimation": 4, "priority": "High"}, {"key": "T-2", "type": "Story", "title": "Build Auth", "description": "Need jwt authorization.", "estimation": 6, "priority": "High"}]}'
                )
            )
        ]
        mock_acomp.return_value = mock_response

        state = {
            "raw_prd": "Need database and auth.",
            "workspace_profile": "React, Python",
            "sprint_constraints": None,
            "custom_tags": [],
            "attempt_count": 0,
            "project_mode": "GREENFIELD"
        }

        res = await estimator_node(state)
        
        self.assertIn("jira_tickets", res)
        tickets = res["jira_tickets"]
        self.assertEqual(len(tickets), 2)
        
        # 4 should be rounded to 3 (first nearest in sequence [1, 2, 3, 5, 8, 13])
        # 6 should be rounded to 5
        self.assertEqual(tickets[0]["estimation"], 3)
        self.assertEqual(tickets[1]["estimation"], 5)
        
        # Verify Greenfield warning was auto-injected
        warning_banner = "*⚠️ NOTE: Greenfield estimation variance is higher due to zero-to-one implementation risk.*"
        self.assertTrue(tickets[0]["description"].startswith(warning_banner))
        self.assertTrue(tickets[1]["description"].startswith(warning_banner))

    @patch("middleware.nodes.estimator.aresilient_completion")
    @patch("middleware.nodes.estimator.search_similar_tickets")
    async def test_estimator_guardrails_brownfield_no_warning(self, mock_search, mock_acomp):
        mock_search.return_value = []
        
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"tickets": [{"key": "T-1", "type": "Story", "title": "Setup database", "description": "Need database schema.", "estimation": 3, "priority": "High"}]}'
                )
            )
        ]
        mock_acomp.return_value = mock_response

        state = {
            "raw_prd": "Need database.",
            "workspace_profile": "React, Python",
            "sprint_constraints": None,
            "custom_tags": [],
            "attempt_count": 0,
            "project_mode": "BROWNFIELD"
        }

        res = await estimator_node(state)
        
        tickets = res["jira_tickets"]
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets[0]["estimation"], 3)
        
        # Verify Greenfield warning was NOT injected
        warning_banner = "*⚠️ NOTE: Greenfield estimation variance is higher due to zero-to-one implementation risk.*"
        self.assertNotIn(warning_banner, tickets[0]["description"])

if __name__ == "__main__":
    unittest.main()
