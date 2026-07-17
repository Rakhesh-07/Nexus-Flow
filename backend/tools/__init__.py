from tools.python_executor import PythonExecutorTool
from tools.rest_client import RESTClientTool
from tools.sql_runner import SQLRunnerTool
from tools.calculator import CalculatorTool

def get_all_tools():
    return [
        PythonExecutorTool(),
        RESTClientTool(),
        SQLRunnerTool(),
        CalculatorTool()
    ]

def get_tool_by_name(name: str):
    for tool in get_all_tools():
        if tool.name == name:
            return tool
    return None
