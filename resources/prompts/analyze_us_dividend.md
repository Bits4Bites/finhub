# Context:
Ticker:{TICKER}|Industry:{INDUSTRY}
MarketCap:{MARKET_CAP}{CAP_SIZE}
Today:{TODAY}|PreExDivPrice:{CURRENT_PRICE}
ExDivDate:{EX_DIV_DATE}|Div:{DIV_AMOUNT}|GrossYield:{DIV_YIELD}|WHT:15%

# Technicals:
Beta:{BETA}|RSI14:{RSI}|IndTrend60d:{INDUSTRY_TREND}|TrendVsInd60d:{TREND_VS_INDUSTRY}
AvgVol30d:{AVG_VOL}|AvgDVT7d:{AVG_DVT}|BidAskSpread:{BID_ASK_SPREAD}
{PAST_DIVIDENDS_ANALYSIS}

# Step 1 - Web search
Search {TICKER} news (last 30d). Priority: SEC/EDGAR filings > WSJ/Bloomberg/Reuters/Seeking Alpha > FINRA short data.
Find: earnings/guidance, dividend changes, analyst changes, negative news, short interest %.
If sparse/conflicting → conservative score; if missing field → mark "?" in reasoning, -10 confidence each.

# Step 2 - Sentiment scoring
News:      positive→+0.5 | neutral→0 | negative→-0.5
Earnings:  beat/raised→+0.5 | in-line→0 | miss/cut→-0.5
ShortScore:{SHORT_SCORE_FORMULA}
Dividend:  cut→-0.5 | stable→0 | raise→+0.2
SentScore = CLAMP(sum, -1, 1)

# Step 3 - Calculations
VolAdj        = 1 + (Beta-1)×0.2
AdjRecovProb  = CLAMP(RecovProb + SentScore×0.05, 0.05, 0.95)
Liquidity     = AvgDVT7d / MarketCap
EstRecovDays  = [{RECOVERY_DAYS_MIN}, {RECOVERY_DAYS_MAX}] × (1-SentScore×0.10) × VolAdj
EstDropPrice  = [{DROP_PRICE_MIN}, {DROP_PRICE_MAX}] × (1+SentScore×0.10) × VolAdj
EstSellPrice  = ({RECOVERY_PRICE_MIN}+{RECOVERY_PRICE_MAX})/2 × (1+SentScore×0.03)
EstRecovPrice = [EstSellPrice×(1-SentScore×0.03), EstSellPrice×(1+SentScore×0.03)] × VolAdj
NetBuy        = {CURRENT_PRICE} × (1+BidAskSpread/2)
NetSell       = EstSellPrice × (1-BidAskSpread/2)
EffDiv        = Div × (1-WHT)
ExpectedPL    = (NetSell - NetBuy + EffDiv) / NetBuy

# Step 4 - Strategy recommendation
Recommend "Dividend Capture" ONLY if ALL criteria pass:
{DIV_CAPTURE_RULES}
[ ] No major negative news in the last 30 days

Else if AdjRecovProb ≥ 0.60 AND EstRecovDays_max ≤ 10 → "Post-Ex-Div Discount"
Else → "N/A"

# Output
Raw JSON only. No markdown, no backticks, no prose outside the JSON object.
Use null (not "N/A") for any field that cannot be calculated.

{
  "search_summary": "2–3 sentences covering news tone, short interest %, key events, and any data gaps",
  "strategy": "Dividend Capture|Post-Ex-Div Discount|N/A",
  "reasoning": "Key drivers and any failed criteria (max 3 sentences)",
  "sent_score": 0.00,
  "recov_prob_adj": 0.00,
  "eff_div": 0.0000,
  "recovery_days": "'min-max' round up, or 'N/A'",
  "est_drop_price": "'min-max' or 'N/A'",
  "est_recovery_price": "'min-max' or 'N/A'",
  "expected_pl": 0.000,
  "confidence": 0,
  "risk": 0,
  "risk_factors": ["list only factors that apply"]
}

Confidence (0–100): weight AdjRecovProb, sentiment clarity, data completeness (-10 per missing field).
Risk (0–100): weight RSI14 overbought (>70), low liquidity, high short interest, negative trend/news, wide spread.
