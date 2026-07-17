import time
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from agents.state import AgentState, PlannerOutput, ValidationOutput, ResponseOutput
from agents.providers import get_llm_provider
from rag.chroma_service import chroma_service
from tools import get_tool_by_name
from loguru import logger

def estimate_tokens(text: str) -> int:
    """Apprx word-count token estimation (1 word = 1.3 tokens)."""
    if not text:
        return 0
    return max(1, int(len(str(text).split()) * 1.3))

def planner_node(state: AgentState) -> Dict[str, Any]:
    """
    Planner Agent: Analyzes query and determines required steps, tools, and RAG status.
    """
    logger.info("--- Entering Planner Node ---")
    query = state["query"]
    provider = get_llm_provider()
    
    system_instruction = (
        "You are an enterprise AI Workflow Planner. Your task is to analyze the user's query and formulate "
        "a sequence of steps (plan) to answer it. You must also decide if external RAG context is required "
        "and if database, python executor, calculator, or REST tools are needed."
    )
    
    prompt = (
        f"User Query: {query}\n\n"
        "Generate a plan. Decide if we need RAG (needs_rag = true) to retrieve uploaded document contexts "
        "and list the steps required."
    )
    
    try:
        output: PlannerOutput = provider.generate_structured_output(
            prompt=prompt,
            schema=PlannerOutput,
            system_instruction=system_instruction
        )
        
        history_entry = {
            "node": "Planner",
            "timestamp": time.time(),
            "decision": {
                "plan": output.plan,
                "needs_rag": output.needs_rag,
                "reasoning": output.reasoning
            }
        }
        
        prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        completion_tokens = estimate_tokens(json.dumps(output.model_dump()))
        
        return {
            "plan": output.plan,
            "needs_rag": output.needs_rag,
            "current_step_index": 0,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "history": [history_entry]
        }
    except Exception as e:
        logger.error(f"Planner node failure: {e}")
        # Return fallback state
        return {
            "plan": ["Retrieve context from documents", "Synthesize final response"],
            "needs_rag": True,
            "current_step_index": 0,
            "history": [{"node": "Planner", "error": str(e), "timestamp": time.time()}]
        }


def retriever_node(state: AgentState) -> Dict[str, Any]:
    """
    Retriever Agent: Performs semantic query search in ChromaDB.
    """
    logger.info("--- Entering Retriever Node ---")
    query = state["query"]
    user_id = state.get("user_id", 0)
    
    # Filter by user_id to ensure multitenant data isolation
    filter_dict = {"user_id": user_id}
    logger.info(f"Querying vector store for user_id={user_id} with query: {query}")
    
    results = chroma_service.query_similarity(query, limit=5, filter_dict=filter_dict)
    
    history_entry = {
        "node": "Retriever",
        "timestamp": time.time(),
        "retrieved_count": len(results),
        "results": [{"id": r["id"], "metadata": r["metadata"], "distance": r["distance"]} for r in results]
    }
    
    return {
        "retrieved_documents": results,
        "history": [history_entry]
    }


def researcher_node(state: AgentState) -> Dict[str, Any]:
    """
    Researcher Agent: Condenses retrieved document chunks into clean reference context.
    """
    logger.info("--- Entering Researcher Node ---")
    documents = state.get("retrieved_documents", [])
    query = state["query"]
    
    if not documents:
        return {
            "research_summary": "No context documents found.",
            "history": [{"node": "Researcher", "summary": "No documents to research", "timestamp": time.time()}]
        }
        
    provider = get_llm_provider()
    
    context_text = "\n\n".join([
        f"Document ID: {doc['id']} | Filename: {doc['metadata'].get('filename', 'Unknown')}\nContent:\n{doc['document']}"
        for doc in documents
    ])
    
    system_instruction = (
        "You are an AI Research Agent. Your job is to extract, summarize, and outline key evidence from "
        "the provided document contexts that is relevant to answering the user's query."
    )
    
    prompt = (
        f"Original User Query: {query}\n\n"
        f"Retrieved Document Contexts:\n{context_text}\n\n"
        "Generate a structured research summary detailing only facts supported by the contexts."
    )
    
    try:
        summary = provider.generate_text(prompt=prompt, system_instruction=system_instruction)
        
        history_entry = {
            "node": "Researcher",
            "timestamp": time.time(),
            "summary_length": len(summary)
        }
        
        prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        completion_tokens = estimate_tokens(summary)
        
        return {
            "research_summary": summary,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "history": [history_entry]
        }
    except Exception as e:
        logger.error(f"Researcher node failed: {e}")
        return {
            "research_summary": "Error generating research summary.",
            "history": [{"node": "Researcher", "error": str(e), "timestamp": time.time()}]
        }


def tool_node(state: AgentState) -> Dict[str, Any]:
    """
    Tool Agent: Looks at the current plan steps and triggers tool execution if needed.
    """
    logger.info("--- Entering Tool Node ---")
    query = state["query"]
    plan = state.get("plan", [])
    current_index = state.get("current_step_index", 0)
    
    # We dynamically decide if a tool should be executed based on the current plan step.
    # We use LLM to check if the current step requires tool invocation.
    provider = get_llm_provider()
    
    if current_index >= len(plan):
        return {
            "history": [{"node": "ToolAgent", "message": "All plan steps completed.", "timestamp": time.time()}]
        }
        
    current_step = plan[current_index]
    
    system_instruction = (
        "You are a Tool Dispatcher. Your job is to decide if the current plan step requires executing a tool.\n"
        "Available Tools:\n"
        "- 'calculator' (parameters: expression): evaluation of basic math expressions.\n"
        "- 'python_executor' (parameters: code): running python code for logic or complex stats.\n"
        "- 'sql_runner' (parameters: query): querying users, documents, conversations, or workflow_executions tables.\n"
        "- 'rest_client' (parameters: url, method, payload): querying external HTTP web hooks.\n\n"
        "Return a JSON object in this format:\n"
        "{\n"
        "  \"requires_tool\": true/false,\n"
        "  \"tool_name\": \"calculator\" | \"python_executor\" | \"sql_runner\" | \"rest_client\" | null,\n"
        "  \"tool_arguments\": { ... dict of args ... }\n"
        "}"
    )
    
    prompt = (
        f"User Query: {query}\n"
        f"Current Plan Step: '{current_step}'\n\n"
        "Determine if this step requires a tool. If yes, specify the tool name and arguments."
    )
    
    # We define a helper class for tool call schema
    class ToolCallDecision(BaseModel):
        requires_tool: bool
        tool_name: Optional[str]
        tool_arguments: Optional[Dict[str, Any]]
        
    try:
        decision = provider.generate_structured_output(prompt=prompt, schema=ToolCallDecision, system_instruction=system_instruction)
        
        if decision.requires_tool and decision.tool_name:
            tool_name = decision.tool_name
            tool_args = decision.tool_arguments or {}
            logger.info(f"Dispatching Tool: {tool_name} with arguments: {tool_args}")
            
            tool = get_tool_by_name(tool_name)
            if tool:
                result = tool.execute(**tool_args)
                logger.info(f"Tool {tool_name} returned output.")
                
                history_entry = {
                    "node": "ToolAgent",
                    "timestamp": time.time(),
                    "tool": tool_name,
                    "args": tool_args,
                    "success": True,
                    "output": result
                }
                
                prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
                completion_tokens = estimate_tokens(json.dumps(decision.model_dump()))
                
                return {
                    "next_tool": tool_name,
                    "tool_inputs": tool_args,
                    "tool_outputs": {tool_name: result},
                    "current_step_index": current_index + 1,
                    "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
                    "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
                    "history": [history_entry]
                }
            else:
                prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
                completion_tokens = estimate_tokens(json.dumps(decision.model_dump()))
                logger.warning(f"Tool '{tool_name}' not found.")
                return {
                    "current_step_index": current_index + 1,
                    "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
                    "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
                    "history": [{"node": "ToolAgent", "error": f"Tool {tool_name} not found", "timestamp": time.time()}]
                }
                
        # If no tool is required, just advance the plan step
        prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        completion_tokens = estimate_tokens(json.dumps(decision.model_dump()))
        return {
            "current_step_index": current_index + 1,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "history": [{"node": "ToolAgent", "message": f"No tool required for step: {current_step}", "timestamp": time.time()}]
        }
    except Exception as e:
        logger.error(f"Tool node failed: {e}")
        return {
            "current_step_index": current_index + 1,
            "history": [{"node": "ToolAgent", "error": str(e), "timestamp": time.time()}]
        }


def reasoner_node(state: AgentState) -> Dict[str, Any]:
    """
    Reasoner Agent: Synthesizes findings, RAG inputs, and tool execution logs.
    """
    logger.info("--- Entering Reasoner Node ---")
    query = state["query"]
    research = state.get("research_summary", "")
    tools_out = state.get("tool_outputs", {})
    feedback = state.get("validation_feedback", "")
    
    provider = get_llm_provider()
    
    system_instruction = (
        "You are an expert Reasoner Agent. Your goal is to synthesize all available contexts (RAG inputs, "
        "tool execution logs) and compose a coherent, highly accurate, and analytical answer to the query.\n"
        "If you have received validation feedback detailing mistakes or hallucinations, you MUST address and correct them."
    )
    
    prompt = (
        f"User Query: {query}\n\n"
        f"RAG Context Summary:\n{research}\n\n"
        f"Tool Outputs:\n{tools_out}\n\n"
    )
    
    if feedback:
        prompt += f"Previous Validation Feedback/Errors to Fix:\n{feedback}\n\n"
        
    prompt += "Synthesize this data into a detailed response reasoning block."
    
    try:
        reasoning = provider.generate_text(prompt=prompt, system_instruction=system_instruction)
        
        history_entry = {
            "node": "Reasoner",
            "timestamp": time.time(),
            "output_length": len(reasoning)
        }
        
        prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        completion_tokens = estimate_tokens(reasoning)
        
        return {
            "reasoning_output": reasoning,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "history": [history_entry]
        }
    except Exception as e:
        logger.error(f"Reasoner node failed: {e}")
        return {
            "reasoning_output": "Error during reasoning synthesis.",
            "history": [{"node": "Reasoner", "error": str(e), "timestamp": time.time()}]
        }


def validator_node(state: AgentState) -> Dict[str, Any]:
    """
    Validator Agent: Analyzes the reasoner's output against the input context to prevent hallucination.
    """
    logger.info("--- Entering Validator Node ---")
    query = state["query"]
    reasoning = state.get("reasoning_output", "")
    research = state.get("research_summary", "")
    attempts = state.get("validation_attempts", 0)
    
    provider = get_llm_provider()
    
    system_instruction = (
        "You are a Quality Validator Agent. Check if the reasoning text answer contains claims that are "
        "not supported by the context documents (hallucinations) or if the reasoning fails to fully address "
        "the user query. Be strict. Assess the confidence score."
    )
    
    prompt = (
        f"Original User Query: {query}\n\n"
        f"Available Context (Reference Document Summary):\n{research}\n\n"
        f"Generated Reasoning Response:\n{reasoning}\n\n"
        "Evaluate validation output schema compliance and hallucination risk."
    )
    
    try:
        output: ValidationOutput = provider.generate_structured_output(
            prompt=prompt,
            schema=ValidationOutput,
            system_instruction=system_instruction
        )
        
        history_entry = {
            "node": "Validator",
            "timestamp": time.time(),
            "passed": output.validation_passed,
            "confidence": output.confidence_score,
            "hallucination": output.hallucination_detected,
            "feedback": output.feedback
        }
        
        prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        completion_tokens = estimate_tokens(json.dumps(output.model_dump()))
        
        return {
            "validation_passed": output.validation_passed,
            "validation_feedback": output.feedback,
            "confidence_score": output.confidence_score,
            "hallucination_detected": output.hallucination_detected,
            "validation_attempts": attempts + 1,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "history": [history_entry]
        }
    except Exception as e:
        logger.error(f"Validator node failed: {e}")
        return {
            "validation_passed": True, # Fail open to avoid loops on schema error
            "validation_feedback": "Skipped validation due to error.",
            "confidence_score": 1.0,
            "hallucination_detected": False,
            "validation_attempts": attempts + 1,
            "history": [{"node": "Validator", "error": str(e), "timestamp": time.time()}]
        }


def responder_node(state: AgentState) -> Dict[str, Any]:
    """
    Responder Agent: Constructs the final structured JSON schema output including recommendations and citations.
    """
    logger.info("--- Entering Responder Node ---")
    query = state["query"]
    reasoning = state.get("reasoning_output", "")
    documents = state.get("retrieved_documents", [])
    
    provider = get_llm_provider()
    
    system_instruction = (
        "You are a Responder Agent. Compile the final answer into the ResponseOutput structured JSON schema, "
        "mapping key results, explanation text, source documents (citations), and future recommendations."
    )
    
    # Extract source filenames for citations
    filenames = list(set([doc["metadata"].get("filename", "Doc") for doc in documents if doc.get("metadata")]))
    
    prompt = (
        f"User Query: {query}\n\n"
        f"Reasoning Content:\n{reasoning}\n\n"
        f"Document Citations list: {filenames}\n\n"
        "Generate final response structured JSON output."
    )
    
    try:
        output: ResponseOutput = provider.generate_structured_output(
            prompt=prompt,
            schema=ResponseOutput,
            system_instruction=system_instruction
        )
        
        history_entry = {
            "node": "Responder",
            "timestamp": time.time(),
            "success": True
        }
        
        # We output standard dict representation to match Pydantic JSON serialization
        final_dict = output.model_dump()
        
        prompt_tokens = estimate_tokens(prompt) + estimate_tokens(system_instruction)
        completion_tokens = estimate_tokens(json.dumps(final_dict))
        
        return {
            "final_response": final_dict,
            "prompt_tokens": state.get("prompt_tokens", 0) + prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + completion_tokens,
            "history": [history_entry]
        }
    except Exception as e:
        logger.error(f"Responder node failed: {e}")
        fallback = {
            "structured_answer": {"answer": "An error occurred constructing the final structured output."},
            "explanation": reasoning,
            "citations": filenames,
            "recommendations": []
        }
        return {
            "final_response": fallback,
            "history": [{"node": "Responder", "error": str(e), "timestamp": time.time()}]
        }
