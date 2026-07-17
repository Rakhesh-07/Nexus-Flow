from typing import Optional, Dict, Any
import httpx
from pydantic import BaseModel, Field
from tools.base_tool import BaseTool
from loguru import logger

class RESTClientArgs(BaseModel):
    url: str = Field(..., description="The fully qualified URL to target (e.g. https://api.github.com)")
    method: str = Field(default="GET", description="HTTP Method (GET, POST, PUT, DELETE)")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Optional HTTP Request Headers")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="Optional JSON Body for POST/PUT requests")

class RESTClientTool(BaseTool):
    name = "rest_client"
    description = "Performs REST HTTP requests (GET, POST, etc.) to query external APIs and retrieve web database information."
    args_schema = RESTClientArgs

    def execute(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, payload: Optional[Dict[str, Any]] = None) -> str:
        method = method.upper()
        try:
            logger.info(f"Executing REST Client: {method} {url}")
            with httpx.Client(timeout=10.0) as client:
                if method == "GET":
                    response = client.get(url, headers=headers)
                elif method == "POST":
                    response = client.post(url, headers=headers, json=payload)
                elif method == "PUT":
                    response = client.put(url, headers=headers, json=payload)
                elif method == "DELETE":
                    response = client.delete(url, headers=headers)
                else:
                    return f"Unsupported method: {method}"
                
                status_code = response.status_code
                content_type = response.headers.get("content-type", "")
                
                # Format output nicely
                try:
                    body = response.json()
                    import json
                    body_str = json.dumps(body, indent=2)
                except Exception:
                    body_str = response.text
                    
                return f"Status Code: {status_code}\nContent-Type: {content_type}\nBody:\n{body_str[:1500]}"
                
        except Exception as e:
            logger.error(f"REST call failed: {e}")
            return f"HTTP Request Failed: {str(e)}"
