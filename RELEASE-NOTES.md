# FinHub release notes

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
