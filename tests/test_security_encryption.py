import unittest
from unittest.mock import MagicMock
import os
from middleware.database import DatabaseManager

class TestSecurityEncryption(unittest.TestCase):
    def setUp(self):
        # We test with a mock database manager
        self.db = DatabaseManager(connection_string="postgresql://dummy")
        os.environ["ENCRYPTION_KEY"] = "8cZJ57D2l8v1cM2H2Fz9j6Qz3D4f1J3d2H5a7e9i1b8=" # valid 32-byte key
        
    def tearDown(self):
        if "ENCRYPTION_KEY" in os.environ:
            del os.environ["ENCRYPTION_KEY"]

    def test_fernet_initialization_with_env(self):
        from cryptography.fernet import Fernet
        db = DatabaseManager()
        db.pool = MagicMock()
        db.checkpointer = MagicMock()
        
        os.environ["ENCRYPTION_KEY"] = "8cZJ57D2l8v1cM2H2Fz9j6Qz3D4f1J3d2H5a7e9i1b8="
        db.fernet = Fernet(os.getenv("ENCRYPTION_KEY").encode())
        self.assertIsNotNone(db.fernet)
        
        secret = "my-secret-access-token"
        encrypted = db.encrypt_token(secret)
        self.assertNotEqual(encrypted, secret)
        
        decrypted = db.decrypt_token(encrypted)
        self.assertEqual(decrypted, secret)

    def test_fernet_fallback_when_no_env(self):
        db = DatabaseManager()
        if "ENCRYPTION_KEY" in os.environ:
            del os.environ["ENCRYPTION_KEY"]
            
        from cryptography.fernet import Fernet
        db.fernet = Fernet(Fernet.generate_key())
        
        self.assertIsNotNone(db.fernet)
        secret = "fallback-test-token"
        encrypted = db.encrypt_token(secret)
        self.assertNotEqual(encrypted, secret)
        
        decrypted = db.decrypt_token(encrypted)
        self.assertEqual(decrypted, secret)

if __name__ == "__main__":
    unittest.main()
