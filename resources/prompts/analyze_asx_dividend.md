# Context:
Ticker:{TICKER}|Industry:{INDUSTRY}
Today:{TODAY}|Price:{CURRENT_PRICE}
ExDiv:{EX_DIV_DATE}|Div:{DIV_AMOUNT}|Yield:{DIV_YIELD}
Tax:30%|Franking:0%

# Technicals:
Beta:{BETA}|RSI14:{RSI}|Trend:{TREND}{BROADER_TREND}
AvgVol:{AVG_VOL}|MarketCap:{MARKET_CAP}|Spread:{EST_SPREAD_PCT}
{PAST_DIVIDENDS_ANALYSIS}

{VOLUME_SPIKES}

# Task

SEARCH WEB: "{TICKER} stock news", "{TICKER} market sentiment", and "{TICKER} short interest site:shortman.com.au OR site:marketindex.com.au".

SENTIMENT: Estimate a SentScore (-1.0 to 1.0) based on recent news (last 30d) and short interest.

CALCULATE:
  - EstDropMid = midpoint(drop range) * (1 - SentScore * 0.02)
  - EstSellPrice = midpoint(recovery range) * (1 + SentScore * 0.01)
  - AdjRecovChance = CLAMP(recovery chance + SentScore * 0.10, 0.10, 0.90)
  - EstRecovDays = midpoint(recovery days) * (1 - SentScore * 0.15)
  - ExpectedPL = (EstSellPrice - Price + (Div * (1 - Tax))) / Price

STRATEGY: Evaluate criteria below to recommend ONE strategy: "Dividend Capture", "Post-Ex-Div Discount", or "N/A". Assume shares sold on ex-div date retain the dividend.

# Rules

Recommend "Dividend Capture" ONLY if ALL criteria pass:
[ ] EstRecovDays ≤ 5
[ ] ExpectedPL ≥ 2%
[ ] RSI14 < 70
[ ] ShortInterest < 5% (Pass if N/A)
[ ] Spread < 1.5% (Pass if N/A)
[ ] Trend > -5%
[ ] No major negative news

If Dividend Capture fails: evaluate "Post-Ex-Div Discount" if AdjRecovChance ≥ 60% and EstRecovDays ≤ 10.
Otherwise: "N/A".

Output ONLY raw JSON. No markdown formatting, no backticks, no conversational text. Use this exact schema:
{
  "search_summary": "Brief web findings (news, sentiment, short %)",
  "strategy": "Dividend Capture|Post-Ex-Div Discount|N/A",
  "reasoning": "Brief reasoning/key drivers/failed criteria",
  "sent_score": 0.0,
  "recov_chance_adj": 0.0,
  "recovery_days": "'2-3' or 'N/A'",
  "expected_drop": "'0.90-0.92' or 'N/A'",
  "expected_recovery": "'0.95-0.97' or 'N/A'",
  "expected_pl": 0.0,
  "confidence": 50,
  "risk": 50
}
