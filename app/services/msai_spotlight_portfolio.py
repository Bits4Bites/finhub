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
    "1. Review the current portfolio and identify the top 2-4 immediate risks that could hurt the portfolio right now.\n"
    "2. Prioritize the top 2-4 immediate actions the investor should take next.\n"
    "3. Take relevant global and local market news, sector trends, and macro context into account when needed, "
    "mentioning only the most relevant themes that support the recommendations.\n"
    "4. Output only two short sections: Top immediate risks and Top immediate actions, keeping the response very concise.\n"
    "5. If there are no obvious immediate risks or actions, still conclude with a brief growth-oriented note explaining why "
    "the portfolio should continue to grow.\n"
    "6. Make the VERY FIRST line of the response a one-line summary, formatted exactly as follows:\n"
    "   - When there are immediate risks and immediate actions, the first line must be exactly: "
    "`R immediate risks and A immediate actions` - where R is the integer count of immediate risks "
    "and A is the integer count of immediate actions (for example: `3 immediate risks and 2 immediate actions`).\n"
    "   - When there are no obvious immediate risks or actions, the first line must be exactly: "
    "`No major immediate risk`.\n"
    "   - This summary line must appear on its own, before the two sections, with no extra prefix or formatting.\n"
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

    holdings_lines = []
    for pos in portfolio:
        market_value = pos.num_shares * pos.market_price
        line = f"  - {pos.ticker}: {pos.num_shares} shares, market value ${market_value:.2f}"
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
