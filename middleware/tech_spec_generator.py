import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from middleware.llm import aresilient_completion, PRIMARY_MODEL

class TechSpecOutput(BaseModel):
    ticket_key: str = Field(description="Ticket key, e.g. TICKET-1")
    target_file_paths: List[str] = Field(description="List of target relative file paths to modify or create, e.g. ['src/components/Modal.jsx']")
    developer_checklist: List[str] = Field(description="High-level step-by-step developer implementation checklist")

async def generate_ticket_tech_spec(
    ticket: Dict[str, Any], 
    codebase_summary: Optional[str] = "", 
    raw_prd: Optional[str] = ""
) -> Dict[str, Any]:
    """
    Generates a lightweight technical specification and developer implementation checklist
    for a given Jira ticket using static codebase_summary and raw_prd context.
    """
    ticket_key = ticket.get("key") or ticket.get("ticket_key") or "TICKET-1"
    title = ticket.get("title", "")
    description = ticket.get("description", "")
    ticket_type = ticket.get("type", "Story")
    
    system_prompt = (
        "You are an expert Lead Principal Software Architect. Your job is to produce a lightweight, "
        "ultra-focused technical specification for a developer picking up a Jira ticket.\n"
        "Analyze the ticket title, description, codebase summary, and PRD.\n"
        "Output ONLY:\n"
        "1. A list of 2-5 exact target relative file paths in the codebase that should be modified or created.\n"
        "2. A high-level step-by-step developer implementation checklist (3-6 bullet points).\n"
        "Keep the specification concise, token-efficient, and practical."
    )
    
    user_prompt = (
        f"Target Ticket: [{ticket_key}] ({ticket_type}) {title}\n"
        f"Ticket Description:\n{description}\n\n"
        f"Codebase Summary:\n{codebase_summary or 'No codebase summary available.'}\n\n"
        f"PRD Context (truncated):\n{(raw_prd or '')[:1000]}"
    )
    
    try:
        response = await aresilient_completion(
            model=PRIMARY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_object",
                "response_schema": TechSpecOutput.model_json_schema()
            }
        )
        parsed = json.loads(response.choices[0].message.content)
        validated = TechSpecOutput(**parsed)
        spec_dict = validated.model_dump()
    except Exception as e:
        print(f"[TechSpec] Failed to generate LLM tech spec ({e}). Returning fallback spec.")
        spec_dict = {
            "ticket_key": ticket_key,
            "target_file_paths": ["src/app/page.js", "middleware/state.py"],
            "developer_checklist": [
                f"Review requirements for {title}",
                "Implement target logic according to acceptance criteria",
                "Verify E2E integration and unit test coverage"
            ]
        }

    # Format clean markdown string representation
    file_list_md = "\n".join([f"- `{p}`" for p in spec_dict.get("target_file_paths", [])])
    checklist_md = "\n".join([f"- [ ] {item}" for item in spec_dict.get("developer_checklist", [])])
    
    spec_dict["markdown_summary"] = (
        f"### 🛠️ Developer Technical Specification: {ticket_key}\n\n"
        f"**Target File Paths:**\n{file_list_md}\n\n"
        f"**Developer Implementation Checklist:**\n{checklist_md}"
    )
    
    return spec_dict
