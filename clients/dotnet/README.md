# FinHub .NET contracts

This .NET 8 class library contains models and response schemas only. It does not implement HTTP transport.

```http
GET /events/new_listings
```

Deserialize a new-listings response with `System.Text.Json`:

```csharp
using System.Text.Json;
using FinHub.Client.Schemas.NewListings;

var response = JsonSerializer.Deserialize<GetNewListingsResponse>(json);
```

Nullable response properties may be absent because the API excludes `null` values. `ListingEvent.Date` and
`ListingEvent.PublicOfferCloseDate` remain strings to match the current OpenAPI contract; formatted analysis dates use
`DateOnly` or `DateTimeOffset`.

## Contract namespaces

- `FinHub.Client.Models.AI`: reusable AI contracts such as reference sources.
- `FinHub.Client.Models.Events`: reusable event contracts.
- `FinHub.Client.Models.Listings`: listing-domain contracts shared by listing APIs.
- `FinHub.Client.Schemas`: reusable API response envelopes.
- `FinHub.Client.Schemas.NewListings`: schemas specific to the new-listings API.
