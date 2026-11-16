import collections.abc
import re
from decimal import ROUND_FLOOR, Decimal

from pydantic import ValidationError

from ..models import portfolio as models_portfolio
from . import portfolio_verification

MONEY_QUANTUM = Decimal("0.000001")
INFERRED_BUDGET_MIN_RATE = Decimal("0.10")
INFERRED_BUDGET_MAX_RATE = Decimal("0.15")

_CURRENCY_CODES = "AUD|CAD|CHF|CNY|EUR|GBP|HKD|INR|JPY|NZD|SGD|USD|VND"
_CURRENCY_MARKERS = rf"{_CURRENCY_CODES}|A\$|[$€£¥]"
_AMOUNT_TOKEN = (
    r"(?P<number>(?:\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.\d+)?)"
    r"(?:\s*(?P<scale>[kKmM])(?![A-Za-z]))?(?![\d,])"
)
_BUDGET_PATTERNS = (
    re.compile(
        rf"(?P<source>(?P<currency>{_CURRENCY_MARKERS})\s*{_AMOUNT_TOKEN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<source>(?:total\s+|recurring\s+|regular\s+)?"
        rf"(?:portfolio\s+)?(?:budget|investment(?:\s+amount)?|contribution|capital|"
        rf"invest|contribute|deploy|fund|allocate|put\s+in)"
        rf"\s*(?:(?:of|is|:|=)\s*)?{_AMOUNT_TOKEN})",
        re.IGNORECASE,
    ),
)
_AMOUNT_CURRENCY_PATTERN = re.compile(
    rf"(?P<source>{_AMOUNT_TOKEN}\s*(?P<currency>{_CURRENCY_CODES}))",
    re.IGNORECASE,
)
_CURRENCY_SUFFIX_PATTERN = re.compile(
    rf"(?:[kKmM](?![A-Za-z])\s*)?(?:{_CURRENCY_CODES})",
    re.IGNORECASE,
)
_BUDGET_CONTEXT_PATTERN = re.compile(
    r"\b(?:budget|invest(?:ment)?|contribut(?:e|ion|ions)?|capital|portfolio|deploy|fund|"
    r"lump[\s-]?sum|recurring|weekly|fortnightly|biweekly|monthly|quarterly|annually|yearly)\b",
    re.IGNORECASE,
)
_NEGATIVE_BUDGET_PATTERN = re.compile(
    rf"\b(?:budget|investment|contribution|invest|contribute|deploy|fund)\b"
    rf"[^.;!?\n]{{0,30}}(?:-\s*(?:(?:{_CURRENCY_MARKERS})\s*)?\d|"
    rf"(?:{_CURRENCY_MARKERS})\s*-\s*\d)",
    re.IGNORECASE,
)


def extract_budget(
    investor_theme: str,
    *,
    default_currency: str,
) -> models_portfolio.PortfolioBudget:
    """Extract one total or recurring investment budget from an investor theme.

    Args:
        investor_theme: Investor goals and constraints that may contain a positive
            amount expressed with a currency code or symbol, common budget or
            contribution wording, optional ``k``/``m`` scaling, and grouped
            digits. A recurring amount must also state a weekly, fortnightly,
            monthly, quarterly, or annual frequency.
        default_currency: Three-letter currency used when the amount omits a
            currency and to interpret ambiguous ``$`` or ``¥`` symbols. Supported
            explicit codes are ``AUD``, ``CAD``, ``CHF``, ``CNY``, ``EUR``,
            ``GBP``, ``HKD``, ``INR``, ``JPY``, ``NZD``, ``SGD``, ``USD``, and
            ``VND``.

    Returns:
        A normalized supplied budget, including the matching theme excerpt.
        One-off amounts return ``Total``; amounts with a supported recurring
        frequency return ``Recurring``. When no budget expression is present,
        returns ``NotProvided`` with no amount, currency, frequency, or source
        text; the default currency is not copied into that result.

    Raises:
        PortfolioInputError: If an amount is non-positive or unsupported, a
            recurring amount lacks a frequency, its currency cannot be resolved,
            or distinct budget expressions make the available amount ambiguous.

    Notes:
        ``€`` resolves to ``EUR``, ``£`` to ``GBP``, and ``A$`` to ``AUD``.
        ``$`` uses an ``AUD``, ``CAD``, ``HKD``, ``NZD``, ``SGD``, or ``USD``
        default when available and otherwise resolves to ``USD``. ``¥`` uses a
        ``CNY`` or ``JPY`` default when available and otherwise resolves to
        ``JPY``.
        Price limits, percentages, salaries, and similar non-budget amounts are
        ignored unless the surrounding text identifies them as investable funds.
        This function never infers an amount from current holdings.
    """
    if _NEGATIVE_BUDGET_PATTERN.search(investor_theme):
        raise portfolio_verification.PortfolioInputError("Investment budget must be a positive finite amount")
    matches: list[tuple[int, int, Decimal, str, str, bool]] = []
    for match in _iter_budget_matches(investor_theme):
        start, end = match.span("source")
        context = investor_theme[max(0, start - 60) : min(len(investor_theme), end + 60)]
        currency_marker = match.groupdict().get("currency")
        if not currency_marker and not _BUDGET_CONTEXT_PATTERN.search(context):
            continue
        if not currency_marker and re.match(
            r"\s*(?:%|percent|ETFs?|stocks?|holdings?|positions?|years?)\b",
            investor_theme[end:],
            re.IGNORECASE,
        ):
            continue
        immediate_context = investor_theme[max(0, start - 40) : min(len(investor_theme), end + 40)]
        if re.search(
            r"\b(?:salary|income|revenue|price|priced|pricing|per\s+share|"
            r"share\s+price|stocks?\s+(?:under|below|above)|market\s+cap|"
            r"dividend|fee|expense|debt)\b",
            immediate_context,
            re.IGNORECASE,
        ) and not re.search(
            r"\b(?:budget|contribut(?:e|ion|ions)?|deploy|fund|lump[\s-]?sum)\b",
            immediate_context,
            re.IGNORECASE,
        ):
            continue

        number_text = match.group("number").replace(",", "").replace(" ", "")
        amount = Decimal(number_text)
        scale = (match.group("scale") or "").lower()
        if scale == "k":
            amount *= Decimal("1000")
        elif scale == "m":
            amount *= Decimal("1000000")
        if not amount.is_finite() or amount <= 0:
            raise portfolio_verification.PortfolioInputError("Investment budget must be a positive finite amount")

        currency = _resolve_budget_currency(
            currency_marker,
            default_currency=default_currency,
        )
        source_text = _budget_source_excerpt(investor_theme, start=start, end=end)
        matches.append(
            (
                start,
                end,
                amount,
                currency,
                source_text,
                bool(currency_marker),
            )
        )

    matches.sort(key=lambda item: (-item[5], -(item[1] - item[0]), item[0]))
    non_overlapping: list[tuple[int, int, Decimal, str, str, bool]] = []
    for candidate in matches:
        if any(candidate[0] < existing[1] and candidate[1] > existing[0] for existing in non_overlapping):
            continue
        non_overlapping.append(candidate)
    non_overlapping.sort(key=lambda item: item[0])

    if not non_overlapping:
        return models_portfolio.PortfolioBudget(
            budget_type="NotProvided",
            is_inferred=False,
            amount=None,
            currency=None,
            frequency=None,
            source_text=None,
        )
    distinct_budgets = {(amount, currency) for _, _, amount, currency, _, _ in non_overlapping}
    if len(distinct_budgets) != 1:
        raise portfolio_verification.PortfolioInputError(
            "Investor theme contains multiple investment amounts; provide one total or recurring budget"
        )

    start, end, amount, currency, source_text, _ = non_overlapping[0]
    context = investor_theme[max(0, start - 60) : min(len(investor_theme), end + 60)]
    frequency_context = investor_theme[max(0, start - 45) : min(len(investor_theme), end + 45)]
    frequency = _budget_frequency(frequency_context)
    recurring_mentioned = re.search(
        r"\b(?:recurring|regular|contribut(?:e|ion|ions)|each)\b",
        context,
        re.IGNORECASE,
    )
    total_mentioned = re.search(
        r"\b(?:total|lump[\s-]?sum|one[\s-]?off)\b",
        context,
        re.IGNORECASE,
    )
    if total_mentioned and not recurring_mentioned:
        frequency = None
    if recurring_mentioned and frequency is None:
        raise portfolio_verification.PortfolioInputError(
            "Recurring investment budget must include a weekly, fortnightly, monthly, quarterly, or annual frequency"
        )

    try:
        return models_portfolio.PortfolioBudget(
            budget_type=("Recurring" if frequency is not None else "Total"),
            is_inferred=False,
            amount=float(amount),
            currency=currency,
            frequency=frequency,
            source_text=source_text,
        )
    except ValidationError as exc:
        raise portfolio_verification.PortfolioInputError(
            "Investment budget contains an unsupported amount or currency"
        ) from exc


def infer_recurring_budget(
    verified_portfolio: portfolio_verification.VerifiedPortfolio,
    *,
    rate: Decimal,
) -> models_portfolio.PortfolioBudget:
    """Create an application-inferred contribution for the next action iteration.

    Args:
        verified_portfolio: Positive, single-currency portfolio whose current
            market value supplies the inference base.
        rate: Positive finite proportion of the verified market value to make
            available as new money.

    Returns:
        An inferred recurring budget in the portfolio currency. The amount is
        rounded to six decimal places and deliberately has no invented calendar
        frequency.

    Raises:
        PortfolioInputError: If ``rate`` is not positive and finite or the
            contribution rounds to zero at six-decimal money precision.
    """
    if not rate.is_finite() or rate <= 0:
        raise portfolio_verification.PortfolioInputError(
            "Investment budget inference rate must be a positive finite value"
        )
    amount = (Decimal(str(verified_portfolio.total_market_value)) * rate).quantize(MONEY_QUANTUM)
    if amount <= 0:
        raise portfolio_verification.PortfolioInputError(
            "Verified holdings are too small to infer an investment budget"
        )
    return models_portfolio.PortfolioBudget(
        budget_type="Recurring",
        is_inferred=True,
        amount=float(amount),
        currency=verified_portfolio.currency,
        frequency=None,
        source_text=(
            f"Application-inferred next-iteration contribution at {rate:.0%} of verified current holdings market value."
        ),
    )


def allocate_whole_shares(
    budget: Decimal,
    *,
    desired_amounts: dict[str, Decimal],
    prices: dict[str, Decimal],
) -> tuple[dict[str, int], Decimal]:
    """Allocate a positive budget across desired positions using whole shares.

    Args:
        budget: Positive finite amount available for purchases.
        desired_amounts: Non-empty mapping from each ticker to its non-negative
            finite desired spend. These targets do not need to sum to
            ``budget``.
        prices: Positive finite per-share prices for exactly the same tickers as
            ``desired_amounts``.

    Returns:
        A quantity mapping containing every requested ticker and the exact
        utilized budget as a ``Decimal``. Quantities are non-negative integers,
        and utilized budget is the sum of quantity times price without exceeding
        ``budget``. Affordable extra shares are included only when they improve
        absolute alignment with the requested spends. Results do not depend on
        mapping insertion order.

    Raises:
        ValueError: If the budget, desired amounts, or prices violate the input
            constraints, their ticker sets differ, or the whole-share allocation
            implied by the requested spends would exceed the available budget.

    Notes:
        The result may leave money unallocated or assign zero shares to every
        ticker when no affordable purchase improves alignment with the requested
        spends. Extra-share ties prefer the larger desired spend, then the
        lexicographically greater ticker.
    """
    if not budget.is_finite() or budget <= 0:
        raise ValueError("Whole-share allocation budget must be a positive finite amount")
    if not desired_amounts:
        raise ValueError("Whole-share allocation requires at least one desired position")
    if set(desired_amounts) != set(prices):
        raise ValueError("Whole-share allocation desired amounts and prices must use the same tickers")
    if any(not amount.is_finite() or amount < 0 for amount in desired_amounts.values()):
        raise ValueError("Whole-share allocation desired amounts must be non-negative finite values")
    if any(not price.is_finite() or price <= 0 for price in prices.values()):
        raise ValueError("Whole-share allocation prices must be positive finite values")

    quantities = {
        ticker: int((desired_amounts[ticker] / prices[ticker]).to_integral_value(rounding=ROUND_FLOOR))
        for ticker in desired_amounts
    }
    utilized = sum(
        (Decimal(quantities[ticker]) * prices[ticker] for ticker in quantities),
        Decimal("0"),
    )
    remaining = budget - utilized

    while True:
        improvements = []
        for ticker, price in prices.items():
            if price > remaining:
                continue
            allocated = Decimal(quantities[ticker]) * price
            improvement = abs(desired_amounts[ticker] - allocated) - abs(desired_amounts[ticker] - allocated - price)
            if improvement > 0:
                improvements.append((improvement, desired_amounts[ticker], ticker))
        if not improvements:
            break
        _, _, selected_ticker = max(improvements, key=lambda item: (item[0], item[1], item[2]))
        quantities[selected_ticker] += 1
        utilized += prices[selected_ticker]
        remaining -= prices[selected_ticker]

    if utilized > budget:
        raise ValueError("Whole-share allocation exceeded the investment budget")
    return quantities, utilized


def round_money(amount: Decimal) -> float:
    """Round a finite money amount to six decimal places.

    Args:
        amount: Finite decimal money value, including zero or a negative amount.

    Returns:
        The value rounded to the nearest six decimal places using the active
        decimal rounding rule, represented as a float.

    Raises:
        ValueError: If ``amount`` is not finite.
    """
    if not amount.is_finite():
        raise ValueError("Money amount must be finite")
    return float(amount.quantize(MONEY_QUANTUM))


def _iter_budget_matches(investor_theme: str) -> collections.abc.Iterator[re.Match[str]]:
    for pattern in _BUDGET_PATTERNS:
        yield from pattern.finditer(investor_theme)

    # Discover currencies first instead of retrying a failed amount at every digit.
    for suffix in _CURRENCY_SUFFIX_PATTERN.finditer(investor_theme):
        number_end = suffix.start()
        while number_end and investor_theme[number_end - 1].isspace():
            number_end -= 1
        start = number_end
        while start and investor_theme[start - 1].isdecimal():
            start -= 1
        if start == number_end:
            continue
        if start > 1 and investor_theme[start - 1] == "." and investor_theme[start - 2].isdecimal():
            number_end = start - 1
            start = number_end
            while start and investor_theme[start - 1].isdecimal():
                start -= 1
        while (
            number_end - start == 3
            and start > 1
            and (investor_theme[start - 1] == "," or investor_theme[start - 1].isspace())
            and investor_theme[start - 2].isdecimal()
        ):
            number_end = start - 1
            start = number_end
            while start and investor_theme[start - 1].isdecimal():
                start -= 1
            if number_end - start > 3:
                # The initial group of a grouped number contains at most three digits.
                start = number_end - 3
                break
        if match := _AMOUNT_CURRENCY_PATTERN.match(investor_theme, start, suffix.end()):
            yield match


def _budget_source_excerpt(
    investor_theme: str,
    *,
    start: int,
    end: int,
) -> str:
    left = max(investor_theme.rfind(delimiter, 0, start) for delimiter in (".", ";", "!", "?", "\n"))
    right_candidates = [
        position for delimiter in (".", ";", "!", "?", "\n") if (position := investor_theme.find(delimiter, end)) >= 0
    ]
    right = min(right_candidates) if right_candidates else len(investor_theme)
    excerpt = investor_theme[left + 1 : right].strip()
    if len(excerpt) <= 500:
        return excerpt

    local_start = max(left + 1, start - 240)
    local_end = min(right, end + 240)
    return investor_theme[local_start:local_end].strip()


def _resolve_budget_currency(marker: str | None, *, default_currency: str) -> str:
    normalized_marker = marker.strip().upper() if marker else ""
    normalized_default_currency = default_currency.strip().upper()
    if not normalized_marker:
        if not normalized_default_currency:
            raise portfolio_verification.PortfolioInputError(
                "Investment budget currency could not be inferred from the selected country"
            )
        return normalized_default_currency
    if len(normalized_marker) == 3 and normalized_marker.isalpha():
        return normalized_marker
    if normalized_marker == "€":
        return "EUR"
    if normalized_marker == "£":
        return "GBP"
    if normalized_marker == "¥":
        return normalized_default_currency if normalized_default_currency in {"CNY", "JPY"} else "JPY"
    if normalized_marker == "A$":
        return "AUD"
    if normalized_marker == "$":
        return (
            normalized_default_currency
            if normalized_default_currency in {"AUD", "CAD", "HKD", "NZD", "SGD", "USD"}
            else "USD"
        )
    raise portfolio_verification.PortfolioInputError(f"Unsupported investment budget currency marker: {marker}")


def _budget_frequency(
    context: str,
) -> models_portfolio.PortfolioBudgetFrequency | None:
    frequency_patterns: tuple[
        tuple[models_portfolio.PortfolioBudgetFrequency, str],
        ...,
    ] = (
        ("Fortnightly", r"\b(?:fortnightly|biweekly|every\s+two\s+weeks?)\b"),
        ("Weekly", r"\b(?:weekly|per\s+week|each\s+week|every\s+week|a\s+week|/\s*(?:week|wk))\b"),
        ("Monthly", r"\b(?:monthly|per\s+month|each\s+month|every\s+month|a\s+month|/\s*(?:month|mo))\b"),
        (
            "Quarterly",
            r"\b(?:quarterly|per\s+quarter|each\s+quarter|every\s+quarter|a\s+quarter|/\s*(?:quarter|qtr))\b",
        ),
        (
            "Annually",
            r"\b(?:annually|annual|yearly|per\s+year|each\s+year|every\s+year|a\s+year|/\s*(?:year|yr))\b",
        ),
    )
    for frequency, pattern in frequency_patterns:
        if re.search(pattern, context, re.IGNORECASE):
            return frequency
    return None
