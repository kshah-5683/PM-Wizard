import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import datetime
import time
from fastapi.testclient import TestClient
import httpx
from server import app
from middleware.integration_fetcher import (
    extract_notion_page_id,
    extract_confluence_page_id,
    extract_rich_text,
    fetch_external_document
)
from middleware.oauth import get_valid_token, refresh_atlassian_token

class TestIntegrationsFetcher(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.state.graph_db = AsyncMock()

    def test_extract_notion_page_id(self):
        urls = [
            ("https://www.notion.so/workspace/My-Page-Title-40f4e3c988ef4b5b820986955a82881a", "40f4e3c988ef4b5b820986955a82881a"),
            ("https://notion.so/a1b2c3d4e5f67890a1b2c3d4e5f67890", "a1b2c3d4e5f67890a1b2c3d4e5f67890"),
            ("https://www.notion.so/a1b2c3d4e5f67890a1b2c3d4e5f67890?v=somevalue", "a1b2c3d4e5f67890a1b2c3d4e5f67890"),
            ("https://www.notion.so/workspace/40f4e3c988ef4b5b820986955a82881a", "40f4e3c988ef4b5b820986955a82881a"),
            ("https://www.notion.so/workspace/My-Page-Title-40f4e3c9-88ef-4b5b-8209-86955a82881a", "40f4e3c988ef4b5b820986955a82881a")
        ]
        for url, expected in urls:
            with self.subTest(url=url):
                self.assertEqual(extract_notion_page_id(url), expected)

    def test_extract_confluence_page_id(self):
        urls = [
            ("https://workspace.atlassian.net/wiki/spaces/SPACE/pages/123456/Page+Title", "123456"),
            ("https://workspace.atlassian.net/wiki/pages/viewpage.action?pageId=987654", "987654"),
            ("https://workspace.atlassian.net/wiki/pages/viewpage.action?pageId=987654&another=param", "987654")
        ]
        for url, expected in urls:
            with self.subTest(url=url):
                self.assertEqual(extract_confluence_page_id(url), expected)

    def test_extract_rich_text(self):
        rich_text = [
            {"text": {"content": "Hello "}, "annotations": {}},
            {"text": {"content": "World"}, "annotations": {"bold": True}},
            {"text": {"content": "!"}, "annotations": {"italic": True, "code": True}}
        ]
        expected = "Hello **World***`!`*"
        self.assertEqual(extract_rich_text(rich_text), expected)

    @patch("middleware.oauth.db_manager")
    async def test_get_valid_token_cached(self, mock_db):
        # Setup: Token is NOT expired
        now = datetime.datetime.now(datetime.timezone.utc)
        future = now + datetime.timedelta(hours=1)
        mock_db.get_integration = AsyncMock(return_value={
            "access_token": "valid-token",
            "token_expires_at": future,
            "refresh_token": "refresh-val"
        })
        
        token = await get_valid_token("user-1", "atlassian", "org-1")
        self.assertEqual(token, "valid-token")
        mock_db.get_integration.assert_called_once_with("user-1", "atlassian", "org-1")

    @patch("middleware.oauth.db_manager")
    @patch("httpx.AsyncClient.post")
    async def test_refresh_atlassian_token(self, mock_post, mock_db):
        # Setup mock db and Atlassian response
        mock_db.get_integration = AsyncMock(return_value={
            "access_token": "old-access",
            "refresh_token": "my-refresh-token",
            "scopes": ["read:jira-work"],
            "tenant_id": "cloud-uuid-123"
        })
        mock_db.save_integration = AsyncMock()

        # Mock Atlassian token refresh endpoint response
        mock_res = MagicMock()
        mock_res.is_success = True
        mock_res.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_res

        with patch("middleware.oauth.ATLASSIAN_CLIENT_ID", "client-id"), \
             patch("middleware.oauth.ATLASSIAN_CLIENT_SECRET", "client-secret"):
            new_token = await refresh_atlassian_token("user-123", "org-456")
            
            self.assertEqual(new_token, "new-access-token")
            mock_db.save_integration.assert_called_once()
            # Ensure Atlassian refresh post request parameters are correct
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://auth.atlassian.com/oauth/token")
            self.assertEqual(kwargs["json"]["refresh_token"], "my-refresh-token")

    @patch("middleware.oauth.refresh_atlassian_token")
    @patch("middleware.oauth.db_manager")
    async def test_get_valid_token_expired(self, mock_db, mock_refresh):
        # Setup: Token is expired (expired 10 minutes ago)
        now = datetime.datetime.now(datetime.timezone.utc)
        past = now - datetime.timedelta(minutes=10)
        mock_db.get_integration = AsyncMock(return_value={
            "access_token": "expired-token",
            "token_expires_at": past,
            "refresh_token": "refresh-val"
        })
        mock_refresh.return_value = "refreshed-token"

        token = await get_valid_token("user-1", "atlassian", "org-1")
        self.assertEqual(token, "refreshed-token")
        mock_refresh.assert_called_once_with("user-1", "org-1")

    @patch("httpx.AsyncClient.get")
    @patch("middleware.integration_fetcher.clean_and_format_markdown")
    async def test_fetch_confluence_document(self, mock_format, mock_get):
        # Setup: Confluence page request
        mock_res = MagicMock()
        mock_res.is_success = True
        mock_res.json.return_value = {
            "title": "My Confluence PRD",
            "body": {
                "storage": {
                    "value": "<p>XHTML content</p>"
                }
            }
        }
        mock_get.return_value = mock_res
        mock_format.return_value = "# Cleaned Markdown PRD"

        from middleware.integration_fetcher import fetch_confluence_document
        result = await fetch_confluence_document("page-123", "cloud-123", "token-abc")
        self.assertEqual(result, "# Cleaned Markdown PRD")
        mock_format.assert_called_once_with("# My Confluence PRD\n\n<p>XHTML content</p>")

    @patch("middleware.integration_fetcher.get_valid_token")
    @patch("middleware.integration_fetcher.fetch_notion_document")
    async def test_fetch_external_document_notion(self, mock_notion, mock_token):
        mock_token.return_value = "notion-access-token"
        mock_notion.return_value = "# Notion PRD Content"

        url = "https://www.notion.so/workspace/My-Page-Title-40f4e3c988ef4b5b820986955a82881a"
        result = await fetch_external_document(url, "user-id-123", "org-123")
        self.assertEqual(result, "# Notion PRD Content")
        mock_token.assert_called_once_with("user-id-123", "notion", "org-123")
        mock_notion.assert_called_once_with("40f4e3c988ef4b5b820986955a82881a", "notion-access-token")

    @patch("server.db_manager")
    @patch("server.run_graph_background")
    @patch("middleware.integration_fetcher.fetch_external_document")
    async def test_start_plan_with_integration_url(self, mock_fetch, mock_run, mock_db):
        # Setup mock db and external document resolver
        mock_db.get_project_history = AsyncMock(return_value=None)
        mock_db.save_project_history = AsyncMock()
        mock_fetch.return_value = "# Resolved PRD Title\nThis is content fetched from Notion."

        response = self.client.post(
            "/api/v1/plan/start",
            json={
                "source_document": "https://www.notion.so/workspace/My-Page-Title-40f4e3c988ef4b5b820986955a82881a"
            },
            headers={
                "X-User-Role": "PM",
                "X-Org-Id": "org-google",
                "user-id": "user-email@test.com"
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("thread_id", response.json())
        mock_fetch.assert_called_once_with(
            "https://www.notion.so/workspace/My-Page-Title-40f4e3c988ef4b5b820986955a82881a",
            "user-email@test.com",
            "org-google"
        )
        
        # Verify run_graph_background is called with the resolved raw_prd
        args, kwargs = mock_run.call_args
        # Second arg is initial_state
        initial_state = args[2]
        self.assertEqual(initial_state["raw_prd"], "# Resolved PRD Title\nThis is content fetched from Notion.")

    def test_start_plan_with_integration_url_missing_user_header(self):
        # Passing source_document URL without the required user-id header should fail with 400
        response = self.client.post(
            "/api/v1/plan/start",
            json={
                "source_document": "https://www.notion.so/workspace/My-Page-Title-40f4e3c988ef4b5b820986955a82881a"
            },
            headers={
                "X-User-Role": "PM",
                "X-Org-Id": "org-google"
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("user-id", response.json()["detail"])

    @patch("middleware.integration_fetcher.fetch_external_document")
    def test_parse_url_endpoint_success(self, mock_fetch):
        mock_fetch.return_value = "# My Fetched Markdown"
        
        response = self.client.post(
            "/api/v1/parse-url",
            json={"url": "https://www.notion.so/my-page"},
            headers={
                "X-User-Role": "PM",
                "X-Org-Id": "org-google",
                "user-id": "user-email@test.com"
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["markdown"], "# My Fetched Markdown")
        mock_fetch.assert_called_once_with("https://www.notion.so/my-page", "user-email@test.com", "org-google")

    def test_parse_url_endpoint_role_restrictions(self):
        # 1. Non-PM should fail with 403
        response = self.client.post(
            "/api/v1/parse-url",
            json={"url": "https://www.notion.so/my-page"},
            headers={
                "X-User-Role": "DEV",
                "X-Org-Id": "org-google",
                "user-id": "user-email@test.com"
            }
        )
        self.assertEqual(response.status_code, 403)

        # 2. Missing user-id header should fail with 400
        response_missing_header = self.client.post(
            "/api/v1/parse-url",
            json={"url": "https://www.notion.so/my-page"},
            headers={
                "X-User-Role": "PM",
                "X-Org-Id": "org-google"
            }
        )
        self.assertEqual(response_missing_header.status_code, 400)

