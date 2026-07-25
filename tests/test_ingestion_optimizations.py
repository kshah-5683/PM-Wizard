import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.nodes.ingester import has_visual_assets, ingestion_node
from middleware.nodes.codebase_inspector import extract_technology_keywords

class TestIngestionOptimizations(unittest.IsolatedAsyncioTestCase):
    def test_has_visual_assets(self):
        # Markdown image
        self.assertTrue(has_visual_assets("Here is an image: ![mock](https://example.com/ui.png)"))
        # Raw URL image link
        self.assertTrue(has_visual_assets("Check https://example.com/mock.jpg for wireframes"))
        # Text only
        self.assertFalse(has_visual_assets("Only text here, no image links."))

    @patch("middleware.nodes.codebase_inspector.aresilient_completion")
    async def test_extract_technology_keywords_success(self, mock_acomp):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='["fastapi", "react", "sqlite"]'))
        ]
        mock_acomp.return_value = mock_response

        res = await extract_technology_keywords("Using fastapi and react with sqlite.")
        self.assertEqual(res, ["fastapi", "react", "sqlite"])

    @patch("middleware.nodes.codebase_inspector.aresilient_completion")
    async def test_extract_technology_keywords_fallback(self, mock_acomp):
        # Failure triggering fallback
        mock_acomp.side_effect = Exception("API error")
        res = await extract_technology_keywords("Using postgres.")
        self.assertIn("postgres", res)
        self.assertIn("redis", res)  # Static keyword should be present

    @patch("middleware.nodes.ingester.extract_technology_keywords")
    @patch("middleware.nodes.ingester.inspect_codebase")
    @patch("middleware.nodes.ingester.profile_repository")
    async def test_ingestion_node_bypass_flow(self, mock_profile, mock_inspect, mock_extract):
        mock_extract.return_value = ["react"]
        mock_inspect.return_value = "codebase summary"
        mock_profile.return_value = "profile summary"

        # State without visual assets
        state = {
            "raw_prd": "This PRD does not contain any images.",
            "attempt_count": 0
        }

        res = await ingestion_node(state)
        
        # Verify visual bypass was activated (prd_images_context is empty)
        self.assertEqual(res["prd_images_context"], [])
        self.assertEqual(res["codebase_summary"], "codebase summary")
        self.assertEqual(res["workspace_profile"], "profile summary")

        # Verify extract and inspect was called with extracted keywords
        mock_extract.assert_called_once_with(state["raw_prd"])

if __name__ == "__main__":
    unittest.main()
