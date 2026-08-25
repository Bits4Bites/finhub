from pydantic import BaseModel, ConfigDict, Field


class CompanyBriefInfo(BaseModel):
    """Brief company profile returned for a market-index constituent."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(default="", description="Security symbol of the index constituent.")
    name: str = Field(default="", description="Company or issuer name.")
    sector: str = Field(default="", description="Economic sector of the company.")
    market_cap: int = Field(default=0, description="Current market capitalization.")
