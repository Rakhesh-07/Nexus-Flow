import sys
import io
from typing import Any
from pydantic import BaseModel, Field
from tools.base_tool import BaseTool
from loguru import logger

class PythonExecutorArgs(BaseModel):
    code: str = Field(..., description="The Python code block to execute. Prints or defines a final 'result' variable.")

class PythonExecutorTool(BaseTool):
    name = "python_executor"
    description = "Executes arbitrary Python code and returns the stdout or 'result' variable. Use for complex math, data manipulation, or logic verification."
    args_schema = PythonExecutorArgs

    def execute(self, code: str) -> str:
        # Save current stdout
        old_stdout = sys.stdout
        redirected_output = sys.stdout = io.StringIO()
        
        # Define local namespace
        local_vars = {}
        # Restricted globals
        global_vars = {
            "__builtins__": {
                "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
                "dict": dict, "dir": dir, "divmod": divmod, "enumerate": enumerate,
                "float": float, "hash": hash, "hex": hex, "int": int, "len": len,
                "list": list, "map": map, "max": max, "min": min, "oct": oct,
                "ord": ord, "pow": pow, "range": range, "repr": repr, "reversed": reversed,
                "round": round, "set": set, "slice": slice, "sorted": sorted,
                "str": str, "sum": sum, "tuple": tuple, "zip": zip, "print": print
            }
        }
        
        try:
            # Execute code in sandbox
            exec(code, global_vars, local_vars)
            
            # Retrieve stdout
            stdout_output = redirected_output.getvalue()
            
            # Restore stdout
            sys.stdout = old_stdout
            
            # Compile return values
            response = ""
            if stdout_output:
                response += f"Stdout:\n{stdout_output}\n"
                
            if "result" in local_vars:
                response += f"Returned Result: {local_vars['result']}"
            elif not stdout_output:
                response += f"Execution complete. Local variables: {list(local_vars.keys())}"
                
            return response
            
        except Exception as e:
            # Restore stdout on failure
            sys.stdout = old_stdout
            logger.error(f"Python execution failed: {e}")
            return f"Execution Error: {str(e)}"
