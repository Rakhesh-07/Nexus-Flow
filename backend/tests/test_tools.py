import pytest
from tools.calculator import CalculatorTool
from tools.python_executor import PythonExecutorTool
from tools.sql_runner import SQLRunnerTool
from tools.rest_client import RESTClientTool

def test_calculator_tool():
    calc = CalculatorTool()
    res = calc.execute(expression="3 * (10 + 5) - 2^3")
    # 3 * 15 - 8 = 45 - 8 = 37
    assert res == "37.0" or res == "37"

def test_calculator_invalid_syntax():
    calc = CalculatorTool()
    res = calc.execute(expression="3 + * 5")
    assert "Error" in res

def test_python_executor_success():
    executor = PythonExecutorTool()
    code = (
        "a = 10\n"
        "b = 20\n"
        "result = a + b\n"
        "print('Logging message')"
    )
    res = executor.execute(code=code)
    assert "Logging message" in res
    assert "Returned Result: 30" in res

def test_python_executor_safety():
    executor = PythonExecutorTool()
    # Try importing disallowed package os
    code = "import os\nresult = os.getcwd()"
    res = executor.execute(code=code)
    # import statement will fail under our restricted builtins
    assert "Execution Error" in res or "Security Error" in res or "name 'import' is not defined" in res or "disallowed" in res

def test_sql_runner_safety():
    runner = SQLRunnerTool()
    res = runner.execute(query="DELETE FROM users")
    assert "Security Error" in res

def test_sql_runner_success(db_session):
    runner = SQLRunnerTool()
    res = runner.execute(query="SELECT count(*) FROM sqlite_master")
    assert "Columns" in res
