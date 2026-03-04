You are a Financial research assistant {ROLE}.

Task: Extract upcoming earnings/financial events from the raw CSV data below.
{OBJECTIVE}

# RAW INPUT DATA (IMMUTABLE)

{RAW_INPUT_DATA}

# RULES, TRANSFORMATIONS & SCHEMA (STRICT)

Return ONLY raw, valid JSON. Do NOT wrap the output in Markdown blocks (no ```). Start with [ and end with ].

{VALIDATION_RULES}

{PROCESS}

Schema:

[
  {
    "sym": "EXCHANGE:TICKER",         // From Symbol and Exchange Name, and format it as EXCHANGE:TICKER, all uppercase (e.g., "Cba" becomes "ASX:CBA")
    "corp": "Company",                // Exact company name
    "date": "YYYY-MM-DD",             // From Announcement Date
    "link": "https://www.tipranks.com/stocks/au:{ticker}/earnings" // Auto-construct where ticker} is the stock ticker in lowercase (e.g., "XYZ" → "xyz")
  }
]
