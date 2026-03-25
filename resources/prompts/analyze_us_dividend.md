# Context:
Ticker:{TICKER}|Industry:{INDUSTRY}
Today:{TODAY}|PreExDivPrice:{CURRENT_PRICE}
ExDiv:{EX_DIV_DATE}|Div:{DIV_AMOUNT}|Yield:{DIV_YIELD}|Tax:15%

# Technicals:
Beta:{BETA}|RSI14:{RSI}|IndTrend60d:{INDUSTRY_TREND}|TrendVsInd60d:{TREND_VS_INDUSTRY}
AvgVol30d:{AVG_VOL}|AvgDVT7d:{AVG_DVT}|MarketCap:{MARKET_CAP}{CAP_SIZE}|Spread:{BID_ASK_SPREAD}
{PAST_DIVIDENDS_ANALYSIS}

# Task
SEARCH WEB (last 30d): "{TICKER} stock news", "{TICKER} stock earnings OR outlook", "{TICKER} short interest".

SENTIMENT: Compute SentScore based on news tone and short interest
- NewsTone: +1(Positive), 0(Neutral/Missing), -1(Negative)
- ShortScore: {SHORT_SCORE_FORMULA}

SentScore = CLAMP(0.6*NewsTone + 0.4*ShortScore, -1, 1)

CALCULATE:
- VolAdj = 1 + (Beta-1)*0.2
- EstPostExPriceMin = min(PostExPriceRange)*(1 + SentScore*0.10)*VolAdj
- EstPostExPriceMax = max(PostExPriceRange)*(1 + SentScore*0.10)*VolAdj
- AdjRecovProb = CLAMP(RecovProb + (SentScore * 0.05), 0.05, 0.95)
- EstRecovDaysMin = min(RecovDays) * (1 - SentScore*0.10)*VolAdj
- EstRecovDaysMax = max(RecovDays) * (1 - SentScore*0.10)*VolAdj
- RecovPriceMean = (min(RecovPriceRange) + max(RecovPriceRange))/2
- EstSellPrice = RecovPriceMean * (1 + SentScore*0.03)
- EstRecovPriceMin = EstSellPrice * (1 - SentScore*0.03)*VolAdj
- EstRecovPriceMax = EstSellPrice * (1 + SentScore*0.03)*VolAdj
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
- Risk (0-100): weight RSI14 overbought, low liquidity, negative trend, spread, short interest.

{
  "search_summary": "Brief web findings (news tone, short %, key events)",
  "strategy": "Dividend Capture|Post-Ex-Div Discount|N/A",
  "reasoning": "Brief reasoning/key drivers/failed criteria",
  "sent_score": 0.00,
  "recov_prob_adj": 0.00,
  "recovery_days": "'min-max' round up, or 'N/A'",
  "est_post_ex_price": "'min-max' or 'N/A'",
  "est_recovery_price": "'min-max' or 'N/A'",
  "expected_pl": 0.000,
  "confidence": 12,
  "risk": 34
}
