import json
from pydantic import BaseModel, Field
from typing import List, Literal
from middleware.config import CRITIC_MODEL
from middleware.state import AgentState
from middleware.llm import aresilient_completion

class CritiqueItem(BaseModel):
    category: Literal["CRITICAL", "WARNING"] = Field(
        description="CRITICAL for non-negotiable gaps that block sprint planning; WARNING for negotiable advisories."
    )
    description: str = Field(description="Description of the identified gap, edge case, or vulnerability.")
    remediation: str = Field(description="Actionable step required to resolve or mitigate this gap.")

class CriticOutput(BaseModel):
    critiques: List[CritiqueItem] = Field(description="List of critiques and gaps identified in the PRD.")

async def critic_node(state: AgentState):
    # Only critique on the first iteration to save rate limits
    if state.get("critiques"):
        return {}
        
    print("\n--- [Critic Node] Analyzing PRD for Gaps & Edge Cases ---")
    system_prompt = (
        "You are a Senior Product Manager and Security Architect. Analyze the raw PRD, codebase context, "
        "and any sprint constraints, and identify critical edge cases, security vulnerabilities, or missing business logic gaps. "
        "Determine the severity of each gap: CRITICAL (must halt and resolve) or WARNING (negotiable advisory). "
        "Ensure all outputs comply with the Pydantic schema."
    )
    
    user_prompt = f"PRD:\n{state['raw_prd']}"
    if state.get("workspace_profile"):
        user_prompt += f"\n\n<workspace_profile>\n{state['workspace_profile']}\n</workspace_profile>"
    if state.get("sprint_constraints"):
        user_prompt += f"\n\n<sprint_constraints>\n{state['sprint_constraints']}\n</sprint_constraints>"
    if state.get("codebase_summary"):
        user_prompt += f"\n\n<codebase_context>\n{state['codebase_summary']}\n</codebase_context>"

    response = await aresilient_completion(
        model=CRITIC_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={
            "type": "json_object",
            "response_schema": CriticOutput.model_json_schema()
        }
    )
    
    parsed = json.loads(response.choices[0].message.content)
    validated = CriticOutput(**parsed)
    
    # Sort so CRITICAL appears first
    sorted_critiques = sorted(
        [c.model_dump() for c in validated.critiques],
        key=lambda x: 0 if x["category"] == "CRITICAL" else 1
    )
    
    # Build markdown summary for missing_edge_cases
    markdown_lines = []
    for c in sorted_critiques:
        severity_badge = "🔴 CRITICAL" if c["category"] == "CRITICAL" else "⚠️ WARNING"
        markdown_lines.append(f"### {severity_badge}: {c['description'][:100]}")
        markdown_lines.append(f"**Description**: {c['description']}")
        markdown_lines.append(f"**Remediation**: {c['remediation']}\n")
    
    markdown_summary = "\n".join(markdown_lines).strip()
    
    try:
        print("\n[Critic Gaps & Edge Cases identified]:")
        print(markdown_summary)
        print("-" * 50)
    except Exception:
        pass
    
    return {
        "critiques": sorted_critiques,
        "missing_edge_cases": markdown_summary,
        "critic_resolved": False
    }
