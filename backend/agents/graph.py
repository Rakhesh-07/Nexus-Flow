from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes import (
    planner_node,
    retriever_node,
    researcher_node,
    tool_node,
    reasoner_node,
    validator_node,
    responder_node
)
from loguru import logger

# Conditional routing functions
def route_after_planner(state: AgentState) -> Literal["retriever", "tool"]:
    if state.get("needs_rag", False):
        logger.info("Planner decided: RAG context needed. Routing to Retriever.")
        return "retriever"
    else:
        logger.info("Planner decided: RAG not needed. Routing to Tool Agent directly.")
        return "tool"

def route_after_tool(state: AgentState) -> Literal["tool", "reasoner"]:
    current_index = state.get("current_step_index", 0)
    plan = state.get("plan", [])
    
    if current_index < len(plan):
        logger.info(f"Plan steps remaining ({current_index}/{len(plan)}). Looping back to Tool Agent.")
        return "tool"
    else:
        logger.info("All plan steps evaluated. Routing to Reasoner.")
        return "reasoner"

def route_after_validator(state: AgentState) -> Literal["reasoner", "responder"]:
    passed = state.get("validation_passed", False)
    attempts = state.get("validation_attempts", 0)
    
    if passed:
        logger.info("Validation passed. Routing to Responder.")
        return "responder"
    elif attempts >= 3:
        logger.info("Validation failed but exceeded maximum attempts (3). Forcing route to Responder.")
        return "responder"
    else:
        logger.warning(f"Validation failed (Attempt {attempts}/3). Routing back to Reasoner with feedback.")
        return "reasoner"

# Build the LangGraph StateGraph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("planner", planner_node)
workflow.add_node("retriever", retriever_node)
workflow.add_node("researcher", researcher_node)
workflow.add_node("tool", tool_node)
workflow.add_node("reasoner", reasoner_node)
workflow.add_node("validator", validator_node)
workflow.add_node("responder", responder_node)

# Set Entry Point
workflow.set_entry_point("planner")

# Add Conditional Edges from Planner
workflow.add_conditional_edges(
    "planner",
    route_after_planner,
    {
        "retriever": "retriever",
        "tool": "tool"
    }
)

# Add standard edges
workflow.add_edge("retriever", "researcher")
workflow.add_edge("researcher", "tool")

# Add Conditional Edges from Tool (Looping for multiple plan steps)
workflow.add_conditional_edges(
    "tool",
    route_after_tool,
    {
        "tool": "tool",
        "reasoner": "reasoner"
    }
)

# Add edge from Reasoner to Validator
workflow.add_edge("reasoner", "validator")

# Add Conditional Edges from Validator
workflow.add_conditional_edges(
    "validator",
    route_after_validator,
    {
        "reasoner": "reasoner",
        "responder": "responder"
    }
)

# Set End Node
workflow.add_edge("responder", END)

# Compile Graph
app_graph = workflow.compile()
logger.info("LangGraph workflow compiled successfully.")
