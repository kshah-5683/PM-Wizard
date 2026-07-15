import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from middleware.llm import resilient_completion, aresilient_completion
from middleware.config import PRIMARY_MODEL, FALLBACK_PRIMARY_MODEL

class TestLlmResilience(unittest.IsolatedAsyncioTestCase):
    @patch("middleware.llm.completion")
    def test_resilient_completion_direct_success(self, mock_comp):
        mock_comp.return_value = "success"
        res = resilient_completion(PRIMARY_MODEL, messages=[])
        self.assertEqual(res, "success")
        mock_comp.assert_called_once_with(model=PRIMARY_MODEL, messages=[])

    @patch("middleware.llm.completion")
    def test_resilient_completion_fallback_success(self, mock_comp):
        mock_comp.side_effect = [Exception("Primary Failed"), "fallback success"]
        res = resilient_completion(PRIMARY_MODEL, messages=[])
        self.assertEqual(res, "fallback success")
        self.assertEqual(mock_comp.call_count, 2)
        mock_comp.assert_any_call(model=PRIMARY_MODEL, messages=[])
        mock_comp.assert_any_call(model=FALLBACK_PRIMARY_MODEL, messages=[])

    @patch("middleware.llm.acompletion")
    async def test_aresilient_completion_fallback_success(self, mock_acomp):
        mock_acomp.side_effect = [Exception("Primary Failed"), "fallback success"]
        res = await aresilient_completion(PRIMARY_MODEL, messages=[])
        self.assertEqual(res, "fallback success")
        self.assertEqual(mock_acomp.call_count, 2)
        mock_acomp.assert_any_call(model=PRIMARY_MODEL, messages=[])
        mock_acomp.assert_any_call(model=FALLBACK_PRIMARY_MODEL, messages=[])

if __name__ == "__main__":
    unittest.main()
