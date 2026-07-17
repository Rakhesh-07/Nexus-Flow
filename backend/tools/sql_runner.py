from pydantic import BaseModel, Field
from tools.base_tool import BaseTool
from database.database import engine
from sqlalchemy import text
from loguru import logger

class SQLRunnerArgs(BaseModel):
    query: str = Field(..., description="The SELECT SQL query to execute against the local application database (e.g. 'SELECT count(*) FROM users')")

class SQLRunnerTool(BaseTool):
    name = "sql_runner"
    description = "Executes read-only SQL queries against the local database schema (tables: users, documents, conversations, workflow_executions)."
    args_schema = SQLRunnerArgs

    def execute(self, query: str) -> str:
        # Safety check: enforce read-only SELECT
        normalized_query = query.strip().upper()
        if not normalized_query.startswith("SELECT") and not normalized_query.startswith("WITH"):
            return "Security Error: Only SELECT queries are permitted for safety reasons."
        
        # Additional safety check for dangerous write keywords
        dangerous_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
        for kw in dangerous_keywords:
            if f" {kw} " in f" {normalized_query} ":
                return f"Security Error: Prohibited write operation keyword detected: '{kw}'."

        try:
            logger.info(f"Executing SQL Runner Query: {query}")
            with engine.connect() as connection:
                result = connection.execute(text(query))
                
                # Fetch headers
                keys = list(result.keys())
                
                # Fetch rows
                rows = result.fetchall()
                
                if not rows:
                    return f"Query returned 0 rows. Columns: {keys}"
                
                # Format output as a text table
                output = f"Columns: {', '.join(keys)}\n"
                output += "-" * 40 + "\n"
                for row in rows[:50]: # Limit to 50 rows
                    row_values = [str(val) for val in row]
                    output += " | ".join(row_values) + "\n"
                    
                if len(rows) > 50:
                    output += f"... (truncated, total rows: {len(rows)})"
                return output
                
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return f"Database Query Error: {str(e)}"
