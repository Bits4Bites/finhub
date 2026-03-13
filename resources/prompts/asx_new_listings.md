Extract upcoming ASX listings from the RAW INPUT DATA section into a JSON array. If no data is available, return an empty array.

IMPORTANT: the "Expected offer close date" is NOT the listing date. The listing date is presented next to the company name.
Ignore the entry if the listing date is not confirmed (e.g. "TBC" or "TBA" or "TBD").

Return ONLY raw, valid JSON. Do NOT wrap the output in Markdown blocks (no ```). Start with [ and end with ].

Schema:
[
  {
    "symbol": "ASX:{ticker}",  // where {ticker} is the ASX ticker symbol, upper case
    "company": "string",       // Company name
    "date": "YYYY-MM-DD",      // Expected Listing date 
    "price": 0.0,              // Extract Issue price as a float (e.g., 0.20). Remove currency symbols/text
    "industry": "string",      // Map from Principal activities
    "capital": "string"        // Map from Capital to be raised
  }}
]

# RAW INPUT DATA

{RAW_INPUT_DATA}
