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
    "- You are ONLY building a prompt. Do NOT analyze the portfolio, do NOT research markets, "
    "and do NOT produce any risks, actions, or recommendations yourself.\n"
    "- All research, review, and analysis must be performed by the premium model when it later executes the prompt you write.\n"
    "- The prompt you write must embed the investor profile and current holdings above so the premium model has full context.\n"
    "\n"
    "Write a ready-to-execute prompt that instructs the premium model to:\n"
    "1. Review the current portfolio and identify the top 2-4 risks that could hurt the portfolio.\n"
    "2. Rank each identified risk into exactly one of these severity levels:\n"
    "   - `Critical` - must act immediately, or within 1 week.\n"
    "   - `High` - act within 1 to 2 weeks.\n"
    "   - `Medium` - should closely monitor the market and act accordingly.\n"
    "   - `Low` - no action needed for now, just monitor.\n"
    "3. Prioritize the `Critical` and `High` risks: for each of them, give a clear, specific and actionable action, "
    "naming specific tickers and concrete numbers - for example: `Add bank stocks such as A, B, C "
    "(allocation %, value, number of shares)` or `Replace X with Y entirely`. Do NOT give generic or vague "
    "actions such as `reduce high-risk stocks and add high-liquidity ones`.\n"
    "4. Take relevant global and local market news, sector trends, and macro context into account when needed, "
    "mentioning only the most relevant themes that support the recommendations.\n"
    "5. Keep the response very concise, listing each risk with its severity level and, for `Critical` and `High` "
    "risks, the specific action to take.\n"
    "6. If there are no obvious risks or actions, still include a brief growth-oriented note explaining why "
    "the portfolio should continue to grow.\n"
    "7. Make the VERY LAST line of the response a one-line summary, formatted exactly as follows:\n"
    "   - The summary line must start with `SUMMARY:`.\n"
    "   - When there are any `Critical` or `High` risks, the line must be exactly: "
    "`SUMMARY: X Critical/High risks with actions` - where X is the integer count of `Critical` and `High` "
    "risks combined (for example: `SUMMARY: 3 Critical/High risks with actions`).\n"
    "   - When there are no `Critical` or `High` risks, the line must be exactly: "
    "`SUMMARY: No major immediate risk`.\n"
    "   - This summary line must appear on its own, at the very end of the response, after all other content, "
    "with no extra formatting.\n"
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

    # Step 2: use AI to build the ready-to-use prompt to spotlight the portfolio
    build_prompt = BUILD_PROMPT_TEMPLATE.format(investor_profile=investor_profile)
    build_result = await ai_helper.ai_exec_task("SPOTLIGHT_PORTFOLIO_BUILD_PROMPT", build_prompt, country)
    if build_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=build_result.error_msg)

    analysis_prompt = build_result.completion

    # Step 3: execute the prompt built from previous step
    exec_result = await ai_helper.ai_exec_task("SPOTLIGHT_PORTFOLIO_EXEC", analysis_prompt, country)
    if exec_result.is_error:
        return models_ai.AnalysisResult(llm_error=True, llm_error_msg=exec_result.error_msg)

    return models_ai.AnalysisResult(analysis=exec_result.completion)
