import os
import json
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from middleware.config import CRITIC_MODEL
from middleware.state import AgentState
from middleware.llm import aresilient_completion

class CritiqueItem(BaseModel):
    category: Literal["CRITICAL", "WARNING"] = Field(
        description="CRITICAL for non-negotiable gaps that block sprint planning; WARNING for negotiable advisories."
    )
    description: str = Field(description="Description of the identified gap, edge case, or vulnerability.")
    remediation: str = Field(description="Actionable step required to resolve or mitigate this gap.")
    rule_code: Optional[str] = Field(
        None,
        description="The code of the software engineering compliance rule violated (e.g. 'SEC-001', 'TEST-001'), or null if it does not violate any standard rule."
    )

class CriticOutput(BaseModel):
    critiques: List[CritiqueItem] = Field(description="List of critiques and gaps identified in the PRD.")

async def critic_node(state: AgentState):
    # Only critique on the first iteration to save rate limits
    if state.get("critiques"):
        return {}
        
    print("\n--- [Critic Node] Analyzing PRD against Compliance Checklists ---")
    
    # 1. Load rules checklist dynamically
    base_rules_list = []
    optional_rules_list = []
    
    try:
        rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "critic_rules.json")
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_data = json.load(f)
                base_rules_list = rules_data.get("base_rules", [])
                optional_rules_list = rules_data.get("optional_rules", [])
    except Exception as e:
        print(f"[Critic] Warning: Failed to load critic rules file: {e}")
        
    # Fallback to inline lists if file reading failed
    if not base_rules_list:
        base_rules_list = [
            {"code": "SEC-001", "title": "OAuth Token Leakage Risk", "description": "PRDs specifying third-party integrations must utilize secure OAuth handshakes and cryptographically store tokens; raw keys or secrets must never be passed in query params or plaintext headers."},
            {"code": "SEC-002", "title": "Unauthenticated REST Endpoints", "description": "Any endpoint mutating database state, retrieving user profiles, or accessing corporate data must require active authentication (JWT session tokens) and enforce strict RBAC checks."},
            {"code": "DB-001", "title": "Missing Schema Constraints", "description": "PRDs initiating new entities or tables must clearly outline primary/foreign keys, uniqueness constraints, nullability, and database types to prevent data corruption."},
            {"code": "API-001", "title": "Missing Pagination on Lists", "description": "API endpoints returning collections or search results must implement cursor or offset-based pagination to prevent memory exhaustion on large datasets."},
            {"code": "API-002", "title": "Missing Input Parameter Validation", "description": "Request payloads mutating database states must define strict parameter constraints, types (e.g. UUID, email format), and length validations to prevent SQL Injection or XSS."}
        ]
    if not optional_rules_list:
        optional_rules_list = [
            {"code": "TEST-001", "title": "Unit Test Specifications Required", "description": "The specification must detail automated testing requirements, coverage targets, or explicit unit test structures for new endpoints or features."},
            {"code": "DOC-001", "title": "API Documentation Specifications Required", "description": "Any new service or endpoint must detail raw request/response payloads, return schemas, error statuses, and markdown documentation templates."},
            {"code": "PERF-001", "title": "Caching Strategy Required", "description": "PRDs introducing heavy DB queries, complex tree walks, or external requests must specify cache behaviors (e.g. Redis, browser caching) to protect server load."}
        ]

    # 2. Filter optional rules enabled for this run
    enabled_codes = state.get("enabled_optional_rules") or []
    active_optional_rules = [r for r in optional_rules_list if r["code"] in enabled_codes]
    
    # 3. Format checklists for the system prompt
    base_text = "\n".join([f"- [{r['code']}] {r['title']}: {r['description']}" for r in base_rules_list])
    optional_text = "\n".join([f"- [{r['code']}] {r['title']}: {r['description']}" for r in active_optional_rules])
    
    rules_instruction = (
        "Audit the PRD and codebase context against the following mandatory Base Compliance Checklist:\n"
        f"{base_text}\n"
    )
    if active_optional_rules:
        rules_instruction += (
            "\nIn addition, audit against the following Custom/Optional Compliance Checklist enabled for this project:\n"
            f"{optional_text}\n"
        )
        
    system_prompt = (
        "You are a Senior Product Manager and Security Architect. Analyze the raw PRD, codebase context, "
        "and any sprint constraints, and identify critical edge cases, security vulnerabilities, or missing business logic gaps.\n\n"
        f"{rules_instruction}\n\n"
        "For each identified gap, determine the severity: CRITICAL (must halt and resolve) or WARNING (negotiable advisory).\n"
        "If a gap violates any checklist rule listed above, set 'rule_code' to that rule code (e.g. 'SEC-001', 'TEST-001'). Otherwise, set 'rule_code' to null.\n"
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
        rule_info = f" [{c['rule_code']}]" if c.get("rule_code") else ""
        markdown_lines.append(f"### {severity_badge}{rule_info}: {c['description'][:100]}")
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
