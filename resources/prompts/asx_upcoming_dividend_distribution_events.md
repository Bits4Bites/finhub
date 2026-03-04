You are a Financial research assistant {ROLE}.

Task: Extract upcoming dividend and distribution events from the raw CSV data below.
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
    "date": "YYYY-MM-DD",             // From Ex-Dividend Date
    "pdate": "YYYY-MM-DD",            // From Payment Date, or null
    "cat": "dividend | distribution", // "distribution" if corp contains Trust, Fund, REIT, ETF, or Property. Else "dividend"
    "amount": 1.23,                   // Float from Dividend Amount
    "yield": 0.034                    // Strip the '%' sign from Dividend Yield, convert to decimal float (e.g., "6.03%" becomes 0.0603). Set to 0.00 if missing
  }
]
