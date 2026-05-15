# FinHub release notes

## 2026-05-15 - v0.9.0

### Added/Refactoring/Deprecation

- (Feat) Client can now specify a custom provider/model when making requests, overriding the default settings.
- (Feat) New API /ai/vendors to list available AI vendors and supported API tiers and models.

### Fixed/Improvements

- (Impr) Update AI client configurations with updated list of models and providers.
- (Fix) Correctly redirect to next instance in proxy mode.
- (Fix) Fix API response for /ai/analyze_portfolio/
- (Impr) Review and Improve/Optimize prompt templates.

## 2026-05-12 - v0.8.0

### Added/Refactoring/Deprecation

- (Feat) API /ai/analyze_portfolio can be used to build new portfolio.

## 2026-05-07 - v0.7.2

### Fixed/Improvements

- (Patch) Refactor & Fix error 401 with AzureOpenAI client.

## 2026-05-06 - v0.7.1

### Fixed/Improvements

- (Fix) API /ai/analyze_portfolio outputs invalid fields.

## 2026-05-06 - v0.7.0

### Added/Refactoring/Deprecation

- (Feat) New API to analyze portfolio.

## 2026-05-05 - v0.6.4

### Fixed/Improvements

- (Fix) Edge case where a ticker has recently listed and has no price history.

## 2026-04-29 - v0.6.3

### Fixed/Improvements

- (Patch) Fix CodeQL warnings.
- (Impr) Added field asset_type to SymbolOverview

## 2026-04-23 - v0.6.2

### Fixed/Improvements

- (Impr) Add payout_frequency field to SymbolDividend.

## 2026-04-17 - v0.6.1

### Fixed/Improvements

- (Patch) Authenticate AzureOpenAI with SP

## 2026-04-12 - v0.6.0

### Added/Refactoring/Deprecation

- (Feat) Add OpenRouter client
- (Feat) Add APIs to return list of companies in an index
- (Feat) Add new API to analyze a dividend event
- (Feat) Add proxy mode
- (Refactor) Move event APIs to a new endpoint /events

### Fixed/Improvements

- (Impr) Cache AU market indexes locally (ASX20, ASX50, ASX100, ASX200, ASX300)
- (Impr) Cache VN market indexes locally (VN30, VN100, HNX30)
- (Impr) Cache US market indexes locally (NASDAQ100, SP500, SP400, SP600)
- (Impr) Add event analysis to API /events/new_listings
- (Patch) Code cleanup

## 2026-03-14 - v0.5.1

### Fixed/Improvements

- (Fix) Fix stock symbol to EXCHANGE:CODE format.

## 2026-03-14 - v0.5.0

### Added/Refactoring/Deprecation

- (Feat) APIs to get Gold/Silver price.

## 2026-03-13 - v0.4.0

### Added/Refactoring/Deprecation

- (Feat) New API to fetch stock quote at a given date.

### Fixed/Improvements

- (Patch) Set auto_adjust=False when fetching ticker history.
- (Patch) Return dividend info in stock history.
- (Patch) Improve responses with datetime fields.
- (Improvement) APIs to fetch upcoming events use LLM only when necessary.

## 2026-03-09 - v0.3.3

### Fixed/Improvements

- (Patch) start_date = current_date - 2 when scraping dividend events.

## 2026-03-09 - v0.3.2

### Fixed/Improvements

- (Patch) Specify User Agent when fetching website content.
- (Patch) Update date range when fetching dividend data.

## 2026-03-06 - v0.3.1

### Fixed/Improvements

- (Patch) Update API endpoints with better naming conventions.

## 2026-03-05 - v0.3.0

### Added/Refactoring/Deprecation

- (Feat) Scrape VN dividend data from VietStock.
- (Feat) Scrape new listings from ASX.

### Fixed/Improvements

- (Fix) Using Playwright async on Windows with uvicorn reload enabled.
- (Patch) Optimize tokens used scraping dividend/distribution/earnings events.

## 2026-03-03 - v0.2.0

### Added/Refactoring/Deprecation

- (Feat) Scrape AU/US dividend data from TipRanks.
- (Feat) Scrape AU/US earnings data from TipRanks.

## 2026-02-26 - v0.1.3

### Fixed/Improvements

- (Patch) Fix typo.

## 2026-02-26 - v0.1.2

### Fixed/Improvements

- (Patch) Fix incoming dividends model fields.
- (Patch) Accept variants of country codes/names.

## 2026-02-25 - v0.1.1

### Fixed/Improvements

- (Patch) Refactor & Optimize AI-assisted function to get incoming events.

## 2026-02-23 - v0.1.0

### Added/Refactoring/Deprecation

- (Feat) AI-assisted to check incoming earnings/dividend/distribution events for markets AU/US/VN.

## 2026-02-16 - v0.0.7

### Fixed/Improvements

- (Patch) Increase history data to 90 days.

## 2026-02-16 - v0.0.6

### Fixed/Improvements

- (Patch) Add 30 days history to StockHistory.

## 2026-02-12 - v0.0.5

### Fixed/Improvements

- (Patch) Add field yesterday_volume to StockHistory.
- (Patch) Temporarily remove field rsi14_history_daily from StockHistory.

## 2026-02-12 - v0.0.4

### Added/Refactoring/Deprecation

- (Feat) Add API to return overview info of a symbol.

## 2026-02-11 - v0.0.3

### Added/Refactoring/Deprecation

- (Feat) Add Stock history info.

## 2026-02-10 - v0.0.2

### Added/Refactoring/Deprecation

- (Feat) Add API to get stock symbol info.
- (Feat) Add dividend info.

## 2026-02-06 - v0.0.1

### Added/Refactoring/Deprecation

- (Feat) API to fetch stock quotes for a given list of stock symbols.
