from ..models import types

ANALYZE_ASX_DIVIDEND = "ASX_DIVIDEND_ANALYSIS"
ANALYZE_US_DIVIDEND = "US_DIVIDEND_ANALYSIS"
ANALYZE_VN_DIVIDEND = "VN_DIVIDEND_ANALYSIS"
ANALYZE_PORTFOLIO_ALLOCATION = "ALLOCATION_PORTFOLIO_ANALYSIS"
ANALYZE_PORTFOLIO_SWING = "SWING_PORTFOLIO_ANALYSIS"
ANALYZE_PORTFOLIO_HYBRID = "HYBRID_PORTFOLIO_ANALYSIS"
BUILD_PORTFOLIO_ALLOCATION = "ALLOCATION_PORTFOLIO_BUILDING"
BUILD_PORTFOLIO_SWING = "SWING_PORTFOLIO_BUILDING"
BUILD_PORTFOLIO_HYBRID = "HYBRID_PORTFOLIO_BUILDING"


prompts: dict[str, str] = {}


# ----------------------------------------------------------------------#


dividend_capture_shortscore_rules = {
    "ASX": {
        types.LARGE_CAP: "<1.5%:0 | 1.5–3%:-0.12 | 3–6%: -0.24 | >6%: -0.36",
        types.MID_CAP: "<2%:0 | 2–4%:-0.14 | 4–8%: -0.30 | >8%: -0.42",
        types.SMALL_CAP: "<3%:0 | 3–6%:-0.18 | 6–10%: -0.36 | >10%: -0.48",
        types.MICRO_CAP: "<4%:0 | 4-8%:-0.24 | 8–15%: -0.42 | >15%: -0.60",
        types.NANO_CAP: "<5%:0 | 5-10%:-0.30 | 10-20%: -0.48 | >20%: -0.72",
    },
    "NASDAQ": {
        types.LARGE_CAP: "<1.5%:0 | 1.5–3%:-0.08 | 3–6%: -0.16 | >6%: -0.24",
        types.MID_CAP: "<2%:0 | 2–4%:-0.10 | 4–8%: -0.20 | >8%: -0.28",
        types.SMALL_CAP: "<3%:0 | 3–6%:-0.12 | 6–10%: -0.24 | >10%: -0.32",
        types.MICRO_CAP: "<4%:0 | 4-8%:-0.16 | 8–15%: -0.28 | >15%: -0.40",
        types.NANO_CAP: "<5%:0 | 5-10%:-0.20 | 10-20%: -0.32 | >20%: -0.48",
    },
    "NYSE": {
        types.LARGE_CAP: "<1.5%:0 | 1.5–3%:-0.10 | 3–6%: -0.20 | >6%: -0.30",
        types.MID_CAP: "<2%:0 | 2–4%:-0.12 | 4–8%: -0.25 | >8%: -0.35",
        types.SMALL_CAP: "<3%:0 | 3–6%:-0.15 | 6–10%: -0.30 | >10%: -0.40",
        types.MICRO_CAP: "<4%:0 | 4-8%:-0.20 | 8–15%: -0.35 | >15%: -0.50",
        types.NANO_CAP: "<5%:0 | 5-10%:-0.25 | 10-20%: -0.40 | >20%: -0.60",
    },
}

dividend_capture_criteria = {
    "ASX": {
        types.LARGE_CAP: [  # >= 10B
            "AdjRecovProb ≥65%",
            "ExpectedPL ≥1.5%",
            "Yield ≥2.0%",
            "EstRecovDays(max) ≤5",
            "Spread <0.003",
            "RSI14 <70",
            "Short Interest <5.0%",
            "IndTrend60d >-2.0%",
            "TrendVsInd60d >-1.0%",
            "AvgDVT7d >20M",
            "Liquidity >0.0006",
        ],
        types.MID_CAP: [  # 2B-10B
            "AdjRecovProb ≥70%",
            "ExpectedPL ≥2.0%",
            "Yield ≥3.0%",
            "EstRecovDays(max) ≤7",
            "Spread <0.008",
            "RSI14 <65",
            "Short Interest <4.0%",
            "IndTrend60d >-1.0%",
            "TrendVsInd60d >-0.5%",
            "AvgDVT7d >5M",
            "Liquidity >0.00048",
        ],
        types.SMALL_CAP: [  # 300M-2B
            "AdjRecovProb ≥75%",
            "ExpectedPL ≥3.0%",
            "Yield ≥4.5%",
            "EstRecovDays(max) ≤10",
            "Spread <0.015",
            "RSI14 <60",
            "Short Interest <2.5%",
            "IndTrend60d >0.0%",
            "TrendVsInd60d >0.0%",
            "AvgDVT7d >1M",
            "Liquidity >0.00036",
        ],
        types.MICRO_CAP: [  # 50M-300M
            "AdjRecovProb ≥85%",
            "ExpectedPL ≥5.0%",
            "Yield ≥6.5%",
            "EstRecovDays(max) ≤14",
            "Spread <0.025",
            "RSI14 <55",
            "Short Interest <1.5%",
            "IndTrend60d >1.0%",
            "TrendVsInd60d >1.0%",
            "AvgDVT7d >250K",
            "Liquidity >0.00024",
        ],
        types.NANO_CAP: [  # <50M
            "AdjRecovProb ≥90%",
            "ExpectedPL ≥7.0%",
            "Yield ≥8.5%",
            "EstRecovDays(max) ≤21",
            "Spread <0.030",
            "RSI14 <50",
            "Short Interest <1.0%",
            "IndTrend60d >2.0%",
            "TrendVsInd60d >2.0%",
            "AvgDVT7d >50K",
            "Liquidity >0.00012",
        ],
    },
    "NASDAQ": {
        types.LARGE_CAP: [  # >= 10B
            "AdjRecovProb ≥65%",
            "EstRecovDays(max) ≤3",
            "ExpectedPL ≥0.5%",
            "Yield ≥0.5%",
            "Spread <0.0005",
            "Beta <1.1",
            "RSI14 <65",
            "Short Interest <3.0%",
            "IndTrend60d >-2.0%",
            "TrendVsInd60d >-1.0%",
            # "AvgDVT7d >100M",
            "Liquidity >0.0004",
        ],
        types.MID_CAP: [  # 2B-10B
            "AdjRecovProb ≥70%",
            "EstRecovDays(max) ≤5",
            "ExpectedPL ≥1.0%",
            "Yield ≥1.0%",
            "Spread <0.0015",
            "Beta <1.0",
            "RSI14 <60",
            "Short Interest <2.0%",
            "IndTrend60d >-1.0%",
            "TrendVsInd60d >-0.5%",
            # "AvgDVT7d >20M",
            "Liquidity >0.00032",
        ],
        types.SMALL_CAP: [  # 300M-2B
            "AdjRecovProb ≥80%",
            "EstRecovDays(max) ≤8",
            "ExpectedPL ≥1.5%",
            "Yield ≥1.5%",
            "Spread <0.004",
            "Beta <0.9",
            "RSI14 <55",
            "Short Interest <1.0%",
            "IndTrend60d >0.0%",
            "TrendVsInd60d >0.0%",
            # "AvgDVT7d >5M",
            "Liquidity >0.00024",
        ],
    },
    "NYSE": {
        types.LARGE_CAP: [  # >= 10B
            "AdjRecovProb ≥60%",
            "EstRecovDays(max) ≤4",
            "ExpectedPL ≥0.8%",
            "Yield ≥1.0%",
            "Spread <0.001",
            "RSI14 <70",
            "Short Interest <4.0%",
            "IndTrend60d >-2.0%",
            "TrendVsInd60 >-1.0%",
            # "AvgDVT7d >50M",
            "Liquidity >0.0005",
        ],
        types.MID_CAP: [  # 2B-10B
            "AdjRecovProb ≥65%",
            "EstRecovDays(max) ≤6",
            "ExpectedPL ≥1.2%",
            "Yield ≥1.5%",
            "Spread <0.0025",
            "RSI14 <65",
            "Short Interest <3.0%",
            "IndTrend60d >-1.0%",
            "TrendVsInd60d >-0.5%",
            # "AvgDVT7d >10M",
            "Liquidity >0.0004",
        ],
        types.SMALL_CAP: [  # 300M-2B
            "AdjRecovProb ≥75%",
            "EstRecovDays ≤10",
            "ExpectedPL ≥2.0%",
            "Yield ≥2.5%",
            "Spread <0.005",
            "RSI14 <60",
            "Short Interest <2.0%",
            "IndTrend60d >0.0%",
            "TrendVsInd60d >0.0%",
            # "AvgDVT7d >2M",
            "Liquidity >0.0003",
        ],
    },
}

DEFAULT_INVESTOR_THEME = (
    "- Risk tolerance: moderate\n- Time horizon: 5-10 years\n- Goal: capital growth\n- Rebalance frequency: semi-annual"
)
