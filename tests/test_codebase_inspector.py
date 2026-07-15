import os
import tempfile
import shutil
import unittest
from middleware.nodes.codebase_inspector import inspect_codebase

class TestCodebaseInspector(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)
        
    def test_keyword_extraction_no_keywords(self):
        prd = "This is a simple document with no special technologies."
        result = inspect_codebase(prd, self.test_dir)
        self.assertIn("No relevant technology keywords detected", result)
        
    def test_codebase_scan_success(self):
        # Create a file matching the keyword "postgres"
        db_file = os.path.join(self.test_dir, "db.py")
        with open(db_file, "w") as f:
            f.write("def connect_postgres():\n    pass\n")
            
        # Create an excluded folder file (should be ignored)
        venv_dir = os.path.join(self.test_dir, ".venv")
        os.makedirs(venv_dir)
        ignored_file = os.path.join(venv_dir, "ignored.py")
        with open(ignored_file, "w") as f:
            f.write("def postgres_helper():\n    pass\n")
            
        prd = "We need a postgres database integration."
        result = inspect_codebase(prd, self.test_dir)
        
        self.assertIn("### Codebase Context Summary", result)
        self.assertIn("postgres", result)
        self.assertIn("db.py", result)
        self.assertNotIn("ignored.py", result)

if __name__ == "__main__":
    unittest.main()
