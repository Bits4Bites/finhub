# FinHub .NET contracts

This .NET 8 class library contains models and response schemas only. It does not implement HTTP transport.

## Restore, build, and test

From the repository root with the .NET 8 SDK installed:

```text
dotnet restore clients/dotnet/FinHub.Client.Contracts.Tests/FinHub.Client.Contracts.Tests.csproj
dotnet build clients/dotnet/FinHub.Client.Contracts.Tests/FinHub.Client.Contracts.Tests.csproj --configuration Release --no-restore --warnaserror
dotnet test clients/dotnet/FinHub.Client.Contracts.Tests/FinHub.Client.Contracts.Tests.csproj --configuration Release --no-build --no-restore
```

Building the test project builds its reference to `FinHub.Client.Contracts.csproj`, so the contracts are not built
twice. The tests use the repository-root `openapi.json` as their authority. They map all 29 public router operations
to request and response contracts, compare every client component's JSON names, requiredness, nullability, types,
integer widths, string formats, and enum wire values, and exercise non-obvious converters and raw market-index
payloads. The root and health operations remain intentionally outside the client contract surface.

## AI vendors

Vendor discovery covers:

```http
GET /ai/vendors
```

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.AIVendors;

var response = JsonSerializer.Deserialize<GetAIVendorsResponse>(json);
```

`Data` is keyed by vendor identifier, and each vendor maps tier identifiers to model-name lists. Only configured
entries are returned; vendor and tier keys are normalized to uppercase. When omitted, `Data` defaults to an empty
dictionary, matching the OpenAPI default.

## Market indices

Static market-index snapshots cover:

```http
GET /market/index/{index_id}
```

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.MarketIndex;

var response = JsonSerializer.Deserialize<GetMarketIndexResponse>(json);
```

`GetMarketIndexResponse` is a direct response and does not derive from `ApiResponse<TData>`. Its snapshot `Date` is a
`DateOnly`; constituents expose nullable `Sector` and `MarketCap` fields because the cached index families use
different source shapes. Market capitalization is represented as a nullable `long`.

## Stocks

Stock contracts cover:

```http
GET /stocks/quotes
GET /stocks/{symbol}/overview
GET /stocks/{symbol}/info
GET /stocks/{symbol}/history
GET /stocks/{symbol}/quote_at/{date_str}
GET /stocks/{symbol}/info_debug
GET /stocks/index/{index}/companies
```

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.Stocks;

var quotes = JsonSerializer.Deserialize<GetStockQuotesResponse>(quotesJson);
var info = JsonSerializer.Deserialize<GetSymbolInfoResponse>(infoJson);
```

`GetStockQuotesResponse.Data` is keyed by requested symbol. The overview and info contracts reuse
`TickerAssetType` because its strict wire values exactly match the stock API's asset classification. Market
capitalization, financial totals, volumes, and Unix timestamps use `long`; unformatted timestamp display values
remain strings. Optional fields preserve their OpenAPI nullability and defaults. `GetSymbolInfoDebugResponse.Data`
is a nullable `JsonElement` because that debug payload is intentionally unstructured.

## Precious metals

Gold and silver endpoints reuse the stock quote and history contracts:

```http
GET /toz/gold/quote
GET /toz/gold/history
GET /toz/silver/quote
GET /toz/silver/history
```

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.Stocks;

var goldQuote = JsonSerializer.Deserialize<GetStockQuoteResponse>(goldJson);
var silverHistory = JsonSerializer.Deserialize<GetStockHistoryResponse>(silverJson);
```

Both quote endpoints use `GetStockQuoteResponse`; both history endpoints use `GetStockHistoryResponse`. The optional
`currency` query defaults to `USD`, and the history endpoints' optional `days` query defaults to `30`.

## Upcoming market events

Upcoming dividend and earnings contracts cover:

```http
GET /events/upcoming_dividends
GET /events/upcoming_dividends_async
GET /events/upcoming_earnings
GET /events/upcoming_earnings_async
```

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.Events;

var dividends = JsonSerializer.Deserialize<GetUpcomingDividendsResponse>(dividendsJson);
var asyncEarnings = JsonSerializer.Deserialize<GetUpcomingEarningsAsyncResponse>(asyncEarningsJson);
```

Synchronous calls use `GetUpcomingDividendsResponse` or `GetUpcomingEarningsResponse`. Start an async task with
`country` and optional `index`, then poll the same endpoint with `task_id=<TASK_ID>`; each endpoint has its own async
response type. Start and running responses use HTTP `202`, completed polls can contain the event collection in
`Data`, and failed polls use HTTP `500`. Async responses require the shared `AsyncTaskInfo` metadata and strict
`TaskState`; cached tasks expire after one hour.

`EventBase.Date`, dividend `PaymentDate`, and earnings `ReportPeriod` remain strings because OpenAPI does not assign
date formats. `UpcomingDividendEvent.PaymentDate` is required but nullable. Unix timestamps, traded-value metrics,
and volume metrics use `long`; sample counts, recovery-day ranges, and `Rsi14` use `int`.

An upcoming dividend can contain nullable `DividendEventMetrics` in its `Analysis` property. This Events-domain type
contains only the current event identity, historical recovery, and technical metrics. It is intentionally distinct
from `FinHub.Client.Models.Dividends.DividendEventAnalysis` and excludes the removed AI error, search, strategy,
reasoning, sentiment, adjusted-forecast, expected-profit/loss, confidence, and risk fields.

## New listings

The new-listings contracts cover:

```http
GET /events/new_listings
GET /events/new_listings_async
```

Deserialize synchronous and async start/poll responses with `System.Text.Json`:

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.NewListings;

var response = JsonSerializer.Deserialize<GetNewListingsResponse>(json);
var asyncResponse = JsonSerializer.Deserialize<GetNewListingsAsyncResponse>(asyncJson);
```

Call `GET /events/new_listings_async?country=AU` to start a task and poll the same endpoint with
`task_id=<TASK_ID>`. Both operations deserialize as `GetNewListingsAsyncResponse`; its required `Extra` property uses
the shared `AsyncTaskInfo` and `TaskState` contracts. Completed polls can include the standard listing collection in
`Data`.

Nullable response properties may be absent because the API excludes `null` values. OpenAPI marks
`ListingEvent.IssuePrice` and `ListingEvent.CapitalToRaise` as required but nullable. `ListingEvent.Date` and
`ListingEvent.PublicOfferCloseDate` remain strings to match the current OpenAPI contract; formatted analysis dates use
`DateOnly` or `DateTimeOffset`.

## Dividend-event analysis

The dividend-analysis contracts cover:

```http
POST /ai/analyze_dividend_event
POST /ai/analyze_dividend_event_async
```

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.DividendAnalysis;

var request = new AnalyzeDividendEventRequest
{
    Symbol = "NASDAQ:AAPL",
    ExDate = new DateOnly(2026, 8, 10),
    DividendAmount = 0.26,
};

var response = JsonSerializer.Deserialize<AnalyzeDividendEventAsyncResponse>(json);
```

`TransactionCosts` defaults both per-share costs to zero, and `HoldingPeriodDays` defaults to 28. Synchronous results
use `AnalyzeDividendEventResponse`; async start and poll responses share `AnalyzeDividendEventAsyncResponse` and
reusable `AsyncTaskInfo`/`TaskState` metadata. Poll with
`POST /ai/analyze_dividend_event_async?task_id=<TASK_ID>`.

## Ticker analysis

The ticker-analysis contracts cover:

```http
POST /ai/analyze_ticker
POST /ai/analyze_ticker_async
```

```csharp
using FinHub.Client.Schemas.TickerAnalysis;

var request = new AnalyzeTickerRequest
{
    Symbol = "NASDAQ:AAPL",
    CurrentHolding = new TickerHoldingInput
    {
        NumShares = 10,
        AvgPrice = 150.0,
    },
};
```

Results contain a verified market snapshot, an optional holding snapshot, source-linked research, exactly four fixed
forecast horizons, and a holding-aware recommendation. `TickerAssetType` and `TickerRecommendationAction` use strict
converters for their exact wire values, including `MUTUAL FUND` and `BUY`. Unformatted OpenAPI integer fields for
market volume and capitalization use `long` to accommodate real market values. Synchronous calls use
`AnalyzeTickerResponse`; async start and poll calls use `AnalyzeTickerAsyncResponse` with shared task metadata.

## Portfolio construction and analysis

The construction contracts cover:

```http
POST /ai/build_portfolio
POST /ai/build_portfolio_async
```

```csharp
using FinHub.Client.Models.Portfolios;
using FinHub.Client.Schemas.PortfolioConstruction;

var request = new BuildPortfolioRequest
{
    Country = "US",
    InvestorTheme = "Durable growth with moderate risk.",
    CurrentAllocation =
    [
        new PortfolioHolding
        {
            Ticker = "NASDAQ:AAPL",
            NumShares = 10,
            AvgPrice = 150.0,
        },
    ],
};
```

`InvestorTheme` is required and `CurrentAllocation` defaults to an empty collection. The result is one
`PortfolioConstruction` with `Scratch` or `Seeded` mode, verified positive seed holdings, allocation-only target
positions, an optional budget-aware action plan, data-quality metadata, canonical references, and the
`PortfolioConstruction` result discriminator. Synchronous calls use `BuildPortfolioResponse`; async start and
query-poll calls use `BuildPortfolioAsyncResponse`.

Nullable budget details and nullable enriched holding values remain required members where OpenAPI requires their
presence; a JSON `null` is distinct from an omitted property.

The dispatcher endpoints:

```http
POST /ai/analyze_portfolio
POST /ai/analyze_portfolio_async
```

use `AnalyzePortfolioResponse` and `AnalyzePortfolioAsyncResponse`. Their `Data` property is
`IPortfolioAnalysisResult`: the included JSON converter requires `result_type` and explicitly selects
`PortfolioConstruction` or `PortfolioReview`. Structured reviews include the verified snapshot, budget, strengths,
risks, per-holding recommendations, target portfolio, rebalance decision, optional action plan, data-quality
metadata, and canonical references. `AnalyzePortfolioRequest.InvestorTheme` is required,
`CurrentAllocation` defaults to an empty collection, and `RebalancePlan` defaults to `false`.

## Portfolio spotlight

The portfolio-spotlight contracts cover:

```http
POST /ai/spotlight_portfolio
POST /ai/spotlight_portfolio_async
```

```csharp
using FinHub.Client.Models.Portfolios;
using FinHub.Client.Schemas.PortfolioSpotlight;

var request = new PortfolioSpotlightRequest
{
    Country = "AU",
    CurrentAllocation =
    [
        new PortfolioHolding
        {
            Ticker = "CBA.AX",
            NumShares = 10,
            AvgPrice = 150.0,
            TargetAllocation = 1.0,
        },
    ],
};
```

The synchronous endpoint uses `PortfolioSpotlightResponse`. Async start and poll calls both use
`PortfolioSpotlightAsyncResponse` with shared `AsyncTaskInfo`/`TaskState` metadata. Results contain verified holdings
through the reusable `PortfolioVerifiedHolding` contract and up to four structured risk actions. `InvestorTheme` is
optional and has no client default. Risk levels are limited to `Critical`, `High`, and `Medium`;
`PortfolioSpotlightRebalanceFlag` strictly maps the wire values `YES` and `NO`.

## Contract namespaces

- `FinHub.Client.Models.AI`: reusable AI contracts for vendor discovery, data quality, evidence, and reference sources.
- `FinHub.Client.Models.Dividends`: reusable dividend-event analysis domain contracts.
- `FinHub.Client.Models.Events`: reusable event contracts.
- `FinHub.Client.Models.Listings`: listing-domain contracts shared by listing APIs.
- `FinHub.Client.Models.Markets`: reusable market-index constituent contracts.
- `FinHub.Client.Models.Portfolios`: reusable holdings, construction, analysis-union, snapshot, risk, and spotlight contracts.
- `FinHub.Client.Models.Stocks`: reusable quote, history, symbol-profile, dividend, and index-company contracts.
- `FinHub.Client.Models.Tickers`: reusable ticker research, forecast, market snapshot, and recommendation contracts.
- `FinHub.Client.Schemas`: reusable synchronous/async API response envelopes and async task metadata.
- `FinHub.Client.Schemas.AIVendors`: response schemas for AI vendor discovery.
- `FinHub.Client.Schemas.DividendAnalysis`: request and response schemas for dividend-event analysis.
- `FinHub.Client.Schemas.Events`: response schemas for upcoming dividend and earnings events.
- `FinHub.Client.Schemas.MarketIndex`: direct response schemas for cached market-index snapshots.
- `FinHub.Client.Schemas.NewListings`: schemas specific to the new-listings API.
- `FinHub.Client.Schemas.PortfolioAnalysis`: request and response schemas for the review-or-construction dispatcher.
- `FinHub.Client.Schemas.PortfolioConstruction`: request and response schemas for portfolio construction.
- `FinHub.Client.Schemas.PortfolioSpotlight`: request and response schemas for portfolio spotlight.
- `FinHub.Client.Schemas.Stocks`: stock responses, also reused by gold and silver quote/history endpoints.
- `FinHub.Client.Schemas.TickerAnalysis`: request and response schemas for ticker analysis.
