from pydantic import BaseModel, Field


class AIVendorInfo(BaseModel):
    """Enabled model tiers exposed for an AI vendor."""

    name: str = Field(default="", description="Display name of the AI vendor.")
    tier_models: dict[str, list[str]] = Field(
        default={},
        description="Enabled model identifiers grouped by service tier.",
    )
