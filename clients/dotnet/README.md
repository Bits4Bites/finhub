# FinHub .NET contracts

This .NET 8 class library contains models and response schemas only. It does not implement HTTP transport.

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
GET /ai/analyze_dividend_event_async/{task_id}
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
reusable `AsyncTaskInfo`/`TaskState` metadata.

## Contract namespaces

- `FinHub.Client.Models.AI`: reusable AI contracts such as reference sources.
- `FinHub.Client.Models.Dividends`: reusable dividend-event analysis domain contracts.
- `FinHub.Client.Models.Events`: reusable event contracts.
- `FinHub.Client.Models.Listings`: listing-domain contracts shared by listing APIs.
- `FinHub.Client.Schemas`: reusable API response envelopes and async task metadata.
- `FinHub.Client.Schemas.DividendAnalysis`: request and response schemas for dividend-event analysis.
- `FinHub.Client.Schemas.NewListings`: schemas specific to the new-listings API.
