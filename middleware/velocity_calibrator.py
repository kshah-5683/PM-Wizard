from typing import List, Dict, Any

def calculate_sprint_velocity_multiplier(closed_tickets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes actual vs planned story point ratio and velocity multiplier for closed sprint issues.
    """
    if not closed_tickets:
        return {
            "planned_points": 0,
            "completed_points": 0,
            "velocity_multiplier": 1.0,
            "retrospective_lesson": "No sprint tickets provided for velocity calculation."
        }

    planned_points = 0
    completed_points = 0

    for t in closed_tickets:
        est = float(t.get("estimation") or 0)
        planned_points += est
        
        status = str(t.get("status") or "").upper()
        # If marked completed/done/closed, count completed points
        if status in ["DONE", "CLOSED", "RESOLVED", "COMPLETED"]:
            actual_est = float(t.get("completed_estimation") if t.get("completed_estimation") is not None else est)
            completed_points += actual_est

    velocity_multiplier = 1.0
    if planned_points > 0:
        velocity_multiplier = round(completed_points / planned_points, 2)

    lesson = f"Team completed {completed_points} out of {planned_points} planned story points (velocity factor: {velocity_multiplier}x)."
    if velocity_multiplier < 0.8:
        lesson += " Sprint suffered from scope creep or under-estimation; team velocity is slower than planned."
    elif velocity_multiplier > 1.2:
        lesson += " Team over-delivered relative to initial estimations."

    return {
        "planned_points": planned_points,
        "completed_points": completed_points,
        "velocity_multiplier": velocity_multiplier,
        "retrospective_lesson": lesson
    }

def format_velocity_calibration_context(velocity_data: Dict[str, Any]) -> str:
    """
    Formats sprint velocity metadata into a clean prompt callout for the Estimator agent.
    """
    mult = velocity_data.get("velocity_multiplier", 1.0)
    lesson = velocity_data.get("retrospective_lesson", "")
    
    return (
        f"📊 RETROSPECTIVE VELOCITY CALIBRATION (Historical Factor: {mult}x):\n"
        f"- {lesson}\n"
        f"- Instruction: Calibrate Fibonacci story point estimations taking this historical team velocity into account."
    )
