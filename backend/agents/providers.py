import json
from typing import Type, TypeVar, Optional, Any
from pydantic import BaseModel
from api.config import settings
from loguru import logger

# Declare generic type for Pydantic models
T = TypeVar('T', bound=BaseModel)

import contextvars
is_mocked_execution = contextvars.ContextVar("is_mocked_execution", default=False)

class BaseLLMProvider:
    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        raise NotImplementedError

    def generate_structured_output(self, prompt: str, schema: Type[T], system_instruction: Optional[str] = None) -> T:
        raise NotImplementedError






class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        import google.generativeai as genai
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in settings.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.GEMINI_MODEL
        self._mock = MockProvider()

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        import google.generativeai as genai
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.2}
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            if any(term in err_str for term in ["API key not valid", "API_KEY_INVALID", "RESOURCE_EXHAUSTED", "429", "quota", "Quota"]):
                logger.warning(f"Gemini API issue ({err_str[:80]}). Falling back to MockProvider for demonstration.")
                is_mocked_execution.set(True)
                return self._mock.generate_text(prompt, system_instruction)
            logger.error(f"Gemini text generation error: {e}")
            raise

    def generate_structured_output(self, prompt: str, schema: Type[T], system_instruction: Optional[str] = None) -> T:
        import google.generativeai as genai
        
        def pydantic_to_gemini_schema(model: Type[BaseModel]) -> dict:
            js = model.model_json_schema()
            def clean(d):
                if not isinstance(d, dict):
                    return d
                d.pop("default", None)
                d.pop("title", None)
                for k, v in list(d.items()):
                    if isinstance(v, dict):
                        d[k] = clean(v)
                    elif isinstance(v, list):
                        d[k] = [clean(item) if isinstance(item, dict) else item for item in v]
                return d
            return clean(js)

        try:
            # We enforce JSON output format and supply the JSON schema
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )
            # Fetch raw JSON schema from Pydantic model and strip 'default' fields
            gemini_schema = pydantic_to_gemini_schema(schema)
            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json",
                    "response_schema": gemini_schema
                }
            )
            raw_text = response.text
            # Parse text into Pydantic schema
            return schema.model_validate_json(raw_text)
        except Exception as e:
            err_str = str(e)
            if any(term in err_str for term in ["API key not valid", "API_KEY_INVALID", "RESOURCE_EXHAUSTED", "429", "quota", "Quota"]):
                logger.warning(f"Gemini API issue ({err_str[:80]}). Falling back to MockProvider for demonstration.")
                is_mocked_execution.set(True)
                return self._mock.generate_structured_output(prompt, schema, system_instruction)
            logger.error(f"Gemini structured output generation error: {e}")
            raise


class MockProvider(BaseLLMProvider):
    """
    Fallback provider for testing when no keys are configured.
    Returns mocked text and valid schema objects.
    """
    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        is_mocked_execution.set(True)
        logger.warning("Using Mock LLM Provider for text generation.")
        return f"Mocked response for prompt: {prompt[:50]}..."

    def generate_structured_output(self, prompt: str, schema: Type[T], system_instruction: Optional[str] = None) -> T:
        is_mocked_execution.set(True)
        logger.warning(f"Using Mock LLM Provider for structured output of type {schema.__name__}.")
        # Construct dynamic mock object satisfying schema fields
        mock_data = {}
        for field_name, field_info in schema.model_fields.items():
            field_type = field_info.annotation
            # Assign standard defaults based on types
            if field_type is str:
                mock_data[field_name] = f"Mocked {field_name}"
            elif field_type is int:
                mock_data[field_name] = 1
            elif field_type is float:
                mock_data[field_name] = 1.0
            elif field_type is bool:
                mock_data[field_name] = True
            elif hasattr(field_type, '__origin__') and field_type.__origin__ is list:
                mock_data[field_name] = []
            elif hasattr(field_type, '__origin__') and field_type.__origin__ is dict:
                mock_data[field_name] = {}
            else:
                mock_data[field_name] = None
        
        # Specific overrides for response formats
        if schema.__name__ == 'PlannerOutput':
            mock_data.update({
                "plan": ["Retrieve context from documents", "Execute Python tool to compute response"],
                "needs_rag": True,
                "reasoning": "Mock planner decision."
            })
        elif schema.__name__ == 'ValidationOutput':
            mock_data.update({
                "validation_passed": True,
                "feedback": "Passed verification checks.",
                "confidence_score": 0.95,
                "hallucination_detected": False
            })
        elif schema.__name__ == 'ResponseOutput':
            mock_data.update({
                "structured_answer": {"result": "Mocked successful output execution"},
                "explanation": "Calculated via mock logic flow.",
                "citations": ["Uploaded doc 1", "Reference manual"],
                "recommendations": ["Review validation scores", "Enable active provider keys"]
            })
            
        return schema.model_validate(mock_data)


def get_llm_provider() -> BaseLLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "gemini":
        if settings.GEMINI_API_KEY:
            return GeminiProvider()
        else:
            logger.warning("GEMINI_API_KEY not found. Falling back to MockProvider.")
            return MockProvider()
    else:
        logger.warning(f"Unknown or mock provider '{provider}'. Using MockProvider.")
        return MockProvider()
