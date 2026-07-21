from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from pydantic import BaseModel, Field


# Pydantic schemas for LLM structured outputs
class PlannerOutput(BaseModel):
    plan: List[str] = Field(..., description="Chronological list of steps to solve the query.")
    needs_rag: bool = Field(..., description="True if external context/uploaded files are needed to answer the query.")
    reasoning: str = Field(..., description="Brief rationale for the generated plan.")

class ValidationOutput(BaseModel):
    validation_passed: bool = Field(..., description="True if response meets compliance, contains no hallucinations, and answers the query.")
    feedback: str = Field(..., description="Feedback detailing any issues or confirmation of success.")
    confidence_score: float = Field(..., description="Confidence score from 0.0 to 1.0.")
    hallucination_detected: bool = Field(..., description="True if reasoning contains claims unsupported by retrieved contexts.")

class ResponseOutput(BaseModel):
    structured_answer: Dict[str, Any] = Field(..., description="JSON structured output containing the final answers or calculated outputs.")
    explanation: str = Field(..., description="Detailed text explanation of the results.")
    citations: List[str] = Field(default=[], description="List of source files or tools referenced to produce the answer.")
    recommendations: List[str] = Field(default=[], description="Actionable recommendations based on the findings.")


# TypedDict representing the active LangGraph workflow state
class AgentState(TypedDict):
    # Core input/output
    query: str
    final_response: Optional[Dict[str, Any]]
    
    # User details for enterprise RBAC and data isolation
    user_id: int
    user_name: Optional[str]
    user_department: Optional[str]
    user_role: Optional[str]
    user_clearance: Optional[str]
    
    # Planner decision
    plan: List[str]
    current_step_index: int
    needs_rag: bool
    
    # Context collection
    retrieved_documents: List[Dict[str, Any]]
    research_summary: str
    
    # Tool inputs and outputs
    next_tool: Optional[str]
    tool_inputs: Optional[Dict[str, Any]]
    tool_outputs: Annotated[Dict[str, Any], lambda a, b: {**(a or {}), **(b or {})}]
    
    # Reasoner synthesis
    reasoning_output: str
    
    # Validation loops
    validation_passed: bool
    validation_feedback: str
    confidence_score: float
    hallucination_detected: bool
    validation_attempts: int
    
    # Detailed execution log trace
    history: Annotated[List[Dict[str, Any]], operator.add]
    
    # Token usage analytics tracking
    prompt_tokens: int
    completion_tokens: int

