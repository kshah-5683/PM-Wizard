import unittest
from middleware.dag_validator import validate_and_sanitize_dag

class TestDAGValidator(unittest.TestCase):
    def test_orphan_references_pruned(self):
        tickets = [
            {
                "key": "TICKET-1",
                "type": "Story",
                "title": "Story 1",
                "parent_key": "NON_EXISTENT_EPIC",
                "blocked_by": ["NON_EXISTENT_TICKET", "TICKET-2"]
            },
            {
                "key": "TICKET-2",
                "type": "Story",
                "title": "Story 2",
                "parent_key": None,
                "blocked_by": []
            }
        ]
        sanitized, warnings = validate_and_sanitize_dag(tickets)
        
        # Assert orphan parent cleared
        self.assertIsNone(sanitized[0]["parent_key"])
        # Assert orphan blocker removed, valid blocker retained
        self.assertEqual(sanitized[0]["blocked_by"], ["TICKET-2"])
        # Assert warnings generated
        self.assertTrue(any(w["code"] == "ORPHAN_PARENT" for w in warnings))
        self.assertTrue(any(w["code"] == "ORPHAN_BLOCKER" for w in warnings))

    def test_circular_dependency_pruned(self):
        tickets = [
            {
                "key": "TICKET-1",
                "type": "Story",
                "title": "Story 1",
                "blocked_by": ["TICKET-2"]
            },
            {
                "key": "TICKET-2",
                "type": "Story",
                "title": "Story 2",
                "blocked_by": ["TICKET-1"]
            }
        ]
        sanitized, warnings = validate_and_sanitize_dag(tickets)
        
        # Assert cycle broken (one direction pruned)
        t1_blockers = next(t["blocked_by"] for t in sanitized if t["key"] == "TICKET-1")
        t2_blockers = next(t["blocked_by"] for t in sanitized if t["key"] == "TICKET-2")
        
        self.assertEqual(len(t1_blockers) + len(t2_blockers), 1)
        self.assertTrue(any(w["code"] == "CIRCULAR_DEPENDENCY" for w in warnings))

if __name__ == "__main__":
    unittest.main()
