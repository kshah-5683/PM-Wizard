import json
from litellm import completion
from middleware.config import PRIMARY_MODEL
from middleware.state import AgentState, SprintPlan

def estimator_node(state: AgentState):
    print(f"\n--- [Estimator Node] Generating Sprint Plan (Attempt {state.get('attempt_count', 0) + 1}) ---")
    
    system_prompt = (
        "You are an expert Scrum Master. Break down the PRD and edge cases into a structured Sprint Plan "
        "consisting of estimated User Stories (Story) and Subtasks (Subtask). Ensure all outputs strictly "
        "comply with the Pydantic schema."
    )
    
    user_prompt = f"PRD:\n{state['raw_prd']}\n\nGaps identified:\n{state['missing_edge_cases']}"
    
    # Append EM revision feedback if it exists
    if state.get("em_feedback_comments"):
        print(f"[Estimator] Incorporating Engineering Manager Feedback: {state['em_feedback_comments']}")
        user_prompt += f"\n\nEngineering Manager feedback to address:\n{state['em_feedback_comments']}"
        if state.get("jira_tickets"):
            user_prompt += f"\n\nPrevious draft tickets:\n{json.dumps(state['jira_tickets'], indent=2)}"
            
    response = completion(
        model=PRIMARY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={
            "type": "json_object",
            "response_schema": SprintPlan.model_json_schema()
        }
    )
    
    parsed = json.loads(response.choices[0].message.content)
    validated = SprintPlan(**parsed)
    tickets = [t.model_dump() for t in validated.tickets]
    
    return {
        "jira_tickets": tickets,
        "em_approval_status": "PENDING"
    }
