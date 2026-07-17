import ast
import operator
import math
from pydantic import BaseModel, Field
from tools.base_tool import BaseTool
from loguru import logger

class CalculatorArgs(BaseModel):
    expression: str = Field(..., description="The mathematical expression to evaluate (e.g. '(15 * 3) + 2^4')")

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Computes mathematical expressions containing arithmetic and power operations safely."
    args_schema = CalculatorArgs

    # Supported operators
    _operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: lambda x: x
    }

    def _eval(self, node):
        if isinstance(node, ast.Num): # Python < 3.8
            return node.n
        elif isinstance(node, ast.Constant): # Python >= 3.8
            return node.value
        elif isinstance(node, ast.BinOp):
            left = self._eval(node.left)
            right = self._eval(node.right)
            op_type = type(node.op)
            if op_type in self._operators:
                return self._operators[op_type](left, right)
            raise TypeError(f"Unsupported binary operator: {op_type}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand)
            op_type = type(node.op)
            if op_type in self._operators:
                return self._operators[op_type](operand)
            raise TypeError(f"Unsupported unary operator: {op_type}")
        raise TypeError(f"Unsupported expression node: {type(node)}")

    def execute(self, expression: str) -> str:
        # Pre-process caret to double asterisk for power operations
        expr_sanitized = expression.replace("^", "**").strip()
        try:
            # Parse expression string into AST tree
            tree = ast.parse(expr_sanitized, mode='eval')
            result = self._eval(tree.body)
            return str(result)
        except Exception as e:
            logger.error(f"Calculator failed to evaluate '{expression}': {e}")
            return f"Error: Failed to evaluate expression. {str(e)}"
