import re

from ..models import ai as models_ai
from ..models import finhub as models
from ..services import ai_helper
from ..utils import conv

DEFAULT_INVESTOR_THEME = (
    "- Risk tolerance: moderate\n- Time horizon: 3-5 years\n- Goal: capital growth\n- Rebalance frequency: semi-annual"
)

NO_REBALANCE_NEEDED = "No rebalance needed"

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
    "- You are ONLY building a prompt. Do NOT analyze the holdings, do NOT research markets, "
    "and do NOT produce any review, recommendations, or conclusions yourself.\n"
    "- All research, analysis, and review must be performed by the premium model when it later executes the prompt you write.\n"
    "- The prompt you write must embed the investor profile and current holdings above so the premium model has full context.\n"
    "- The prompt must instruct the premium model to check for the following conditions and respond accordingly:\n"
    "  - Over-concentration (any single position > 2x equal weight): flag over-concentration risk explicitly\n"
    "  - Poor diversification: assess sector/geography gaps\n"
    "  - Conservative profile holding high-volatility positions: flag profile-to-holding mismatches\n"
    "  - Aggressive profile holding mostly cash or bonds: flag under-deployment of risk capacity\n"
    "  - Available cash: suggest deployment opportunities\n"
    "  - ESG exclusions: screen current holdings and new suggestions against excluded sectors\n"
    "\n"
    "Write a prompt that tells the premium model to:\n"
    "1. Use its web search capability to fetch current prices, valuations, recent news, and analyst views\n"
    "2. Assess each existing position individually and make a clear add / hold / trim / exit recommendation\n"
    "3. Identify gaps in the portfolio and suggest specific new tickers to fill them\n"
    "4. Propose a revised portfolio with concrete allocations - specific tickers with percentages and estimated number of shares\n"
    "5. Justify every recommendation with data (valuation, fundamentals, portfolio fit, growth profile, role in the portfolio)\n"
    "6. Account for relevant tax implications of any suggested exits\n"
    "7. Decide whether the portfolio requires a major rebalance. A major rebalance means material structural changes "
    "such as multiple trades, meaningful allocation shifts, urgent exits/replacements, or changes needed to correct "
    "serious concentration, diversification, or investor-profile misalignment. Routine monitoring, small adjustments, "
    "or normal periodic maintenance do not count as a major rebalance.\n"
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
    "- Clear recommendation: ADD / HOLD / TRIM / EXIT with rationale and suggested new allocation %\n"
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
    "- A summary table listing every position in the revised portfolio, with at minimum these columns: ticker, "
    "approximate allocation %, approximate number of shares, approximate cost, and the ticker's role in the "
    "portfolio (e.g. Yield Booster, Defensive, Growth, Core, Hedge) - start with an emoji for visual reason\n"
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
    "The prompt must instruct the premium model to make the final non-empty line exactly "
    "REBALANCE_NEEDED: YES when a major rebalance is needed, or exactly REBALANCE_NEEDED: NO otherwise. "
    "The flag must be plain text with no Markdown formatting.\n"
    "The premium model is NOT to include any suggested follow-up questions."
)

SUMMARIZE_REVIEW_PROMPT_TEMPLATE = (
    "You are a precise financial-analysis summarizer.\n"
    "\n"
    "Summarize the premium AI's portfolio review for use by another premium AI that will build a rebalance plan.\n"
    "\n"
    "## Investor profile and current holdings\n"
    "{investor_profile}\n"
    "\n"
    "## Premium portfolio review\n"
    "{portfolio_review}\n"
    "\n"
    "## Your instructions\n"
    "- Summarize only the supplied review. Do NOT research, perform new analysis, change recommendations, or build a "
    "rebalance plan.\n"
    "- Preserve every ticker, holding quantity, cost basis, market value, ADD/HOLD/TRIM/EXIT recommendation, target "
    "allocation, proposed addition, urgency, rationale, tax consideration, execution constraint, uncertainty, and "
    "caveat stated in the review.\n"
    "- Clearly distinguish facts and recommendations from assumptions or missing information.\n"
    "- Resolve no inconsistencies yourself; identify them explicitly for the premium model.\n"
    "\n"
    "## Output format\n"
    "Return only a concise, structured Markdown summary. No preamble, commentary, rebalance plan, or follow-up "
    "questions.\n"
    "Use the hyphen character (-) instead of em-dash throughout."
)

BUILD_REBALANCE_PROMPT_TEMPLATE = (
    "You are an expert financial advisor and prompt engineer.\n"
    "\n"
    "Your task is to write a detailed, ready-to-execute prompt that instructs a premium AI model to build a concrete "
    "rebalance plan from a summarized premium portfolio review.\n"
    "\n"
    "## Investor profile and current holdings\n"
    "{investor_profile}\n"
    "\n"
    "## Portfolio review summary\n"
    "{review_summary}\n"
    "\n"
    "## Your instructions\n"
    "- You are ONLY building a prompt. Do NOT rebalance the portfolio, research markets, calculate trades, or make "
    "investment decisions yourself.\n"
    "- Treat the supplied summary as the authoritative review context. Do not infer recommendations or facts that are "
    "not present in it.\n"
    "- Embed the investor profile, current holdings, and review summary in the prompt so the premium model receives all "
    "available context.\n"
    "\n"
    "Write a prompt that tells the premium model to:\n"
    "1. Revalidate material recommendations against current prices, market news, fundamentals, and the investor's "
    "profile, using web search where appropriate.\n"
    "2. Resolve any inconsistencies or stale information in the review and clearly state any assumptions required.\n"
    "3. Build a funded rebalance plan that preserves the portfolio's approximate total value unless the source context "
    "explicitly includes additional cash or withdrawals.\n"
    "4. Give exact, actionable trades for every affected position: BUY / HOLD / TRIM / SELL, current and target "
    "allocation, current and target number of shares, share delta, and approximate trade value.\n"
    "5. Include every retained, removed, and newly added position in a final target-portfolio table with ticker, role, "
    "target allocation %, target shares, and target value.\n"
    "6. Provide an ordered execution plan, including timing, dependencies between sells and buys, transaction costs, "
    "tax implications, and practical rounding of share quantities.\n"
    "7. Prioritize the most urgent changes and explain how the final portfolio improves diversification and alignment "
    "with the investor's goals and risk tolerance.\n"
    "8. Never invent available cash, tax lots, or investor preferences. State conservative assumptions when required "
    "data is unavailable.\n"
    "\n"
    "## Output format\n"
    "Return ONLY the ready-to-execute prompt. No preamble, explanation, commentary, or follow-up questions.\n"
    "The prompt must be self-contained and instruct the premium model to format its response in Markdown and use the "
    "hyphen character (-) instead of em-dash throughout."
)


def _extract_rebalance_decision(portfolio_review: str) -> tuple[bool | None, str]:
    lines = [line.strip() for line in portfolio_review.splitlines() if line.strip()]
    if not lines:
        return None, portfolio_review

    flag_match = re.fullmatch(
        r"(?:[`*_]{1,2})?REBALANCE_NEEDED\s*:\s*(YES|NO)(?:[`*_]{1,2})?[.!]?",
        lines[-1],
        flags=re.IGNORECASE,
    )
    if not flag_match:
        return None, portfolio_review

    review_without_flag = portfolio_review.rsplit(lines[-1], 1)[0].rstrip()
    return flag_match.group(1).upper() == "YES", review_without_flag


async def ai_review_portfolio(
    *,
    portfolio: list[models.HoldingTicker],
    country: str,
    investor_theme: str = DEFAULT_INVESTOR_THEME,
    rebalance_plan: bool = False,
) -> models_ai.AnalyzePortfolioResult | None:
    """
    Review a portfolio and optionally build a rebalance plan using AI assistance.

    Args:
        portfolio (list[models.HoldingTicker]): Existing positions in the current portfolio
        country (str): Country for which to build the portfolio (used for market context)
        investor_theme (optional, string): The investor's profile, goals, and preferences
        rebalance_plan (optional, bool): If True, generate a rebalance plan after reviewing the portfolio.

    Returns:
        models_ai.AnalyzePortfolioResult | None: A models_ai.AnalyzePortfolioResult object containing the analysis, or None.
    """
    if not portfolio:
        return None

    # Step 1: build {investor_profile} from investor_theme + existing holdings
    currency = conv.country_to_currency_symbol(country) or "$"
    holdings_lines = []
    for pos in portfolio:
        market_value = pos.num_shares * pos.market_price
        line = f"- {pos.ticker}: {pos.num_shares} shares, avg price {currency}{pos.avg_price:.2f}, market value {currency}{market_value:.2f}"
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
        return models_ai.AnalyzePortfolioResult(llm_error=True, llm_error_msg=build_result.error_msg)

    analysis_prompt = build_result.completion

    # Step 3: execute the prompt built from previous step
    exec_result = await ai_helper.ai_exec_task("REVIEW_PORTFOLIO_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        return models_ai.AnalyzePortfolioResult(llm_error=True, llm_error_msg=exec_result.error_msg)

    rebalance_needed, portfolio_review = _extract_rebalance_decision(exec_result.completion)
    if not rebalance_plan:
        return models_ai.AnalyzePortfolioResult(analysis=portfolio_review)

    if rebalance_needed is None:
        return models_ai.AnalyzePortfolioResult(
            analysis=portfolio_review,
            llm_error=True,
            llm_error_msg="Premium portfolio review did not include a valid final REBALANCE_NEEDED flag.",
        )
    if not rebalance_needed:
        return models_ai.AnalyzePortfolioResult(
            analysis=portfolio_review,
            rebalance_plan=NO_REBALANCE_NEEDED,
        )

    # Step 4: use the low-cost model to summarize the premium review without adding new analysis
    summarize_prompt = SUMMARIZE_REVIEW_PROMPT_TEMPLATE.format(
        investor_profile=investor_profile,
        portfolio_review=portfolio_review,
    )
    summary_result = await ai_helper.ai_exec_task("REVIEW_PORTFOLIO_SUMMARIZE", summarize_prompt, country)
    if summary_result.is_error:
        return models_ai.AnalyzePortfolioResult(
            analysis=portfolio_review,
            llm_error=True,
            llm_error_msg=summary_result.error_msg,
        )

    # Step 5: use the low-cost model to build a prompt for the premium rebalance task
    rebalance_build_prompt = BUILD_REBALANCE_PROMPT_TEMPLATE.format(
        investor_profile=investor_profile,
        review_summary=summary_result.completion,
    )
    rebalance_build_result = await ai_helper.ai_exec_task(
        "REVIEW_PORTFOLIO_REBALANCE_BUILD_PROMPT",
        rebalance_build_prompt,
        country,
    )
    if rebalance_build_result.is_error:
        return models_ai.AnalyzePortfolioResult(
            analysis=portfolio_review,
            llm_error=True,
            llm_error_msg=rebalance_build_result.error_msg,
        )

    # Step 6: use the premium model to execute the self-contained rebalance prompt
    rebalance_result = await ai_helper.ai_exec_task(
        "REVIEW_PORTFOLIO_REBALANCE_EXEC",
        rebalance_build_result.completion,
        country,
    )
    if rebalance_result.is_error:
        return models_ai.AnalyzePortfolioResult(
            analysis=portfolio_review,
            llm_error=True,
            llm_error_msg=rebalance_result.error_msg,
        )

    return models_ai.AnalyzePortfolioResult(
        analysis=portfolio_review,
        rebalance_plan=rebalance_result.completion,
    )
