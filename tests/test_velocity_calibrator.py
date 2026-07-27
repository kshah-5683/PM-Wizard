import pytest
from middleware.velocity_calibrator import calculate_sprint_velocity_multiplier, format_velocity_calibration_context

def test_velocity_multiplier_calculation():
    tickets = [
        {"key": "TICKET-1", "estimation": 5, "completed_estimation": 5, "status": "DONE"},
        {"key": "TICKET-2", "estimation": 3, "completed_estimation": 5, "status": "DONE"},
        {"key": "TICKET-3", "estimation": 2, "completed_estimation": 0, "status": "IN_PROGRESS"}
    ]
    res = calculate_sprint_velocity_multiplier(tickets)
    
    assert res["planned_points"] == 10
    assert res["completed_points"] == 10
    assert res["velocity_multiplier"] == 1.0
    assert "Team completed 10.0 out of 10.0 planned story points" in res["retrospective_lesson"]

def test_velocity_calibration_formatting():
    data = {
        "velocity_multiplier": 1.25,
        "retrospective_lesson": "Team over-delivered relative to initial estimations."
    }
    formatted = format_velocity_calibration_context(data)
    assert "Historical Factor: 1.25x" in formatted
    assert "Team over-delivered" in formatted
