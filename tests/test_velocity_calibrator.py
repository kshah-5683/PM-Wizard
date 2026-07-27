import unittest
from middleware.velocity_calibrator import calculate_sprint_velocity_multiplier, format_velocity_calibration_context

class TestVelocityCalibrator(unittest.TestCase):
    def test_velocity_multiplier_calculation(self):
        tickets = [
            {"key": "TICKET-1", "estimation": 5, "completed_estimation": 5, "status": "DONE"},
            {"key": "TICKET-2", "estimation": 3, "completed_estimation": 5, "status": "DONE"},
            {"key": "TICKET-3", "estimation": 2, "completed_estimation": 0, "status": "IN_PROGRESS"}
        ]
        res = calculate_sprint_velocity_multiplier(tickets)
        
        self.assertEqual(res["planned_points"], 10)
        self.assertEqual(res["completed_points"], 10)
        self.assertEqual(res["velocity_multiplier"], 1.0)
        self.assertIn("Team completed 10.0 out of 10.0 planned story points", res["retrospective_lesson"])

    def test_velocity_calibration_formatting(self):
        data = {
            "velocity_multiplier": 1.25,
            "retrospective_lesson": "Team over-delivered relative to initial estimations."
        }
        formatted = format_velocity_calibration_context(data)
        self.assertIn("Historical Factor: 1.25x", formatted)
        self.assertIn("Team over-delivered", formatted)

if __name__ == "__main__":
    unittest.main()
