import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from server import app

class TestServerRoutes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Mock graph_db directly on app.state to avoid startup lifespan issues
        app.state.graph_db = AsyncMock()

    @patch("server.db_manager")
    @patch("server.run_graph_background")
    async def test_start_plan_role_restrictions(self, mock_run, mock_db):
        # 1. PM role should succeed
        mock_db.get_project_history = AsyncMock(return_value=None)
        mock_db.save_project_history = AsyncMock()
        
        response = self.client.post(
            "/api/v1/plan/start",
            json={"raw_prd": "Test PRD"},
            headers={"X-User-Role": "PM", "X-Org-Id": "org-google"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("thread_id", response.json())

        # 2. DEV role should fail with 403 Forbidden
        response_dev = self.client.post(
            "/api/v1/plan/start",
            json={"raw_prd": "Test PRD"},
            headers={"X-User-Role": "DEV", "X-Org-Id": "org-google"}
        )
        self.assertEqual(response_dev.status_code, 403)
        self.assertIn("Only Product Managers", response_dev.json()["detail"])

    @patch("server.db_manager")
    @patch("server.run_graph_background")
    async def test_start_plan_failed_run_retry(self, mock_run, mock_db):
        # Setup: Duplicate check returns an existing FAILED session
        mock_db.get_project_history = AsyncMock(return_value={
            "thread_id": "test-uuid-123",
            "status": "FAILED",
            "title": "Failed Run"
        })
        mock_db.save_project_history = AsyncMock()

        # Attempt to start with same thread_id should succeed because it was FAILED
        response = self.client.post(
            "/api/v1/plan/start",
            json={"raw_prd": "Test PRD", "thread_id": "test-uuid-123"},
            headers={"X-User-Role": "PM", "X-Org-Id": "org-google"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["thread_id"], "test-uuid-123")
        mock_db.save_project_history.assert_called_once()

    @patch("server.db_manager")
    @patch("server.run_graph_background")
    async def test_start_plan_active_run_duplicate_blocked(self, mock_run, mock_db):
        # Setup: Duplicate check returns an existing PROCESSING session
        mock_db.get_project_history = AsyncMock(return_value={
            "thread_id": "test-uuid-123",
            "status": "PROCESSING",
            "title": "Active Run"
        })
        mock_db.save_project_history = AsyncMock()

        # Attempt to start with same thread_id should fail with 400 Bad Request
        response = self.client.post(
            "/api/v1/plan/start",
            json={"raw_prd": "Test PRD", "thread_id": "test-uuid-123"},
            headers={"X-User-Role": "PM", "X-Org-Id": "org-google"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.json()["detail"])

    @patch("server.db_manager")
    async def test_status_cross_tenant_prevention(self, mock_db):
        # Setup: Thread belongs to org-google
        mock_db.get_project_history = AsyncMock(return_value={
            "thread_id": "test-uuid-123",
            "status": "COMPLETED",
            "title": "Google Run",
            "org_id": "org-google",
            "source_document": "Test Doc",
            "total_epics": 2,
            "total_stories": 5,
            "total_story_points": 13,
            "ai_summary": "Test Summary"
        })
        
        # Mock Graph state snapshot values
        mock_snapshot = MagicMock()
        mock_snapshot.values = {"org_id": "org-google"}
        mock_snapshot.next = []
        mock_snapshot.tasks = []
        app.state.graph_db.aget_state = AsyncMock(return_value=mock_snapshot)

        # 1. Query status with org-google should succeed
        response_ok = self.client.get(
            "/api/v1/plan/test-uuid-123/status",
            headers={"X-Org-Id": "org-google"}
        )
        self.assertEqual(response_ok.status_code, 200)

        # 2. Query status with org-microsoft should return 403 Forbidden
        response_leak = self.client.get(
            "/api/v1/plan/test-uuid-123/status",
            headers={"X-Org-Id": "org-microsoft"}
        )
        self.assertEqual(response_leak.status_code, 403)
        self.assertIn("belongs to another organization", response_leak.json()["detail"])

if __name__ == "__main__":
    unittest.main()
