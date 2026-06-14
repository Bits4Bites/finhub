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
    "to review an investor's existing stock portfolio and suggest concrete improvements.\n"
    "\n"
    "## Investor profile and goal\n"
    "{investor_profile}\n"
    "\n"
    "## Your instructions\n"
    "Adapt the portfolio review prompt to both the investor's profile and the specific holdings above:\n"
    "- For concentrated portfolios (any single position > 2x equal weight): flag over-concentration risk explicitly\n"
    "- For portfolios with poor diversification: instruct the premium model to assess sector/geography gaps\n"
    "- For conservative profiles holding high-volatility positions: flag profile-to-holding mismatches\n"
    "- For aggressive profiles holding mostly cash or bonds: flag under-deployment of risk capacity\n"
    "- For portfolios with available cash: instruct the premium model to suggest deployment opportunities\n"
    "- For ESG exclusions: screen current holdings and new suggestions against excluded sectors\n"
    "\n"
    "Write a prompt that tells the premium model to:\n"
    "1. Use its web search capability to fetch current prices, valuations, recent news, and analyst views\n"
    "2. Assess each existing position individually and make a clear hold / trim / exit recommendation\n"
    "3. Identify gaps in the portfolio and suggest specific new tickers to fill them\n"
    "4. Propose a revised portfolio with concrete allocations — specific tickers and percentages\n"
    "5. Justify every recommendation with data (valuation, fundamentals, portfolio fit)\n"
    "6. Account for relevant tax implications of any suggested exits\n"
    "\n"
    "## The prompt must instruct the premium model to cover:\n"
    "\n"
    "### 1. Portfolio health check\n"
    "- Overall diversification assessment (sector, geography, market cap, asset type)\n"
    "- Concentration risks (any over-weight positions)\n"
    "- Profile alignment check (do current holdings match the investor's stated risk tolerance and goal?)\n"
    "- Current income yield vs. goal (if passive income is relevant)\n"
    "- Unrealised gain/loss summary and tax lot awareness\n"
    "\n"
    "### 2. Position-by-position review\n"
    "For each ticker in portfolio, the premium model must assess:\n"
    "- Current fundamental health (recent earnings, revenue trend, valuation vs. peers)\n"
    "- Recent news and sentiment (last 30 days)\n"
    "- Analyst consensus and price target\n"
    "- Role and fit within the portfolio\n"
    "- Clear recommendation: HOLD / TRIM / EXIT with rationale and suggested new allocation %\n"
    "\n"
    "### 3. Portfolio gaps and new additions\n"
    "- Identify missing sectors, geographies, or asset types given the investor's goal and risk profile\n"
    "- Suggest 2–5 specific new tickers to add, each with:\n"
    "  - Ticker and full name\n"
    "  - Suggested allocation % and estimated number of shares\n"
    "  - Rationale (why this pick, why now, how it improves the portfolio)\n"
    "  - Key risks specific to this position\n"
    "\n"
    "### 4. Revised portfolio proposal\n"
    "- Full revised holdings list: existing positions (with adjusted allocations) + new additions\n"
    "- Side-by-side comparison: current allocation % vs. proposed allocation %\n"
    "- How to get from current to proposed (what to sell, what to buy, in what order)\n"
    "- If there is available cash: how to deploy it within the revised plan\n"
    "\n"
    "### 5. Tax and execution considerations\n"
    "- Relevant tax implications of recommended exits (capital gains, wash-sale rules, franking credit loss)\n"
    "- Suggested order of execution to minimise tax impact\n"
    "- Rebalancing frequency recommendation going forward\n"
    "\n"
    "### 6. Summary\n"
    "- Top 3 most urgent actions the investor should take\n"
    '- Overall portfolio score or assessment (e.g. "well-diversified but overweight tech,\n'
    '  misaligned with conservative risk profile")\n'
    '- Suggested next review date or trigger conditions (e.g. "review if any position moves > 15%")\n'
    "\n"
    "## Output format\n"
    "Return ONLY the ready-to-execute prompt. No preamble, no explanation, no commentary.\n"
    "The prompt must be self-contained, the premium model will receive it with no other context.\n"
    "The prompt must instruct the premium model to format the response in Markdown, "
    "and use the hyphen character (-) instead of em-dash (\u2014) throughout.\n"
    "The premium model is NOT to include any suggested follow-up questions."
)


async def ai_review_portfolio(
    *,
    portfolio: list[models.HoldingTicker],
    country: str,
    investor_theme: str = DEFAULT_INVESTOR_THEME,
) -> models_ai.AnalysisResult | None:
    """
    Build a portfolio using AI assistance.

    Args:
        portfolio (list[models.HoldingTicker]): Existing positions in the current portfolio
        country (str): Country for which to build the portfolio (used for market context)
        investor_theme (optional, string): The investor's profile, goals, and preferences

    Returns:
        models_ai.AnalysisResult | None: A models_ai.AnalysisResult object containing the analysis, or None.
    """
    if not portfolio:
        return None

    portfolio = _normalize_portfolio_allocation(portfolio)

    # Step 1: build {investor_profile} from investor_theme + existing holdings
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

    # Step 2: use AI to build the ready-to-use prompt to review the portfolio
    build_prompt = BUILD_PROMPT_TEMPLATE.format(investor_profile=investor_profile)
    build_result = await ai_helper.ai_exec_task("REVIEW_PORTFOLIO_BUILD_PROMPT", build_prompt, country)
    if build_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=build_result.error_msg)

    analysis_prompt = build_result.completion

    # Step 3: execute the prompt built from previous step
    exec_result = await ai_helper.ai_exec_task("REVIEW_PORTFOLIO_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=exec_result.error_msg)

    return models_ai.AnalysisResult(analysis=exec_result.completion)


def _normalize_portfolio_allocation(portfolio: list[models.HoldingTicker]) -> list[models.HoldingTicker]:
    """
    Each allocation is expected to be a float in range [0, 1] (hence the sum of all allocations should be 1 - e.g. 100%).
    However, in the case where the allocation is already in percentage (e.g. 23), normalize the allocation to float (e.g. 0.23).
    """

    def build_holding_ticker(ht: models.HoldingTicker) -> models.HoldingTicker:
        return models.HoldingTicker(
            ticker=ht.ticker,
            num_shares=ht.num_shares,
            avg_price=ht.avg_price,
            market_price=ht.market_price,
            target_allocation=ht.target_allocation / 100,
        )

    if sum(ht.target_allocation for ht in portfolio) > 1.25:
        return [build_holding_ticker(ht) for ht in portfolio]
    else:
        return portfolio
