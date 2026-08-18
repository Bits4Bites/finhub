from pydantic import BaseModel


class AIVendorInfo(BaseModel):
    name: str = ""
    tier_models: dict[str, list[str]] = {}  # map {tier -> list of models}


class BaseAIResult(BaseModel):
    llm_error: bool = False
    llm_error_msg: str | None = None
    llm_response: str | None = None


class AnalysisResult(BaseAIResult):
    analysis: str = ""


class AnalyzePortfolioResult(BaseAIResult):
    analysis: str = ""
    rebalance_plan: str = ""
