import json
from litellm import token_counter
from middleware.config import PRIMARY_MODEL, MODEL_MAX_TOKENS
from middleware.state import AgentState, SprintPlan
from middleware.database import db_manager
from middleware.rag import search_similar_tickets
from middleware.llm import aresilient_completion

def make_user_prompt(prd, gaps_val, codebase_val, tickets_val, feedback_val):
    parts = [
        f"<prd>\n{prd}\n</prd>",
        f"<gaps_identified>\n{gaps_val}\n</gaps_identified>"
    ]
    if codebase_val:
        parts.append(f"<codebase_context>\n{codebase_val}\n</codebase_context>")
    if tickets_val:
        parts.append(f"<historical_reference_tickets>\nUse these past tickets and their story-point estimations for calibration:\n{tickets_val}\n</historical_reference_tickets>")
    if feedback_val:
        parts.append(f"<em_feedback>\n{feedback_val}\n</em_feedback>")
    return "\n\n".join(parts)

async def estimator_node(state: AgentState):
    attempt = state.get("attempt_count", 0) + 1
    print(f"\n--- [Estimator Node] Generating Sprint Plan (Attempt {attempt}) ---")
    
    # Retrieve similar tickets from RAG pipeline
    try:
        raw_prd_query = state.get("raw_prd", "")[:500]
        similar_tickets = await search_similar_tickets(db_manager, raw_prd_query)
    except Exception as e:
        print(f"[Estimator] RAG retrieval failed ({e}), continuing without past references.")
        similar_tickets = []

    system_prompt = (
        "You are an expert Scrum Master. Break down the PRD, codebase context, gaps, and past reference tickets "
        "into a structured Sprint Plan consisting of estimated User Stories (Story) and Subtasks (Subtask). "
        "Calibrate your estimations against the provided historical reference tickets to maintain consistency. "
        "If engineering manager feedback is provided in the <em_feedback> block, you MUST revise the sprint plan "
        "and modify, add, delete, or refine the tickets to fully address all of their comments and suggestions. "
        "Ensure all outputs strictly comply with the Pydantic schema."
    )
    
    # Format similar tickets context
    formatted_similar_tickets = ""
    for t in similar_tickets:
        formatted_similar_tickets += f"- Ticket {t['ticket_key']}: {t['title']} (Estimation: {t['estimation']} SP, Priority: {t['priority']})\n  Description: {t['description']}\n"
    
    # Handle Engineering Manager revision feedback
    em_feedback = ""
    if state.get("em_feedback_comments"):
        print(f"[Estimator] Incorporating Engineering Manager Feedback: {state['em_feedback_comments']}")
        em_feedback += f"Engineering Manager feedback to address:\n{state['em_feedback_comments']}\n"
        if state.get("jira_tickets"):
            em_feedback += f"Previous draft tickets:\n{json.dumps(state['jira_tickets'], indent=2)}\n"

    raw_prd = state.get("raw_prd", "")
    gaps = state.get("missing_edge_cases", "") or ""
    codebase_summary = state.get("codebase_summary", "") or ""

    # Token Guard check and dynamic truncation logic
    user_prompt = make_user_prompt(raw_prd, gaps, codebase_summary, formatted_similar_tickets, em_feedback)
    full_prompt = system_prompt + "\n" + user_prompt
    
    tokens = token_counter(model=PRIMARY_MODEL, text=full_prompt)
    max_allowed = int(MODEL_MAX_TOKENS * 0.9)
    
    if tokens > max_allowed:
        print(f"[Estimator] Token count {tokens} exceeds 90% model max threshold ({max_allowed}). Truncating supplementary contexts...")
        # 1. Truncate codebase_summary first (if any)
        if codebase_summary:
            codebase_summary = codebase_summary[:len(codebase_summary) // 2]
            codebase_summary += "\n[...truncated due to context limits]"
            user_prompt = make_user_prompt(raw_prd, gaps, codebase_summary, formatted_similar_tickets, em_feedback)
            tokens = token_counter(model=PRIMARY_MODEL, text=system_prompt + "\n" + user_prompt)
            
        # If still too long, completely omit codebase summary
        if tokens > max_allowed and codebase_summary:
            codebase_summary = ""
            user_prompt = make_user_prompt(raw_prd, gaps, codebase_summary, formatted_similar_tickets, em_feedback)
            tokens = token_counter(model=PRIMARY_MODEL, text=system_prompt + "\n" + user_prompt)
            
        # If still too long, truncate historical tickets
        if tokens > max_allowed and formatted_similar_tickets:
            if len(similar_tickets) > 1:
                reduced_tickets = similar_tickets[:1]
                formatted_similar_tickets = ""
                for t in reduced_tickets:
                    formatted_similar_tickets += f"- Ticket {t['ticket_key']}: {t['title']} (Estimation: {t['estimation']} SP, Priority: {t['priority']})\n  Description: {t['description']}\n"
                formatted_similar_tickets += "\n[...truncated due to context limits]"
                user_prompt = make_user_prompt(raw_prd, gaps, codebase_summary, formatted_similar_tickets, em_feedback)
                tokens = token_counter(model=PRIMARY_MODEL, text=system_prompt + "\n" + user_prompt)
               
        # If still too long, completely omit historical tickets
        if tokens > max_allowed and formatted_similar_tickets:
            formatted_similar_tickets = ""
            user_prompt = make_user_prompt(raw_prd, gaps, codebase_summary, formatted_similar_tickets, em_feedback)

    response = await aresilient_completion(
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
        "em_approval_status": "PENDING",
        "attempt_count": attempt,
        "historical_context": similar_tickets
    }
