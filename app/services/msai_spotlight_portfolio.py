from ..models import ai as models_ai
from ..models import finhub as models
from ..services import ai_helper
from ..utils import conv

DEFAULT_INVESTOR_THEME = (
    "- Risk tolerance: moderate\n- Time horizon: 3-5 years\n- Goal: capital growth\n- Rebalance frequency: semi-annual"
)

BUILD_PROMPT_TEMPLATE = (
    "You are an expert financial advisor and prompt engineer.\n"
    "\n"
    "Your task is to write a concise, action-oriented prompt that instructs a premium AI model\n"
    "to spotlight the most urgent portfolio risks and actions for an investor's current holdings.\n"
    "\n"
    "## Investor profile and goal\n"
    "{investor_profile}\n"
    "\n"
    "## Your instructions\n"
    "- Review the current portfolio and identify the top 2-4 immediate risks that could hurt the portfolio right now.\n"
    "- Prioritize the top 2-4 immediate actions the investor should take next.\n"
    "- If there are no obvious immediate risks or actions, explicitly say the portfolio should continue to grow and explain why.\n"
    "- Take relevant global and local market news, sector trends, and macro context into account when needed.\n"
    "- Keep the output very concise and focused only on Top immediate risks and Top immediate actions.\n"
    "\n"
    "Write a ready-to-execute prompt that tells the premium model to:\n"
    "1. Output only two short sections: Top immediate risks and Top immediate actions.\n"
    "2. Keep the response very concise.\n"
    "3. If no urgent issues are found, still conclude with a brief growth-oriented note.\n"
    "4. Mention only the most relevant local/global news or macro themes that support the recommendations.\n"
    "\n"
    "## Output format\n"
    "Return ONLY the ready-to-execute prompt. No preamble, no explanation, no commentary."
    "The prompt must be self-contained, the premium model will receive it with no other context.\n"
    "The prompt must instruct the premium model to format the response in Markdown, "
    "and use the hyphen character (-) instead of em-dash (\u2014) throughout.\n"
    "The premium model is NOT to include any suggested follow-up questions."
)


async def ai_spotlight_portfolio(
    *,
    portfolio: list[models.HoldingTicker],
    country: str,
    investor_theme: str = DEFAULT_INVESTOR_THEME,
) -> models_ai.AnalysisResult | None:
    """
    Spotlight immediate portfolio risks and actions using AI assistance.

    Args:
        portfolio (list[models.HoldingTicker]): Existing positions in the current portfolio.
        country (str): Country for which to review the portfolio.
        investor_theme (optional, string): The investor profile and goal.

    Returns:
        models_ai.AnalysisResult | None: AI analysis result containing the recommended spotlight review.
    """
    if not portfolio:
        return None

    portfolio = _normalize_portfolio_allocation(portfolio)

    holdings_lines = []
    for pos in portfolio:
        market_value = pos.num_shares * pos.market_price
        line = (
            f"  - {pos.ticker}: {pos.num_shares} shares, market value ${market_value:.2f}, "
            f"target allocation {pos.target_allocation:.1%}"
        )
        if pos.tags:
            line += f" ({pos.tags})"
        holdings_lines.append(line)

    existing_holdings = "\n\n### Current holdings\n" + "\n".join(holdings_lines)
    country = conv.country_to_iso2(country)
    investor_profile = f"- Target market/country: {country}\n" + investor_theme + existing_holdings

    build_prompt = BUILD_PROMPT_TEMPLATE.format(investor_profile=investor_profile)
    build_result = await ai_helper.ai_exec_task("SPOTLIGHT_PORTFOLIO_BUILD_PROMPT", build_prompt, country)
    if build_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=build_result.error_msg)

    analysis_prompt = build_result.completion
    exec_result = await ai_helper.ai_exec_task("SPOTLIGHT_PORTFOLIO_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=exec_result.error_msg)

    return models_ai.AnalysisResult(analysis=exec_result.completion)


def _normalize_portfolio_allocation(portfolio: list[models.HoldingTicker]) -> list[models.HoldingTicker]:
    """
    Normalize allocations to fractional values when percentages are provided.
    """

    def build_holding_ticker(ht: models.HoldingTicker) -> models.HoldingTicker:
        return models.HoldingTicker(
            ticker=ht.ticker,
            num_shares=ht.num_shares,
            avg_price=ht.avg_price,
            market_price=ht.market_price,
            target_allocation=ht.target_allocation / 100,
            tags=ht.tags,
        )

    if sum(ht.target_allocation for ht in portfolio) > 1.25:
        return [build_holding_ticker(ht) for ht in portfolio]
    return portfolio
