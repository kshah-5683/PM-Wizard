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

# Pydantic models for structured output generation
class JiraTicket(BaseModel):
    key: str = Field(description="Unique temporary key, e.g. TICKET-1")
    type: str = Field(description="Type of issue: 'Epic', 'Story', or 'Subtask'")
    title: str = Field(description="A clear and concise title")
    description: str = Field(description="Detailed user story or task description including acceptance criteria")
    estimation: int = Field(description="Story points (Fibonacci sequence: 1, 2, 3, 5, 8, 13)")
    priority: str = Field(description="Priority: 'Highest', 'High', 'Medium', 'Low', 'Lowest'")

class SprintPlan(BaseModel):
    tickets: List[JiraTicket] = Field(description="List of proposed Jira tickets")
