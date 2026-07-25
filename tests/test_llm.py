import unittest
from unittest.mock import patch
from middleware.llm import aresilient_completion
from middleware.config import PRIMARY_MODEL, FALLBACK_PRIMARY_MODEL

class TestLlmResilience(unittest.IsolatedAsyncioTestCase):
    @patch("middleware.llm.acompletion")
    async def test_aresilient_completion_direct_success(self, mock_acomp):
        mock_acomp.return_value = "success"
        res = await aresilient_completion(PRIMARY_MODEL, messages=[])
        self.assertEqual(res, "success")
        mock_acomp.assert_called_once_with(model=PRIMARY_MODEL, messages=[])

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
