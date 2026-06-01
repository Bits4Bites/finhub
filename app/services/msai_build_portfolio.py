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
    "Your task is to write a detailed, ready-to-execute prompt that instructs a premium AI model\n"
    "to help an investor build a stock portfolio from scratch.\n"
    "\n"
    "## Investor profile and goal\n"
    "{investor_profile}\n"
    "\n"
    "## Your instructions\n"
    "Adapt the portfolio-building prompt to the investor's specific profile:\n"
    "- For conservative profiles: weight toward dividend stocks, blue chips, bonds, or bond ETFs\n"
    "- For aggressive profiles: allow higher allocation to growth stocks, small-caps, thematic ETFs\n"
    "- For passive income goals: emphasize REITs, dividend ETFs, high-yield equities\n"
    "- For short horizons: reduce volatility exposure, increase cash or short-duration assets\n"
    "- For ESG exclusions: explicitly instruct the premium model to screen out excluded sectors\n"
    "\n"
    "Write a prompt that tells the premium model to:\n"
    "1. Use its web search capability to gather current market data, valuations, and recent performance\n"
    "2. Recommend a concrete, actionable portfolio - specific tickers, not vague asset classes\n"
    "3. Justify every pick with data (valuation, growth profile, role in the portfolio)\n"
    "4. Define the allocation clearly (percentage per position)\n"
    "5. Flag key risks for the overall portfolio and for individual positions\n"
    "6. Keep the portfolio manageable (typically 8–15 positions unless the investor profile suggests otherwise)\n"
    "\n"
    "## The prompt must instruct the premium model to cover:\n"
    "- Proposed asset allocation strategy (equities / ETFs / REITs / bonds / cash %)\n"
    "- Individual stock/ETF picks with:\n"
    "  - Ticker and full name\n"
    "  - Allocation % and estimated number of shares\n"
    "  - Rationale (why this pick, why this weighting)\n"
    "  - Key risks specific to this position\n"
    "- Portfolio-level analysis:\n"
    "  - Diversification assessment (sector, geography, market cap spread)\n"
    "  - Expected income yield (if relevant to goal)\n"
    "  - Overall risk profile vs. stated tolerance\n"
    "- Relevant tax considerations (e.g. franking credits, withholding tax, capital gains treatment)\n"
    "- Suggested rebalancing frequency\n"
    "- A clear next-steps section for the investor to act on the recommendations\n"
    "{existing_holdings_instruction}"
    "\n"
    "## Output format\n"
    "Return ONLY the ready-to-execute prompt. No preamble, no explanation, no commentary.\n"
    "The prompt must be self-contained, the premium model will receive it with no other context.\n"
    "The prompt must instruct the premium model to format the response in Markdown, "
    "and use the hyphen character (-) instead of em-dash (\u2014) throughout.\n"
    "The premium model is NOT to include any suggested follow-up questions."
)


async def ai_build_portfolio(
    *,
    existing_positions: list[models.HoldingTicker] | None = None,
    country: str,
    investor_theme: str = DEFAULT_INVESTOR_THEME,
) -> models_ai.AnalysisResult | None:
    """
    Build a portfolio using AI assistance.

    Args:
        existing_positions (optional, list[models.HoldingTicker] | None): Existing positions to consider in the analysis
        country (str): Country for which to build the portfolio (used for market context)
        investor_theme (optional, string): The investor's profile, goals, and preferences

    Returns:
        models_ai.AnalysisResult | None: A models_ai.AnalysisResult object containing the analysis, or None.
    """
    # Step 1: build {investor_profile} from investor_theme + existing holdings
    existing_holdings = ""
    existing_holdings_instruction = ""
    if existing_positions:
        holdings_lines = []
        for pos in existing_positions:
            market_value = pos.num_shares * pos.market_price
            holdings_lines.append(f"  - {pos.ticker}: {pos.num_shares} shares, market value ${market_value:.2f}")
        existing_holdings = "\n\n### Current holdings\n" + "\n".join(holdings_lines)
        existing_holdings_instruction = "- How the new recommendations complement or adjust the existing holdings\n"

    country = conv.country_to_iso2(country)
    investor_profile = f"- Target market/country: {country}\n" + investor_theme + existing_holdings

    # Step 2: use AI to build the ready-to-use prompt to build the portfolio
    build_prompt = BUILD_PROMPT_TEMPLATE.format(
        investor_profile=investor_profile,
        existing_holdings_instruction=existing_holdings_instruction,
    )
    build_result = await ai_helper.ai_exec_task("BUILD_PORTFOLIO_BUILD_PROMPT", build_prompt, country)
    if build_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=build_result.error_msg)

    analysis_prompt = build_result.completion

    # Step 3: execute the prompt built from previous step
    exec_result = await ai_helper.ai_exec_task("BUILD_PORTFOLIO_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=exec_result.error_msg)

    return models_ai.AnalysisResult(analysis=exec_result.completion)
