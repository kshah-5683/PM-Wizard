import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.rag import generate_embedding, search_similar_tickets, store_approved_tickets

class TestRagPipeline(unittest.IsolatedAsyncioTestCase):
    @patch("litellm.aembedding")
    async def test_generate_embedding_success(self, mock_aembed):
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_aembed.return_value = mock_response
        
        emb = await generate_embedding("test text")
        self.assertEqual(emb, [0.1, 0.2, 0.3])
        mock_aembed.assert_called_once()

    @patch("litellm.aembedding")
    async def test_generate_embedding_failure(self, mock_aembed):
        mock_aembed.side_effect = Exception("API Error")
        
        emb = await generate_embedding("test text")
        self.assertIsNone(emb)

    async def test_search_similar_tickets_no_db(self):
        db = MagicMock()
        db.pool = None
        
        res = await search_similar_tickets(db, "query")
        self.assertEqual(res, [])

    @patch("middleware.rag.generate_embedding")
    async def test_search_similar_tickets_fallback_text(self, mock_gen_emb):
        mock_gen_emb.return_value = None
        
        mock_db = MagicMock()
        mock_db.pgvector_enabled = True
        
        mock_conn = MagicMock()
        mock_cur = AsyncMock()
        
        mock_db.pool.connection.return_value.__aenter__.return_value = mock_conn
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cur
        
        mock_cur.fetchall.return_value = [
            {"ticket_key": "PROJ-101", "title": "Stripe Integration", "description": "stripe payment", "estimation": 3, "priority": "HIGH"}
        ]
        
        res = await search_similar_tickets(mock_db, "stripe payment")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["ticket_key"], "PROJ-101")
        
        called_args = mock_cur.execute.call_args[0]
        self.assertIn("ILIKE", called_args[0])

if __name__ == "__main__":
    unittest.main()
