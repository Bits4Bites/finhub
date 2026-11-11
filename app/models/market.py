from pydantic import BaseModel, ConfigDict, Field


class CompanyBriefInfo(BaseModel):
    """Brief company profile returned for a market-index constituent."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(default="", description="Security symbol of the index constituent.")
    name: str = Field(default="", description="Company or issuer name.")
    sector: str = Field(default="", description="Economic sector of the company.")
    market_cap: int = Field(default=0, description="Current market capitalization.")

    def extract_exchange_code(self) -> tuple[str, str]:
        """Extract the exchange and code from the symbol.

        Returns:
            A tuple of (exchange, code) if the symbol is in the format 'EXCHANGE:CODE', otherwise ("", code).
        """
        if ":" in self.symbol:
            exchange, code = self.symbol.split(":", 1)
            return exchange, code
        return "", self.symbol
