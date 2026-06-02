from pydantic import BaseModel


class AIVendorInfo(BaseModel):
    name: str = ""
    tier_models: dict[str, list[str]] = {}  # map {tier -> list of models}


class LLMResponse(BaseModel):
    completion: str = ""
    time_taken_ms: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_thought: int = 0
    tokens_total: int = 0
    is_error: bool = False
    error_msg: str | None = None


class BaseAIResult(BaseModel):
    llm_error: bool = False
    llm_error_msg: str | None = None
    llm_response: str | None = None


class AnalysisResult(BaseAIResult):
    analysis: str = ""
