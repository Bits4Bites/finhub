# FinHub API Documentation

Base URL: `http://localhost:8000`

Most responses follow a standard envelope format:

```json
{
  "status": 200,
  "message": "ok",
  "data": ...
}
```

`GET /market/index/{index_id}` is the exception: it returns the cached static JSON file directly.

---

## Authentication

All endpoints under `/stocks`, `/events`, `/ai`, and `/toz` are protected by an API key. The
root (`/`), health (`/health`), and market (`/market`) endpoints are open.

The server-side key is configured via the `FINHUB_API_KEY` environment variable (or the
`app_config.env` file). When it is left empty, authentication is disabled and all requests are
allowed (fail-open).

When a key is configured, clients must send it in the `X-API-Key` request header (the header name
is case-insensitive). A missing or incorrect key returns `401`:

```json
{
  "status": 401,
  "message": "Invalid or missing API key"
}
```

**Example:**

```bash
curl -H 'X-API-Key: your-api-key' 'http://localhost:8000/stocks/quotes?symbols=AAPL'
```

---

## Market

### `GET /market/index/{index_id}`

Get the cached static JSON file for a market index. This public endpoint does not require an API
key. The index ID is case-insensitive and must be one of the hardcoded supported values.

| Parameter  | Type | Required | Description                                                                                                                             |
|------------|------|----------|-----------------------------------------------------------------------------------------------------------------------------------------|
| `index_id` | path | Yes      | Supported values: `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `HNX30`, `VN30`, and `VN100`. |

**Example:**

```bash
curl 'http://localhost:8000/market/index/SP500'
```

```json
{
  "date": "2026-07-28",
  "data": [
    {
      "symbol": "NASDAQ:AAPL",
      "company": "Apple Inc.",
      "sector": "Information Technology"
    }
  ]
}
```

> The response is served from the in-memory static-data cache and may not reflect real-time index
> constituents. Unsupported or unavailable IDs return HTTP `404`.

---

## Stocks

### `GET /stocks/quotes`

Get stock quotes for multiple symbols.

| Parameter | Type  | Required | Description                                                                                                               |
|-----------|-------|----------|---------------------------------------------------------------------------------------------------------------------------|
| `symbols` | query | Yes      | Comma-separated list of stock symbols. Accepts Yahoo Finance format (`CBA.AX`) or `EXCHANGE:CODE` format (`NASDAQ:AAPL`). |

**Example:**

```bash
curl 'http://localhost:8000/stocks/quotes?symbols=AAPL,NASDAQ:MSFT'
```

---

### `GET /stocks/{symbol}/overview`

Get overview information for a ticker symbol.

| Parameter | Type | Required | Description                                                              |
|-----------|------|----------|--------------------------------------------------------------------------|
| `symbol`  | path | Yes      | Stock symbol in YF format (`CBA.AX`) or `EXCHANGE:CODE` (`NASDAQ:AAPL`). |

**Example:**

```bash
curl 'http://localhost:8000/stocks/AAPL/overview'
```

---

### `GET /stocks/{symbol}/info`

Get detailed information for a ticker symbol.

| Parameter | Type | Required | Description                                                              |
|-----------|------|----------|--------------------------------------------------------------------------|
| `symbol`  | path | Yes      | Stock symbol in YF format (`CBA.AX`) or `EXCHANGE:CODE` (`NASDAQ:AAPL`). |

**Example:**

```bash
curl 'http://localhost:8000/stocks/AAPL/info'
```

---

### `GET /stocks/{symbol}/history`

Get historical daily price data for a ticker symbol.

| Parameter | Type  | Required | Default | Description                                                              |
|-----------|-------|----------|---------|--------------------------------------------------------------------------|
| `symbol`  | path  | Yes      |         | Stock symbol in YF format (`CBA.AX`) or `EXCHANGE:CODE` (`NASDAQ:AAPL`). |
| `days`    | query | No       | `100`   | Number of days of historical data to retrieve.                           |

**Example:**

```bash
curl 'http://localhost:8000/stocks/AAPL/history?days=30'
```

---

### `GET /stocks/{symbol}/quote_at/{date_str}`

Get stock quote at a specific date.

| Parameter  | Type | Required | Description                                   |
|------------|------|----------|-----------------------------------------------|
| `symbol`   | path | Yes      | Stock symbol in YF format or `EXCHANGE:CODE`. |
| `date_str` | path | Yes      | Date in `YYYY-MM-DD` format.                  |

> If the date falls on a non-trading day, the API may return the quote for the most recent trading day before the given date.

**Example:**

```bash
curl 'http://localhost:8000/stocks/AAPL/quote_at/2026-04-01'
```

---

### `GET /stocks/{symbol}/info_debug`

Get raw detailed information for a ticker symbol (debug mode).

| Parameter | Type | Required | Description   |
|-----------|------|----------|---------------|
| `symbol`  | path | Yes      | Stock symbol. |

---

### `GET /stocks/index/{index}/companies`

Get list of companies for a given market index.

| Parameter | Type | Required | Description                                                                                                                              |
|-----------|------|----------|------------------------------------------------------------------------------------------------------------------------------------------|
| `index`   | path | Yes      | Index name. Supported: `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `VN30`, `VN100`, `HNX30`. |

**Example:**

```bash
curl 'http://localhost:8000/stocks/index/NASDAQ100/companies'
```

> The data may not be up-to-date as the API relies on static data files for index constituents.

---

## Events

### `GET /events/upcoming_dividends`

Get upcoming dividend/distribution events for a market.

| Parameter | Type  | Required | Description                                                                                                                        |
|-----------|-------|----------|------------------------------------------------------------------------------------------------------------------------------------|
| `country` | query | Yes      | Country code: `AU`, `US`, or `VN`.                                                                                                 |
| `index`   | query | No       | Filter by index: `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `VN30`, `VN100`, `HNX30`. |

Events for stocks in major indices (ASX300, NASDAQ100, SP500, SP400, VN100) include AI-generated dividend analysis.

**Example:**

```bash
curl 'http://localhost:8000/events/upcoming_dividends?country=AU&index=ASX200'
```

### `GET /events/upcoming_dividends_async`

Run the upcoming-dividends request in the background. Start a task with the same `country` and
`index` parameters, then poll using the returned task ID. Task state and results expire after one hour.

| Parameter | Type  | Required    | Description                                                                                                   |
|-----------|-------|-------------|---------------------------------------------------------------------------------------------------------------|
| `country` | query | Conditional | Country code: `AU`, `US`, or `VN`. Required when starting a task.                                             |
| `index`   | query | No          | Optional stock-index filter used when starting a task; supports the same indices as the synchronous endpoint. |
| `task_id` | query | Conditional | Task ID returned when starting a task. Required when polling.                                                 |

```bash
# Start a task
curl 'http://localhost:8000/events/upcoming_dividends_async?country=AU&index=ASX200'

# Poll a task
curl 'http://localhost:8000/events/upcoming_dividends_async?task_id=<TASK_ID>'
```

Starting a task returns HTTP `202`:

```json
{
  "status": 202,
  "message": "Task started",
  "extra": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "state": "RUNNING"
  }
}
```

Polling returns:

| HTTP status | Task state  | Result                                              |
|-------------|-------------|-----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                          |
| `200`       | `COMPLETED` | The standard upcoming-dividends payload in `data`.  |
| `500`       | `FAILED`    | The background task failed.                         |
| `404`       | —           | The task ID is unknown or its cache entry expired.  |

---

### `GET /events/upcoming_earnings`

Get upcoming earnings events for a market.

| Parameter | Type  | Required | Description                                                                                              |
|-----------|-------|----------|----------------------------------------------------------------------------------------------------------|
| `country` | query | Yes      | Country code: `AU` or `US`.                                                                              |
| `index`   | query | No       | Filter by index: `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`. |

**Example:**

```bash
curl 'http://localhost:8000/events/upcoming_earnings?country=US&index=SP500'
```

### `GET /events/upcoming_earnings_async`

Run the upcoming-earnings request in the background using the same one-hour task lifecycle as
`/events/upcoming_dividends_async`.

| Parameter | Type  | Required    | Description                                                        |
|-----------|-------|-------------|--------------------------------------------------------------------|
| `country` | query | Conditional | Country code: `AU` or `US`. Required when starting a task.         |
| `index`   | query | No          | Optional stock-index filter used when starting a task.             |
| `task_id` | query | Conditional | Task ID returned when starting a task. Required when polling.      |

```bash
# Start a task
curl 'http://localhost:8000/events/upcoming_earnings_async?country=US&index=SP500'

# Poll a task
curl 'http://localhost:8000/events/upcoming_earnings_async?task_id=<TASK_ID>'
```

Starting a task returns HTTP `202`:

```json
{
  "status": 202,
  "message": "Task started",
  "extra": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "state": "RUNNING"
  }
}
```

Polling returns:

| HTTP status | Task state  | Result                                             |
|-------------|-------------|----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                         |
| `200`       | `COMPLETED` | The standard upcoming-earnings payload in `data`.  |
| `500`       | `FAILED`    | The background task failed.                        |
| `404`       | —           | The task ID is unknown or its cache entry expired. |

---

### `GET /events/new_listings`

Get new listing events for a market (AI-assisted).

| Parameter | Type  | Required | Description                                     |
|-----------|-------|----------|-------------------------------------------------|
| `country` | query | Yes      | Country code. Currently only `AU` is supported. |

**Example:**

```bash
curl 'http://localhost:8000/events/new_listings?country=AU'
```

### `GET /events/new_listings_async`

Run the new-listings request in the background. Task state and results expire after one hour.

| Parameter | Type  | Required    | Description                                                                    |
|-----------|-------|-------------|--------------------------------------------------------------------------------|
| `country` | query | Conditional | Country code. Currently only `AU` is supported. Required when starting a task. |
| `task_id` | query | Conditional | Task ID returned when starting a task. Required when polling.                  |

```bash
# Start a task
curl 'http://localhost:8000/events/new_listings_async?country=AU'

# Poll a task
curl 'http://localhost:8000/events/new_listings_async?task_id=<TASK_ID>'
```

Starting a task returns HTTP `202`:

```json
{
  "status": 202,
  "message": "Task started",
  "extra": {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "state": "RUNNING"
  }
}
```

Polling returns:

| HTTP status | Task state  | Result                                             |
|-------------|-------------|----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                         |
| `200`       | `COMPLETED` | The standard new-listings payload in `data`.       |
| `500`       | `FAILED`    | The background task failed.                        |
| `404`       | —           | The task ID is unknown or its cache entry expired. |

---

## AI

AI features use one HTTP verb consistently across each endpoint pair: `VERB /endpoint` runs synchronously,
`VERB /endpoint_async` starts a background task, and `VERB /endpoint_async?task_id=<TASK_ID>` polls it. The
AI-assisted new-listings endpoints under `/events` follow the same convention.

### `GET /ai/vendors`

Get the list of available AI vendors and supported API tiers and models.

No parameters required.

**Example:**

```bash
curl 'http://localhost:8000/ai/vendors'
```

---

### `POST /ai/analyze_dividend_event`

Analyze a dividend event using deterministic historical metrics, sourced AI research, and a no-web strategy
assessment. Estimates are gross and pre-tax.

| JSON field                                           | Required | Description                                                        |
|------------------------------------------------------|----------|--------------------------------------------------------------------|
| `symbol`                                             | Yes      | Symbol in YF (`CBA.AX`) or `EXCHANGE:CODE` (`NASDAQ:AAPL`) format. |
| `ex_date`                                            | Yes      | Ex-dividend date in `YYYY-MM-DD` format.                           |
| `dividend_amount`                                    | Yes      | Positive finite gross dividend per share.                          |
| `transaction_costs.dividend_capture_per_share`       | No       | Non-negative round-trip per-share cost; defaults to zero.          |
| `transaction_costs.post_dividend_discount_per_share` | No       | Non-negative round-trip per-share cost; defaults to zero.          |
| `holding_period_days`                                | No       | Calendar-day analysis window from 1 through 365; defaults to 28.   |

**Example:**

```bash
curl -X POST 'http://localhost:8000/ai/analyze_dividend_event' \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"NASDAQ:AAPL","ex_date":"2026-08-10","dividend_amount":0.26}'
```

The response keeps deterministic ex-date open/close/intraday-low drops and later drawdown separate. It also returns
recovery estimates for the pre-ex close and both strategy break-even targets, source-linked research, independent
strategy assessments, and one of `DividendCapture`, `PostDividendDiscount`, `NoClearWinner`, or
`InsufficientInsights`. If an AI stage fails, HTTP `502` still includes the deterministic baseline with
`analysis_status=Failed`.

Repairable assessment arithmetic mismatches return HTTP `200` with `analysis_status=CompleteWithWarnings`.
`validation_warnings` identifies each application correction, and the affected strategy repeats the warning in
`data_gaps`.

### `POST /ai/analyze_dividend_event_async`

Start dividend-event analysis in the background using the same JSON body as the synchronous endpoint, or poll the
same endpoint with the returned task ID in the `task_id` query parameter. Task state and results expire after one
hour. Completed analysis cache freshness varies from one hour to 72 hours based on event phase and proximity.

```bash
# Start a task
curl -X POST 'http://localhost:8000/ai/analyze_dividend_event_async' \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"NASDAQ:AAPL","ex_date":"2026-08-10","dividend_amount":0.26}'

# Poll a task
curl -X POST 'http://localhost:8000/ai/analyze_dividend_event_async?task_id=<TASK_ID>'
```

Polling returns:

| HTTP status | Task state  | Result                                              |
|-------------|-------------|-----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                          |
| `200`       | `COMPLETED` | The standard dividend-analysis payload in `data`.   |
| `400`/`422` | `FAILED`    | Market input or history validation failed.          |
| `502`       | `FAILED`    | An AI stage failed; deterministic data is retained. |
| `500`       | `FAILED`    | An unexpected background task failure occurred.     |
| `404`       | —           | The task ID is unknown or its cache entry expired.  |

---

### `POST /ai/analyze_ticker`

Analyze a stock ticker using AI.

**Request Body (JSON):**

| Field    | Type     | Required | Description                                                                       |
|----------|----------|----------|-----------------------------------------------------------------------------------|
| `symbol` | `string` | Yes      | Stock symbol in YF format (`CBA.AX`) or `EXCHANGE:CODE` (`NASDAQ:AAPL`).          |
| `intent` | `string` | No       | Analysis intent defining the angle of insight. Defaults to a built-in intent.     |

**Example:**

```bash
curl -X POST 'http://localhost:8000/ai/analyze_ticker' \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "CBA.AX", "intent": "dividend capture strategy"}'
```

### `POST /ai/analyze_ticker_async`

Run ticker analysis in the background. Start a task with the same JSON request body as
`/ai/analyze_ticker`, then poll by posting to this endpoint with the returned task ID. Task state and
results expire after one hour; completed analyses are cached for 72 hours.

| Parameter | Location  | Required    | Description                                                   |
|-----------|-----------|-------------|---------------------------------------------------------------|
| `symbol`  | JSON body | Conditional | Stock symbol. Required when starting a task.                  |
| `intent`  | JSON body | No          | Optional analysis intent used when starting a task.           |
| `task_id` | query     | Conditional | Task ID returned when starting a task. Required when polling. |

```bash
# Start a task
curl -X POST 'http://localhost:8000/ai/analyze_ticker_async' \
  -H 'Content-Type: application/json' \
  -d '{"symbol": "CBA.AX", "intent": "dividend capture strategy"}'

# Poll a task
curl -X POST 'http://localhost:8000/ai/analyze_ticker_async?task_id=<TASK_ID>'
```

Polling returns:

| HTTP status | Task state  | Result                                             |
|-------------|-------------|----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                         |
| `200`       | `COMPLETED` | The standard ticker-analysis payload in `data`.    |
| `500`       | `FAILED`    | The background task failed.                        |
| `404`       | —           | The task ID is unknown or its cache entry expired. |

---

### `POST /ai/build_portfolio`

Construct one research-backed target portfolio from a required investor theme. With no positive-share positions the
flow constructs from scratch; otherwise it verifies positive starting holdings and uses them as seed context.

**Request Body (JSON):**

| Field                | Type                 | Required | Description                                                                                  |
|----------------------|----------------------|----------|----------------------------------------------------------------------------------------------|
| `country`            | `string`             | Yes      | ISO code or country name, from 2 through 64 characters.                                      |
| `investor_theme`     | `string`             | Yes      | Non-blank goals, constraints, preferences, horizon, and risk context; maximum 4,000 characters. |
| `current_allocation` | `PortfolioHolding[]` | No       | Up to 50 starting positions; defaults to `[]`, and zero-share positions are ignored.         |

Each `PortfolioHolding` object:

| Field               | Type   | Description                                     |
|---------------------|--------|-------------------------------------------------|
| `ticker`            | string | Required stock symbol, limited to 32 characters.                    |
| `num_shares`        | float  | Non-negative finite share count; defaults to zero.                  |
| `avg_price`         | float  | Non-negative finite average purchase price; defaults to zero.       |
| `market_price`      | float  | Optional positive current market price per share.                   |
| `target_allocation` | float  | Optional target allocation from `0` through `1`.                    |
| `tags`              | string | Optional holding metadata, limited to 500 characters.               |

**Example:**

```bash
curl -X POST 'http://localhost:8000/ai/build_portfolio' \
  -H 'Content-Type: application/json' \
  -d '{"country": "AU", "investor_theme": "growth with moderate risk"}'
```

Unknown request fields, including `rebalance_plan`, are rejected. Duplicate normalized request tickers are also
rejected. Positive starting holdings are verified against current market data; duplicate canonical tickers and
mixed-currency seeds are invalid.

The `data` object contains:

| Field                     | Description                                                                                         |
|---------------------------|-----------------------------------------------------------------------------------------------------|
| `as_of`                   | Timezone-aware finalization timestamp.                                                              |
| `construction_status`     | `Complete` or `CompleteWithWarnings`.                                                               |
| `construction_mode`       | `Scratch` or `Seeded`.                                                                              |
| `country`                 | Normalized ISO 3166-1 alpha-2 country code.                                                         |
| `investor_theme`          | Normalized theme used by every AI stage.                                                            |
| `summary`                 | Concise explanation of the target portfolio.                                                        |
| `verified_seed_holdings`  | Verified positive starting holdings; empty in `Scratch` mode.                                       |
| `target_portfolio`        | Three through 20 researched target positions whose `allocation` values sum to `1.0`.                |
| `overall_data_quality`    | `High`, `Medium`, `Low`, or `Insufficient`.                                                         |
| `data_gaps`               | Limitations found during verification, planning, research, or construction.                         |
| `validation_warnings`     | Source-verification warnings.                                                                       |
| `references`              | Canonical HTTPS sources cited by target positions.                                                  |

Each target position contains `ticker`, optional `company_name`, `allocation`, `role`, `rationale`, and
`reference_ids`. The response contains allocation percentages only: it does not invent an investment amount, share
counts, costs, trades, or a rebalance plan.

The quality-first flow is seed verification, structured theme-aware planning, sourced candidate research, structured
portfolio construction, and deterministic final validation. Verification is cached for five minutes; planning,
research, construction, and the final result are independently cached for one hour.

### `POST /ai/build_portfolio_async`

Build a portfolio in the background. Start a task with the same JSON request body as
`/ai/build_portfolio`, then poll by posting to this endpoint with the returned task ID. Task state and
results expire after one hour.

| Parameter            | Location  | Required    | Description                                                   |
|----------------------|-----------|-------------|---------------------------------------------------------------|
| `current_allocation` | JSON body | No          | Optional existing holdings used when starting a task.         |
| `country`            | JSON body | Conditional | Country context. Required when starting a task.               |
| `investor_theme`     | JSON body | Conditional | Required non-blank investor theme when starting a task.       |
| `task_id`            | query     | Conditional | Task ID returned when starting a task. Required when polling. |

```bash
# Start a task
curl -X POST 'http://localhost:8000/ai/build_portfolio_async' \
  -H 'Content-Type: application/json' \
  -d '{"country": "AU", "investor_theme": "growth with moderate risk"}'

# Poll a task
curl -X POST 'http://localhost:8000/ai/build_portfolio_async?task_id=<TASK_ID>'
```

Polling returns:

| HTTP status | Task state  | Result                                             |
|-------------|-------------|----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                         |
| `200`       | `COMPLETED` | The standard build-portfolio payload in `data`.    |
| `422`       | `FAILED`    | Request semantics or verified seed holdings are invalid. |
| `502`       | `FAILED`    | Market verification, AI execution, or structured output failed. |
| `500`       | `FAILED`    | An unexpected background error occurred.           |
| `404`       | —           | The task ID is unknown or its cache entry expired. |

---

### `POST /ai/spotlight_portfolio`

Verify a portfolio against current market data, build a validated analysis plan, research its material risks, and
return up to four ranked, structured risk actions. Risk levels are limited to `Critical`, `High`, and `Medium`.

**Request Body (JSON):**

| Field                | Type                 | Required | Description                                                                                          |
|----------------------|----------------------|----------|------------------------------------------------------------------------------------------------------|
| `country`            | `string`             | Yes      | ISO code or country name, from 2 through 64 characters.                                              |
| `current_allocation` | `PortfolioHolding[]` | No       | Up to 50 positions; defaults to `[]`. Empty or all-zero positions skip verification and every AI stage. |
| `investor_theme`     | `string \| null`     | No       | Optional risk tolerance, horizon, goals, and preferences. Omitted, null, or blank means no theme.    |

Each `PortfolioHolding` object:

| Field               | Required | Description                                                                                          |
|---------------------|----------|------------------------------------------------------------------------------------------------------|
| `ticker`            | Yes      | Stock symbol in Yahoo Finance or `EXCHANGE:CODE` format, limited to 32 characters.                   |
| `num_shares`        | No       | Non-negative finite share count; defaults to zero.                                                   |
| `avg_price`         | No       | Non-negative finite average purchase price; defaults to zero.                                        |
| `market_price`      | No       | Positive client price used only when authoritative market data has no usable price.                  |
| `target_allocation` | No       | Target portfolio weight from `0` through `1`.                                                        |
| `tags`              | No       | Optional holding metadata, limited to 500 characters.                                                |

Duplicate request tickers, unknown securities, duplicate canonical symbols, and mixed-currency portfolios are
rejected. Zero-share positions are ignored.

**Example:**

```bash
curl -X POST 'http://localhost:8000/ai/spotlight_portfolio' \
  -H 'Content-Type: application/json' \
  -d '{
    "country": "AU",
    "investor_theme": "growth with moderate risk",
    "current_allocation": [
      {"ticker": "CBA.AX", "num_shares": 10, "avg_price": 150.0, "market_price": 160.9, "target_allocation": 0.35, "tags": "bank"},
      {"ticker": "BHP.AX", "num_shares": 20, "avg_price": 40.0, "market_price": 61.24, "target_allocation": 0.30, "tags": "resources"},
      {"ticker": "CSL.AX", "num_shares": 15, "avg_price": 90.0, "market_price": 97.91, "target_allocation": 0.35, "tags": "healthcare"}
    ]
  }'
```

The `data` object contains:

| Field                     | Description                                                                                         |
|---------------------------|-----------------------------------------------------------------------------------------------------|
| `as_of`                   | Timezone-aware analysis timestamp.                                                                  |
| `analysis_status`         | `Complete` or `CompleteWithWarnings`.                                                               |
| `portfolio_empty`         | Whether the request contained no positive-share positions.                                          |
| `overall_data_quality`    | `High`, `Medium`, `Low`, or `Insufficient`.                                                         |
| `snapshot`                | Verified holdings, allocations, valuation, price source, P/L, target drift, and verification gaps. |
| `risks`                   | Up to four ranked `PortfolioSpotlightRiskAction` objects.                                           |
| `rebalance_recommended`   | Deterministic `YES` when any risk requires rebalancing; otherwise `NO`.                              |
| `data_gaps`               | Analysis-level evidence gaps.                                                                       |
| `validation_warnings`     | Application validation or source-verification warnings.                                             |
| `references`              | Canonical HTTPS sources cited by the returned risks.                                                 |

Each risk includes `rank`, `level`, `action_timing`, `risk`, `action`, `affected_tickers`,
`requires_rebalance`, `confidence`, `data_gaps`, and `reference_ids`. Timing is fixed by risk level:
`Critical` means `AsSoonAsPossibleWithinOneWeek`, `High` means `WithinOneToTwoWeeks`, and `Medium` means `Monitor`.
The API returns only the `YES`/`NO` rebalance recommendation, not a rebalance plan.

An empty or all-zero portfolio returns HTTP `200` with `portfolio_empty=true`, `snapshot=null`, no risks,
`rebalance_recommended=NO`, and `overall_data_quality=Insufficient`, without invoking AI.

For a non-empty portfolio, the flow is verify, build a structured plan, perform sourced research, assess the validated
research, and deterministically finalize the response. The plan adapts to a supplied investor theme; without one, it
derives priorities only from the verified holdings.

Invalid input returns HTTP `422`. Portfolio-verification, AI-provider, and invalid structured-output failures return
HTTP `502`.

### `POST /ai/spotlight_portfolio_async`

Run the same structured portfolio spotlight flow in the background. Start a task with the same JSON request body as
`/ai/spotlight_portfolio`, then poll by posting to this endpoint with the returned task ID. Task state and results
expire after one hour. Verification is cached for five minutes; planning, research, assessment, and final analysis
stages are cached independently for one hour.

| Parameter            | Location  | Required    | Description                                                   |
|----------------------|-----------|-------------|---------------------------------------------------------------|
| Request body         | JSON body | Conditional | Spotlight request. Required when starting and omitted when polling. |
| `task_id`            | query     | Conditional | Task ID returned when starting a task. Required when polling. |

```bash
# Start a task
curl -X POST 'http://localhost:8000/ai/spotlight_portfolio_async' \
  -H 'Content-Type: application/json' \
  -d '{
    "country": "AU",
    "current_allocation": [
      {"ticker": "CBA.AX", "num_shares": 10, "avg_price": 150.0, "target_allocation": 1.0}
    ]
  }'

# Poll a task
curl -X POST 'http://localhost:8000/ai/spotlight_portfolio_async?task_id=<TASK_ID>'
```

Polling returns:

| HTTP status | Task state  | Result                                              |
|-------------|-------------|-----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                          |
| `200`       | `COMPLETED` | The standard spotlight-portfolio payload in `data`. |
| `422`       | `FAILED`    | Portfolio input validation failed.                  |
| `502`       | `FAILED`    | Portfolio verification or an AI stage failed.       |
| `500`       | `FAILED`    | The background task failed.                         |
| `404`       | —           | The task ID is unknown or its cache entry expired.  |

---

### `POST /ai/analyze_portfolio`

Analyze or build a stock portfolio using AI. Positive-share holdings select the existing-portfolio review branch,
which can optionally assess whether a major rebalance is needed. Empty or all-zero holdings select the structured
construction flow described under `/ai/build_portfolio`.

**Request Body (JSON):**

| Field                | Type              | Required | Description                                                                                                                      |
|----------------------|-------------------|----------|----------------------------------------------------------------------------------------------------------------------------------|
| `current_allocation` | `PortfolioHolding[]` | No       | List of current holdings. If empty, builds a new portfolio instead.                                                              |
| `country`            | `string`          | Yes      | Required country context for the analysis (e.g. `AU`, `US`).                                                                     |
| `investor_theme`     | `string`          | Conditional | Required and non-blank for construction; optional for review, where omission uses the review default.                         |
| `rebalance_plan`     | `boolean`         | No       | If `true`, assesses whether existing holdings need a major rebalance and generates a plan only when needed. Defaults to `false`. |

Each `PortfolioHolding` object:

| Field               | Type   | Description                                     |
|---------------------|--------|-------------------------------------------------|
| `ticker`            | string | Required stock symbol, limited to 32 characters.                    |
| `num_shares`        | float  | Non-negative finite share count; defaults to zero.                  |
| `avg_price`         | float  | Non-negative finite average purchase price; defaults to zero.       |
| `market_price`      | float  | Optional positive current market price per share.                   |
| `target_allocation` | float  | Optional target allocation from `0` through `1`.                    |
| `tags`              | string | Optional holding metadata, limited to 500 characters.               |

**Example:**

```bash
curl -X POST 'http://localhost:8000/ai/analyze_portfolio' \
  -H 'Content-Type: application/json' \
  -d '{
    "current_allocation": [
      {"ticker": "AAPL", "num_shares": 50, "avg_price": 150.0, "market_price": 195.0, "target_allocation": 0.3},
      {"ticker": "MSFT", "num_shares": 30, "avg_price": 280.0, "market_price": 420.0, "target_allocation": 0.3},
      {"ticker": "GOOGL", "num_shares": 20, "avg_price": 120.0, "market_price": 175.0, "target_allocation": 0.4}
    ],
    "country": "US",
    "investor_theme": "growth with moderate risk",
    "rebalance_plan": true
  }'
```

**Response `data`:**

The construction branch returns the structured `PortfolioConstruction` object documented under
`/ai/build_portfolio`. The review branch returns:

| Field            | Type             | Description                                                                                                 |
|------------------|------------------|-------------------------------------------------------------------------------------------------------------|
| `analysis`       | `string`         | Premium review of the existing positive-share portfolio.                                                   |
| `rebalance_plan` | `string`         | Premium rebalance plan when needed; `"No rebalance needed"` when assessed but unnecessary; otherwise empty. |
| `llm_error`      | `boolean`        | Whether an LLM stage failed.                                                                                |
| `llm_error_msg`  | `string \| null` | Error details when an LLM stage fails.                                                                      |

If the rebalance decision or any later rebalance stage fails after the portfolio review succeeds, `analysis` retains
the completed review while `llm_error` and `llm_error_msg` describe the later failure.

### `POST /ai/analyze_portfolio_async`

Analyze or build a portfolio in the background using the same review-or-build behavior and JSON
request body as `/ai/analyze_portfolio`. Poll by posting to this endpoint with the returned task ID.
Task state and results expire after one hour. Construction results use one-hour stage and final caches; the legacy
review branch retains its existing review cache behavior.

| Parameter            | Location  | Required    | Description                                                   |
|----------------------|-----------|-------------|---------------------------------------------------------------|
| `current_allocation` | JSON body | No          | Holdings to review; when empty, a new portfolio is built.     |
| `country`            | JSON body | Conditional | Country context. Required when starting a task.               |
| `investor_theme`     | JSON body | Conditional | Required for construction; optional for review.               |
| `rebalance_plan`     | JSON body | No          | Whether to generate a major-rebalance plan when needed.       |
| `task_id`            | query     | Conditional | Task ID returned when starting a task. Required when polling. |

```bash
# Start a task
curl -X POST 'http://localhost:8000/ai/analyze_portfolio_async' \
  -H 'Content-Type: application/json' \
  -d '{
    "country": "US",
    "current_allocation": [
      {"ticker": "AAPL", "num_shares": 50, "avg_price": 150.0, "target_allocation": 1.0}
    ],
    "rebalance_plan": true
  }'

# Poll a task
curl -X POST 'http://localhost:8000/ai/analyze_portfolio_async?task_id=<TASK_ID>'
```

Polling returns:

| HTTP status | Task state  | Result                                             |
|-------------|-------------|----------------------------------------------------|
| `202`       | `RUNNING`   | The task is still running.                         |
| `200`       | `COMPLETED` | The standard analyze-portfolio payload in `data`.  |
| `422`       | `FAILED`    | Construction input or verified seeds are invalid.  |
| `502`       | `FAILED`    | Construction verification or an AI stage failed.  |
| `500`       | `FAILED`    | The background task failed.                        |
| `404`       | —           | The task ID is unknown or its cache entry expired. |

---

## Precious Metals (Troy Ounce)

### `GET /toz/gold/quote`

Get current gold price.

| Parameter  | Type  | Required | Default | Description                        |
|------------|-------|----------|---------|------------------------------------|
| `currency` | query | No       | `USD`   | Currency code (e.g. `AUD`, `EUR`). |

**Example:**

```bash
curl 'http://localhost:8000/toz/gold/quote?currency=AUD'
```

---

### `GET /toz/gold/history`

Get historical gold prices.

| Parameter  | Type  | Required | Default | Description                |
|------------|-------|----------|---------|----------------------------|
| `currency` | query | No       | `USD`   | Currency code.             |
| `days`     | query | No       | `30`    | Number of days of history. |

**Example:**

```bash
curl 'http://localhost:8000/toz/gold/history?currency=AUD&days=90'
```

---

### `GET /toz/silver/quote`

Get current silver price.

| Parameter  | Type  | Required | Default | Description    |
|------------|-------|----------|---------|----------------|
| `currency` | query | No       | `USD`   | Currency code. |

**Example:**

```bash
curl 'http://localhost:8000/toz/silver/quote?currency=AUD'
```

---

### `GET /toz/silver/history`

Get historical silver prices.

| Parameter  | Type  | Required | Default | Description                |
|------------|-------|----------|---------|----------------------------|
| `currency` | query | No       | `USD`   | Currency code.             |
| `days`     | query | No       | `30`    | Number of days of history. |

**Example:**

```bash
curl 'http://localhost:8000/toz/silver/history?currency=EUR&days=7'
```

---

## Health & Root

### `GET /`

Returns a welcome message.

### `GET /health`

Health check endpoint. Returns `{"status": 200, "message": "ok"}`.
