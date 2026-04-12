TASK: Extract upcoming ASX listings from RAW INPUT DATA into a JSON array. If none, return [].

Rules:
- Listing date is next to company name (NOT "Expected offer close date").
- Skip entries with unconfirmed dates (TBC/TBA/TBD).
- Map principal_activities to ONE sector from: {SECTORS}
  (normalize synonyms, e.g. "INFORMATION TECHNOLOGY" → TECHNOLOGY).

Output:
- Raw JSON only (no markdown/text), starting with [ and ending with ].

Schema:
[
  {
    "symbol": "ASX:{TICKER}",
    "company": "string",
    "date": "YYYY-MM-DD",
    "price": 0.0,
    "principal_activities": "string",
    "sector": "string",
    "capital": 0
  }
]

Notes:
- price: float, strip currency/text.
- capital: int, strip currency/commas.

RAW INPUT DATA:
{RAW_INPUT_DATA}
