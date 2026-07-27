import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from middleware.nodes.sync import (
    string_to_adf,
    discover_story_points_field,
    fetch_default_jira_project,
    publish_tickets_to_jira,
    push_to_jira_node
)

class TestJiraPublishing(unittest.IsolatedAsyncioTestCase):
    def test_string_to_adf(self):
        result = string_to_adf("Hello world")
        self.assertEqual(result["type"], "doc")
        self.assertEqual(result["content"][0]["type"], "paragraph")
        self.assertEqual(result["content"][0]["content"][0]["text"], "Hello world")

        # None / empty fallback
        empty_res = string_to_adf(None)
        self.assertEqual(empty_res["content"][0]["content"][0]["text"], "No description provided.")

    @patch("httpx.AsyncClient.get")
    async def test_discover_story_points_field(self, mock_get):
        mock_res = MagicMock()
        mock_res.is_success = True
        mock_res.json.return_value = [
            {"id": "customfield_12345", "name": "Story Points"},
            {"id": "customfield_99999", "name": "Sprint"}
        ]
        mock_get.return_value = mock_res
        
        async with httpx.AsyncClient() as client:
            field_id = await discover_story_points_field("cloud-id-123", "fake-token", client)
            self.assertEqual(field_id, "customfield_12345")

    @patch("httpx.AsyncClient.get")
    async def test_fetch_default_jira_project(self, mock_get):
        mock_res = MagicMock()
        mock_res.is_success = True
        mock_res.json.return_value = [
            {"id": "10000", "key": "ALPHA", "name": "Alpha Project"},
            {"id": "10001", "key": "BETA", "name": "Beta Project"}
        ]
        mock_get.return_value = mock_res
        
        async with httpx.AsyncClient() as client:
            project_key = await fetch_default_jira_project("cloud-id-123", "fake-token", client)
            self.assertEqual(project_key, "ALPHA")

    @patch("httpx.AsyncClient.post")
    @patch("middleware.nodes.sync.discover_story_points_field")
    async def test_publish_tickets_to_jira(self, mock_discover, mock_post):
        mock_discover.return_value = "customfield_10016"
        
        # We will mock the issue posts for Epic, Story, Subtask
        res_epic = MagicMock()
        res_epic.is_success = True
        res_epic.json.return_value = {"id": "1000", "key": "KEY-1", "self": "..."}

        res_story = MagicMock()
        res_story.is_success = True
        res_story.json.return_value = {"id": "1001", "key": "KEY-2", "self": "..."}

        res_subtask = MagicMock()
        res_subtask.is_success = True
        res_subtask.json.return_value = {"id": "1002", "key": "KEY-3", "self": "..."}

        side_effects = [res_epic, res_story, res_subtask]
        mock_post.side_effect = side_effects

        tickets = [
            {"key": "TICKET-1", "type": "Epic", "title": "My Epic", "description": "Epic desc", "estimation": None, "priority": "High"},
            {"key": "TICKET-2", "type": "Story", "title": "My Story", "description": "Story desc", "estimation": 5, "priority": "Medium"},
            {"key": "TICKET-3", "type": "Subtask", "title": "My Subtask", "description": "Subtask desc", "estimation": None, "priority": "Low"}
        ]

        updated = await publish_tickets_to_jira(tickets, "cloud-123", "fake-token", "PROJ")
        
        # Verify keys and URLs are mapped
        self.assertEqual(updated[0]["jira_key"], "KEY-1")
        self.assertEqual(updated[1]["jira_key"], "KEY-2")
        self.assertEqual(updated[2]["jira_key"], "KEY-3")
        
        # Verify parent links were passed correctly in POST calls
        # 1st call: Epic
        args_1, kwargs_1 = mock_post.call_args_list[0]
        self.assertEqual(kwargs_1["json"]["fields"]["issuetype"]["name"], "Epic")
        self.assertNotIn("parent", kwargs_1["json"]["fields"])

        # 2nd call: Story under Epic
        args_2, kwargs_2 = mock_post.call_args_list[1]
        self.assertEqual(kwargs_2["json"]["fields"]["issuetype"]["name"], "Story")
        self.assertEqual(kwargs_2["json"]["fields"]["parent"]["key"], "KEY-1")
        self.assertEqual(kwargs_2["json"]["fields"]["customfield_10016"], 5.0)

        # 3rd call: Sub-task under Story
        args_3, kwargs_3 = mock_post.call_args_list[2]
        self.assertEqual(kwargs_3["json"]["fields"]["issuetype"]["name"], "Sub-task")
        self.assertEqual(kwargs_3["json"]["fields"]["parent"]["key"], "KEY-2")

    @patch("middleware.nodes.sync.db_manager")
    @patch("middleware.nodes.sync.store_approved_tickets")
    @patch("middleware.nodes.sync.publish_tickets_to_jira")
    @patch("middleware.oauth.get_valid_token")
    async def test_push_to_jira_node_triggered(self, mock_get_token, mock_publish, mock_store, mock_db):
        mock_db.get_change_requests = AsyncMock(return_value=[])
        mock_db.get_integration = AsyncMock(return_value={
            "tenant_id": "cloud-id-123"
        })
        mock_get_token.return_value = "jira-oauth-token"
        
        tickets = [
            {"key": "TICKET-1", "type": "Story", "title": "Story 1", "estimation": 3}
        ]
        mock_publish.return_value = [
            {"key": "TICKET-1", "type": "Story", "title": "Story 1", "estimation": 3, "jira_key": "PROJ-99"}
        ]
        
        state = {
            "jira_tickets": tickets,
            "user_id": "user-123",
            "org_id": "org-google",
            "jira_project_key": "PROJ"
        }
        config = {"configurable": {"thread_id": "thread-123"}}
        
        res = await push_to_jira_node(state, config)
        
        self.assertEqual(res["em_approval_status"], "COMPLETED")
        self.assertEqual(res["jira_tickets"][0]["jira_key"], "PROJ-99")
        mock_publish.assert_called_once_with(tickets, "cloud-id-123", "jira-oauth-token", "PROJ")
        mock_store.assert_called_once()

if __name__ == "__main__":
    unittest.main()
