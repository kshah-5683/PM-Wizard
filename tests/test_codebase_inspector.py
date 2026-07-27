import os
import tempfile
import shutil
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from middleware.nodes.codebase_inspector import inspect_codebase, inspect_codebase_remote

class TestCodebaseInspector(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
    async def test_keyword_extraction_no_keywords(self):
        prd = "This is a simple document with no special technologies."
        result = await inspect_codebase(prd, self.test_dir)
        self.assertIn("No relevant technology keywords detected", result)
        
    async def test_codebase_scan_success(self):
        db_file = os.path.join(self.test_dir, "db.py")
        with open(db_file, "w") as f:
            f.write("def connect_postgres():\n    pass\n")
            
        venv_dir = os.path.join(self.test_dir, ".venv")
        os.makedirs(venv_dir)
        ignored_file = os.path.join(venv_dir, "ignored.py")
        with open(ignored_file, "w") as f:
            f.write("def postgres_helper():\n    pass\n")
            
        prd = "We need a postgres database integration."
        result = await inspect_codebase(prd, self.test_dir)
        
        self.assertIn("### Codebase Context Summary", result)
        self.assertIn("postgres", result)
        self.assertIn("db.py", result)
        self.assertNotIn("ignored.py", result)

    @patch("httpx.AsyncClient.get")
    async def test_remote_codebase_scan_success(self, mock_get):
        # 1. Mock repo default branch fetch
        res_repo = MagicMock()
        res_repo.is_success = True
        res_repo.json.return_value = {"default_branch": "develop"}
        
        # 2. Mock git recursive tree fetch
        res_tree = MagicMock()
        res_tree.is_success = True
        res_tree.json.return_value = {
            "tree": [
                {"path": "src/main.py", "type": "blob", "size": 1000},
                {"path": "src/ignored_file.txt", "type": "blob", "size": 2000},
                {"path": "node_modules/ignored.js", "type": "blob", "size": 500},
                {"path": "src/db.sql", "type": "blob", "size": 1024}
            ]
        }
        
        # 3. Mock raw content fetches
        # src/main.py -> matches "oauth"
        res_main = MagicMock()
        res_main.is_success = True
        res_main.text = "import oauth"
        
        # src/db.sql -> matches "postgres"
        res_db = MagicMock()
        res_db.is_success = True
        res_db.text = "CREATE TABLE user_postgres (...)"

        def get_mock_side_effect(url, *args, **kwargs):
            if "repos/my-owner/my-repo/git/trees/develop" in url:
                return res_tree
            elif "repos/my-owner/my-repo" in url:
                return res_repo
            elif "raw.githubusercontent.com/my-owner/my-repo/develop/src/main.py" in url:
                return res_main
            elif "raw.githubusercontent.com/my-owner/my-repo/develop/src/db.sql" in url:
                return res_db
            # Default response
            res_default = MagicMock()
            res_default.is_success = False
            return res_default

        mock_get.side_effect = get_mock_side_effect

        prd = "We need an oauth login flow and a postgres database."
        keywords = ["oauth", "postgres"]
        
        result = await inspect_codebase_remote(prd, "my-owner/my-repo", "fake-token", keywords)
        
        self.assertIn("### Codebase Context Summary (GitHub Remote)", result)
        self.assertIn("**Repository:** `my-owner/my-repo` (branch: `develop`)", result)
        self.assertIn("src/main.py", result)
        self.assertIn("src/db.sql", result)
        self.assertNotIn("ignored_file.txt", result)
        self.assertNotIn("ignored.js", result)

if __name__ == "__main__":
    unittest.main()
