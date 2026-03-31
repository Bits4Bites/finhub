# Context:
Ticker:{TICKER}|{INDUSTRY}
Today:{TODAY}|PreExDivPrice:{CURRENT_PRICE}
ExDiv:{EX_DIV_DATE}|Div:{DIV_AMOUNT}|Yield:{DIV_YIELD}|Tax:15%

# Technicals:
Beta:{BETA}|RSI14:{RSI}|IndTrend60d:{INDUSTRY_TREND}|TrendVsInd60d:{TREND_VS_INDUSTRY}
AvgVol30d:{AVG_VOL}|AvgDVT7d:{AVG_DVT}|MarketCap:{MARKET_CAP}{CAP_SIZE}|Spread:{BID_ASK_SPREAD}
{PAST_DIVIDENDS_ANALYSIS}

# Task
SEARCH WEB (last 30d): earnings, outlook, short interest, dividend changes

SENTIMENT: Score components:
- News: +0.5 / 0 / -0.5
- Earnings: +0.5 / 0 / -0.5
- ShortScore: {SHORT_SCORE_FORMULA}
- Dividend: cut:-0.5 | stable:0 | raise:+0.2

SentScore = CLAMP(sum, -1, 1)

CALCULATE:
- VolAdj = 1 + (Beta-1)*0.2
- AdjRecovProb = CLAMP(RecovProb + (SentScore*0.05), 0.05, 0.95)
- EstRecovDays = [{RECOVERY_DAYS_MIN},{RECOVERY_DAYS_MAX}]*(1 - SentScore*0.10)*VolAdj
- EstDropPrice = [{DROP_PRICE_MIN},{DROP_PRICE_MAX}]*(1 + SentScore*0.10)*VolAdj
- EstSellPrice = ({RECOVERY_PRICE_MIN} + {RECOVERY_PRICE_MAX})/2*(1 + SentScore*0.03)
- EstRecovPriceMin = EstSellPrice*(1 - SentScore*0.03)*VolAdj
- EstRecovPriceMax = EstSellPrice*(1 + SentScore*0.03)*VolAdj
- NetBuy = PreExDivPrice*(1 + Spread/2)
- NetSell = EstSellPrice*(1 - Spread/2)
- ExpectedPL = (NetSell - NetBuy + (Div * (1 - Tax))) / NetBuy
- Liquidity = AvgDVT7d/MarketCap

# Rules
Recommend "Dividend Capture" ONLY if ALL pass:
{DIV_CAPTURE_RULES}
[ ] No major negative news

Else if AdjRecovProb ≥0.60 AND EstRecovDays(max) ≤10 → "Post-Ex-Div Discount"
Else → "N/A"

Output ONLY raw JSON. No markdown, no backticks, no prose.
- Confidence (0-100): weight AdjRecovProb, sentiment clarity, data completeness.
- Risk (0-100): weight RSI14 overbought, low liquidity, negative trend/news, spread, short interest.

{
  "search_summary": "Brief web findings (news tone, short %, key events)",
  "strategy": "Dividend Capture|Post-Ex-Div Discount|N/A",
  "reasoning": "Brief reasoning/key drivers/failed criteria",
  "sent_score": 0.00,
  "recov_prob_adj": 0.00,
  "recovery_days": "'min-max' round up, or 'N/A'",
  "est_drop_price": "'min-max' or 'N/A'",
  "est_recovery_price": "'min-max' or 'N/A'",
  "expected_pl": 0.000,
  "confidence": 12,
  "risk": 34,
  "risk_factors": ["Overbought", "Liquidity", "Shorts", "Trend/News", "Spread"]
}
