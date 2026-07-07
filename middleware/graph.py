from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from middleware.state import AgentState
from middleware.nodes import (
    ingestion_node,
    critic_node,
    estimator_node,
    human_approval_node,
    push_to_jira_node
)

def should_continue(state: AgentState):
    if state["em_approval_status"] == "APPROVED":
        return "push_to_jira"
    elif state["em_approval_status"] == "REVISE":
        return "estimator"
    return END

# Build the LangGraph workflow
workflow = StateGraph(AgentState)

workflow.add_node("ingestion", ingestion_node)
workflow.add_node("critic", critic_node)
workflow.add_node("estimator", estimator_node)
workflow.add_node("human_approval", human_approval_node)
workflow.add_node("push_to_jira", push_to_jira_node)

workflow.add_edge(START, "ingestion")
workflow.add_edge("ingestion", "critic")
workflow.add_edge("critic", "estimator")
workflow.add_edge("estimator", "human_approval")

workflow.add_conditional_edges(
    "human_approval",
    should_continue,
    {
        "push_to_jira": "push_to_jira",
        "estimator": "estimator"
    }
)
workflow.add_edge("push_to_jira", END)

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)
