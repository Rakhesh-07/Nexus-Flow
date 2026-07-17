from typing import Any, Dict, Type
from pydantic import BaseModel

class BaseTool:
    name: str
    description: str
    args_schema: Type[BaseModel]

    def execute(self, **kwargs) -> Any:
        """
        Execute the tool synchronously with the parsed arguments.
        """
        raise NotImplementedError

    async def execute_async(self, **kwargs) -> Any:
        """
        Execute the tool asynchronously. Defaults to calling the synchronous method.
        """
        return self.execute(**kwargs)
