import unittest
from middleware.tech_spec_generator import generate_ticket_tech_spec

class TestTechSpecGenerator(unittest.IsolatedAsyncioTestCase):
    async def test_tech_spec_generator_output(self):
        test_ticket = {
            "key": "TICKET-101",
            "type": "Story",
            "title": "Build User Profile Modal",
            "description": "Create interactive modal for user profile settings",
            "estimation": 5
        }
        
        spec = await generate_ticket_tech_spec(
            ticket=test_ticket,
            codebase_summary="Next.js frontend with TailwindCSS and FastAPI backend.",
            raw_prd="# User Profile PRD\nAllow users to edit profile and avatar."
        )
        
        self.assertEqual(spec["ticket_key"], "TICKET-101")
        self.assertIsInstance(spec["target_file_paths"], list)
        self.assertIsInstance(spec["developer_checklist"], list)
        self.assertGreater(len(spec["target_file_paths"]), 0)
        self.assertGreater(len(spec["developer_checklist"]), 0)
        self.assertIn("### 🛠️ Developer Technical Specification", spec["markdown_summary"])

if __name__ == "__main__":
    unittest.main()
