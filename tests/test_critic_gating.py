import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.nodes.critic import critic_node
from middleware.graph import route_after_critic, route_after_resolution

class TestCriticGating(unittest.IsolatedAsyncioTestCase):
    @patch("middleware.nodes.critic.aresilient_completion")
    async def test_critic_node_structured_gaps(self, mock_acomp):
        # Mock structured response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"critiques": [{"category": "CRITICAL", "description": "No auth check", "remediation": "Add middleware"}, {"category": "WARNING", "description": "Low log verbosity", "remediation": "Add logs"}]}'
                )
            )
        ]
        mock_acomp.return_value = mock_response

        state = {
            "raw_prd": "Need database and auth.",
            "workspace_profile": "Python",
            "sprint_constraints": None,
            "codebase_summary": None,
            "critiques": None
        }

        res = await critic_node(state)
        
        self.assertIn("critiques", res)
        self.assertEqual(len(res["critiques"]), 2)
        self.assertEqual(res["critiques"][0]["category"], "CRITICAL")
        self.assertEqual(res["critiques"][1]["category"], "WARNING")
        self.assertIn("missing_edge_cases", res)
        self.assertIn("🔴 CRITICAL: No auth check", res["missing_edge_cases"])

    def test_route_after_critic_critical(self):
        # Gaps exist with category CRITICAL
        state = {
            "critiques": [
                {"category": "CRITICAL", "description": "No auth check", "remediation": "Add middleware"},
                {"category": "WARNING", "description": "Low log verbosity", "remediation": "Add logs"}
            ],
            "critic_resolved": False
        }
        res = route_after_critic(state)
        self.assertEqual(res, "critic_resolution")

    def test_route_after_critic_warnings_only(self):
        # Gaps exist with only category WARNING
        state = {
            "critiques": [
                {"category": "WARNING", "description": "Low log verbosity", "remediation": "Add logs"}
            ],
            "critic_resolved": False
        }
        res = route_after_critic(state)
        self.assertEqual(res, "estimator")

    def test_route_after_critic_resolved(self):
        # Gaps exist with category CRITICAL but are marked as resolved/bypassed
        state = {
            "critiques": [
                {"category": "CRITICAL", "description": "No auth check", "remediation": "Add middleware"}
            ],
            "critic_resolved": True
        }
        res = route_after_critic(state)
        self.assertEqual(res, "estimator")

    def test_route_after_resolution_bypass(self):
        state = {
            "critic_resolved": True
        }
        res = route_after_resolution(state)
        self.assertEqual(res, "estimator")

    def test_route_after_resolution_amend(self):
        state = {
            "critic_resolved": False
        }
        res = route_after_resolution(state)
        self.assertEqual(res, "ingestion")

if __name__ == "__main__":
    unittest.main()
