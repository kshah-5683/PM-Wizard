from litellm import completion
from middleware.config import CRITIC_MODEL
from middleware.state import AgentState

def critic_node(state: AgentState):
    # Only critique on the first iteration to save rate limits
    if state.get("missing_edge_cases"):
        return {}
        
    print("\n--- [Critic Node] Analyzing PRD for Gaps & Edge Cases ---")
    system_prompt = (
        "You are a Senior Product Manager and Security Architect. Analyze the raw PRD and identify "
        "at least 3 critical edge cases, security vulnerabilities, or missing business logic gaps that need "
        "to be resolved before technical task breakdown. Respond in clean Markdown."
    )
    
    response = completion(
        model=CRITIC_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"PRD:\n{state['raw_prd']}"}
        ]
    )
    
    critique = response.choices[0].message.content.strip()
    print("\n[Critic Gaps & Edge Cases identified]:")
    print(critique)
    print("-" * 50)
    return {"missing_edge_cases": critique}
