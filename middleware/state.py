from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field

# In LangGraph, if a piece of data isn't in this state, it ceases to exist.
class AgentState(TypedDict):
    raw_prd: str
    codebase_summary: Optional[str]
    missing_edge_cases: Optional[str]
    jira_tickets: Optional[List[Dict[str, Any]]]
    em_approval_status: str
    em_feedback_comments: Optional[str]
    prd_images_context: Optional[List[Dict[str, str]]]
    attempt_count: int
    historical_context: Optional[List[Dict[str, Any]]]  # NEW: RAG reference tickets
    workspace_profile: Optional[str]  # NEW: Auto-inferred tech stack & repo profiling
    sprint_constraints: Optional[str]  # NEW: Dynamic EM constraints passed JIT
    custom_tags: Optional[List[str]]  # NEW: Custom tagging context
    enabled_optional_rules: Optional[List[str]]  # NEW: List of optional compliance rules enabled for this run
    critiques: Optional[List[Dict[str, Any]]]  # NEW: Structured critique items from critic node
    critic_resolved: bool  # NEW: Flag indicating if critical issues have been bypassed or resolved
    org_id: Optional[str]  # NEW: Multi-tenant organization identifier
    user_id: Optional[str]  # NEW: User UUID for resolving OAuth connections
    github_repo: Optional[str]  # NEW: Target remote repository (owner/repo)
    jira_project_key: Optional[str]  # NEW: Target Jira project key (e.g. 'PROJ')
    project_mode: Optional[str]  # 'BROWNFIELD' or 'GREENFIELD'
    warnings: Optional[List[Dict[str, str]]]  # NEW: Degraded execution or non-fatal warning tracking
    max_revisions_exceeded: Optional[bool]  # NEW: Flag when revision circuit breaker (max 3) is hit


# Pydantic models for structured output generation
class JiraTicket(BaseModel):
    key: str = Field(description="Unique temporary key, e.g. TICKET-1")
    type: str = Field(description="Type of issue: 'Epic', 'Story', or 'Subtask'")
    title: str = Field(description="A clear and concise title")
    description: str = Field(description="Detailed user story or task description including acceptance criteria")
    estimation: int = Field(description="Story points (Fibonacci sequence: 1, 2, 3, 5, 8, 13)")
    priority: str = Field(description="Priority: 'Highest', 'High', 'Medium', 'Low', 'Lowest'")
    parent_key: Optional[str] = Field(default=None, description="Key of parent Epic (for Story) or parent Story (for Subtask), e.g. TICKET-1")
    blocked_by: Optional[List[str]] = Field(default_factory=list, description="Keys of tickets that block this ticket")
    jira_issue_id: Optional[str] = Field(default=None, description="Synced Atlassian Jira Issue Key/ID once published")
    confidence_level: Optional[str] = Field(default="MEDIUM", description="Estimation confidence level: 'HIGH', 'MEDIUM', or 'LOW'")
    estimation_rationale: Optional[str] = Field(default=None, description="Short rationale for the estimated story points")

class SprintPlan(BaseModel):
    tickets: List[JiraTicket] = Field(description="List of proposed Jira tickets")

