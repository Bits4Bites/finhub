# FinHub API Documentation

Base URL: `http://localhost:8000`

All responses follow a standard envelope format:

```json
{
  "status": 200,
  "message": "ok",
  "data": ...
}
```

---

## Authentication

All endpoints under `/stocks`, `/events`, `/ai`, and `/toz` are protected by an API key. The
root (`/`) and health (`/health`) endpoints are open.

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
| `days`    | query | No       | `100`   | Number of days of historical data to retrieve.                          |

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

| Parameter | Type  | Required | Description                                                                                                               |
|-----------|-------|----------|---------------------------------------------------------------------------------------------------------------------------|
| `country` | query | Yes      | Country code: `AU`, `US`, or `VN`.                                                                                        |
| `index`   | query | No       | Filter by index: `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `VN30`, `VN100`. |

Events for stocks in major indices (ASX300, NASDAQ100, SP500, SP400, VN100) include AI-generated dividend analysis.

**Example:**

```bash
curl 'http://localhost:8000/events/upcoming_dividends?country=AU&index=ASX200'
```

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

---

### `GET /events/new_listings`

Get new listing events for a market (AI-assisted).

| Parameter | Type  | Required | Description                                     |
|-----------|-------|----------|-------------------------------------------------|
| `country` | query | No       | Country code. Currently only `AU` is supported. |

**Example:**

```bash
curl 'http://localhost:8000/events/new_listings?country=AU'
```

---

## AI

### `GET /ai/vendors`

Get the list of available AI vendors and supported API tiers and models.

No parameters required.

**Example:**

```bash
curl 'http://localhost:8000/ai/vendors'
```

---

### `GET /ai/analyze_dividend_event`

Analyze a dividend event using AI.

| Parameter    | Type  | Required | Description                                                                                                  |
|--------------|-------|----------|--------------------------------------------------------------------------------------------------------------|
| `symbol`     | query | Yes      | Stock symbol in YF format (`CBA.AX`) or `EXCHANGE:CODE` (`NASDAQ:AAPL`).                                     |
| `ex_date`    | query | Yes      | Ex-dividend date in `YYYY-MM-DD` format.                                                                     |
| `div_amount` | query | Yes      | Dividend amount as a float (e.g. `0.50`).                                                                    |
| `intent`     | query | No       | Analysis intent/context. Defaults to `"Looking to capture the dividend or if post-div dip is worth buying"`. |

**Example:**

```bash
curl 'http://localhost:8000/ai/analyze_dividend_event?symbol=AAPL&ex_date=2026-02-09&div_amount=0.26'
```

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

---

### `POST /ai/build_portfolio`

Build a new portfolio using AI assistance.

**Request Body (JSON):**

| Field                | Type              | Required | Description                                                               |
|----------------------|-------------------|----------|---------------------------------------------------------------------------|
| `current_allocation` | `HoldingTicker[]` | No       | List of existing holdings (see fields below).                             |
| `country`            | `string`          | No       | Country context for the portfolio (e.g. `AU`, `US`).                      |
| `investor_theme`     | `string`          | No       | Investor theme/preference for the analysis. Defaults to a built-in theme. |

Each `HoldingTicker` object:

| Field               | Type   | Description                                     |
|---------------------|--------|-------------------------------------------------|
| `ticker`            | string | Stock symbol.                                   |
| `num_shares`        | float  | Number of shares held.                          |
| `avg_price`         | float  | Average purchase price per share.               |
| `market_price`      | float  | Current market price per share.                 |
| `target_allocation` | float  | Target allocation weight (e.g. `0.25` for 25%). |
| `tags`              | string | Optional tag(s) for the holding.                |

**Example:**

```bash
curl -X POST 'http://localhost:8000/ai/build_portfolio' \
  -H 'Content-Type: application/json' \
  -d '{"country": "AU", "investor_theme": "growth with moderate risk"}'
```

---

### `POST /ai/spotlight_portfolio`

Review a portfolio and highlight the top immediate risks and prioritized immediate actions using AI.

**Request Body (JSON):**

| Field                | Type              | Required | Description                                                               |
|----------------------|-------------------|----------|---------------------------------------------------------------------------|
| `current_allocation` | `HoldingTicker[]` | No       | List of current holdings to review.                                       |
| `country`            | `string`          | No       | Country context for the analysis (e.g. `AU`, `US`).                       |
| `investor_theme`     | `string`          | No       | Investor theme/preference for the analysis. Defaults to a built-in theme. |

Each `HoldingTicker` object:

| Field               | Type   | Description                                     |
|---------------------|--------|-------------------------------------------------|
| `ticker`            | string | Stock symbol.                                   |
| `num_shares`        | float  | Number of shares held.                          |
| `avg_price`         | float  | Average purchase price per share.               |
| `market_price`      | float  | Current market price per share.                 |
| `target_allocation` | float  | Target allocation weight (e.g. `0.25` for 25%). |
| `tags`              | string | Optional tag(s) for the holding.                |

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

---

### `POST /ai/analyze_portfolio`

Analyze or build a stock portfolio using AI. If `current_allocation` is provided, reviews the existing portfolio; otherwise builds a new one.

**Request Body (JSON):**

| Field                | Type              | Required | Description                                                               |
|----------------------|-------------------|----------|---------------------------------------------------------------------------|
| `current_allocation` | `HoldingTicker[]` | No       | List of current holdings. If empty, builds a new portfolio instead.       |
| `country`            | `string`          | No       | Country context for the analysis (e.g. `AU`, `US`).                       |
| `investor_theme`     | `string`          | No       | Investor theme/preference for the analysis. Defaults to a built-in theme. |

Each `HoldingTicker` object:

| Field               | Type   | Description                                     |
|---------------------|--------|-------------------------------------------------|
| `ticker`            | string | Stock symbol.                                   |
| `num_shares`        | float  | Number of shares held.                          |
| `avg_price`         | float  | Average purchase price per share.               |
| `market_price`      | float  | Current market price per share.                 |
| `target_allocation` | float  | Target allocation weight (e.g. `0.25` for 25%). |
| `tags`              | string | Optional tag(s) for the holding.                |

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
    "investor_theme": "growth with moderate risk"
  }'
```

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
