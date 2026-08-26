using System.Reflection;
using FinHub.Client.Models.AI;
using FinHub.Client.Models.Dividends;
using FinHub.Client.Models.Events;
using FinHub.Client.Schemas;
using FinHub.Client.Schemas.AIVendors;
using FinHub.Client.Schemas.DividendAnalysis;
using FinHub.Client.Schemas.Events;
using FinHub.Client.Schemas.MarketIndex;
using FinHub.Client.Schemas.NewListings;
using FinHub.Client.Schemas.PortfolioAnalysis;
using FinHub.Client.Schemas.PortfolioConstruction;
using FinHub.Client.Schemas.PortfolioSpotlight;
using FinHub.Client.Schemas.Stocks;
using FinHub.Client.Schemas.TickerAnalysis;

namespace FinHub.Client.Contracts.Tests;

internal enum ResponseEnvelopeKind
{
    Synchronous,
    Asynchronous,
    Raw,
}

internal sealed record EndpointContract(
    string Method,
    string Path,
    Type? RequestType,
    string? RequestComponent,
    bool RequestBodyRequired,
    Type ResponseType,
    string? ResponseComponent,
    ResponseEnvelopeKind EnvelopeKind
);

internal static class ContractMappings
{
    public static Assembly ContractsAssembly => typeof(ApiResponse<>).Assembly;

    // FastAPI's framework validation payloads are outside this contracts-only client.
    public static IReadOnlySet<string> IgnoredOpenApiComponents { get; } =
        new HashSet<string>(StringComparer.Ordinal)
        {
            "HTTPValidationError",
            "ValidationError",
        };

    public static IReadOnlyDictionary<string, Type> SpecialComponentMappings { get; } =
        new Dictionary<string, Type>(StringComparer.Ordinal)
        {
            ["AIVendorsResponse"] = typeof(GetAIVendorsResponse),
            ["BaseResponse"] = typeof(GetSymbolInfoDebugResponse),
            ["DividendEvidenceClaim"] = typeof(EvidenceClaim),
            ["DividendEvidenceSection"] = typeof(EvidenceSection),
            ["IndexCompaniesResponse"] = typeof(GetIndexCompaniesResponse),
            ["ListingEvidenceClaim"] = typeof(EvidenceClaim),
            ["ListingsAsyncResponse"] = typeof(GetNewListingsAsyncResponse),
            ["ListingsResponse"] = typeof(GetNewListingsResponse),
            ["PreciousMetalHistoryResponse"] = typeof(GetStockHistoryResponse),
            ["PreciousMetalQuoteResponse"] = typeof(GetStockQuoteResponse),
            ["StockHistoryResponse"] = typeof(GetStockHistoryResponse),
            ["StockQuoteAtDateResponse"] = typeof(GetStockQuoteAtDateResponse),
            ["StockQuotesResponse"] = typeof(GetStockQuotesResponse),
            ["SymbolInfoResponse"] = typeof(GetSymbolInfoResponse),
            ["SymbolOverviewResponse"] = typeof(GetSymbolOverviewResponse),
            ["TickerEvidenceClaim"] = typeof(EvidenceClaim),
            ["UpcomingDividendsAsyncResponse"] =
                typeof(GetUpcomingDividendsAsyncResponse),
            ["UpcomingDividendsResponse"] = typeof(GetUpcomingDividendsResponse),
            ["UpcomingEarningsAsyncResponse"] =
                typeof(GetUpcomingEarningsAsyncResponse),
            ["UpcomingEarningsResponse"] = typeof(GetUpcomingEarningsResponse),
            ["app__models__event__DividendEventAnalysis"] =
                typeof(DividendEventMetrics),
            ["app__models__events_dividends__DividendEventAnalysis"] =
                typeof(DividendEventAnalysis),
        };

    public static IReadOnlyList<EndpointContract> Endpoints { get; } =
    [
        new(
            "GET",
            "/ai/vendors",
            null,
            null,
            false,
            typeof(GetAIVendorsResponse),
            "AIVendorsResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "POST",
            "/ai/analyze_dividend_event",
            typeof(AnalyzeDividendEventRequest),
            "AnalyzeDividendEventRequest",
            true,
            typeof(AnalyzeDividendEventResponse),
            "AnalyzeDividendEventResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "POST",
            "/ai/analyze_dividend_event_async",
            typeof(AnalyzeDividendEventRequest),
            "AnalyzeDividendEventRequest",
            false,
            typeof(AnalyzeDividendEventAsyncResponse),
            "AnalyzeDividendEventAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "POST",
            "/ai/build_portfolio",
            typeof(BuildPortfolioRequest),
            "BuildPortfolioRequest",
            true,
            typeof(BuildPortfolioResponse),
            "BuildPortfolioResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "POST",
            "/ai/build_portfolio_async",
            typeof(BuildPortfolioRequest),
            "BuildPortfolioRequest",
            false,
            typeof(BuildPortfolioAsyncResponse),
            "BuildPortfolioAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "POST",
            "/ai/analyze_portfolio",
            typeof(AnalyzePortfolioRequest),
            "AnalyzePortfolioRequest",
            true,
            typeof(AnalyzePortfolioResponse),
            "AnalyzePortfolioResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "POST",
            "/ai/analyze_portfolio_async",
            typeof(AnalyzePortfolioRequest),
            "AnalyzePortfolioRequest",
            false,
            typeof(AnalyzePortfolioAsyncResponse),
            "AnalyzePortfolioAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "POST",
            "/ai/spotlight_portfolio",
            typeof(PortfolioSpotlightRequest),
            "PortfolioSpotlightRequest",
            true,
            typeof(PortfolioSpotlightResponse),
            "PortfolioSpotlightResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "POST",
            "/ai/spotlight_portfolio_async",
            typeof(PortfolioSpotlightRequest),
            "PortfolioSpotlightRequest",
            false,
            typeof(PortfolioSpotlightAsyncResponse),
            "PortfolioSpotlightAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "POST",
            "/ai/analyze_ticker",
            typeof(AnalyzeTickerRequest),
            "AnalyzeTickerRequest",
            true,
            typeof(AnalyzeTickerResponse),
            "AnalyzeTickerResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "POST",
            "/ai/analyze_ticker_async",
            typeof(AnalyzeTickerRequest),
            "AnalyzeTickerRequest",
            false,
            typeof(AnalyzeTickerAsyncResponse),
            "AnalyzeTickerAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "GET",
            "/events/upcoming_dividends",
            null,
            null,
            false,
            typeof(GetUpcomingDividendsResponse),
            "UpcomingDividendsResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/events/upcoming_dividends_async",
            null,
            null,
            false,
            typeof(GetUpcomingDividendsAsyncResponse),
            "UpcomingDividendsAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "GET",
            "/events/upcoming_earnings",
            null,
            null,
            false,
            typeof(GetUpcomingEarningsResponse),
            "UpcomingEarningsResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/events/upcoming_earnings_async",
            null,
            null,
            false,
            typeof(GetUpcomingEarningsAsyncResponse),
            "UpcomingEarningsAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "GET",
            "/events/new_listings",
            null,
            null,
            false,
            typeof(GetNewListingsResponse),
            "ListingsResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/events/new_listings_async",
            null,
            null,
            false,
            typeof(GetNewListingsAsyncResponse),
            "ListingsAsyncResponse",
            ResponseEnvelopeKind.Asynchronous
        ),
        new(
            "GET",
            "/stocks/quotes",
            null,
            null,
            false,
            typeof(GetStockQuotesResponse),
            "StockQuotesResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/stocks/{symbol}/overview",
            null,
            null,
            false,
            typeof(GetSymbolOverviewResponse),
            "SymbolOverviewResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/stocks/{symbol}/info",
            null,
            null,
            false,
            typeof(GetSymbolInfoResponse),
            "SymbolInfoResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/stocks/{symbol}/history",
            null,
            null,
            false,
            typeof(GetStockHistoryResponse),
            "StockHistoryResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/stocks/{symbol}/quote_at/{date_str}",
            null,
            null,
            false,
            typeof(GetStockQuoteAtDateResponse),
            "StockQuoteAtDateResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/stocks/{symbol}/info_debug",
            null,
            null,
            false,
            typeof(GetSymbolInfoDebugResponse),
            "BaseResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/stocks/index/{index}/companies",
            null,
            null,
            false,
            typeof(GetIndexCompaniesResponse),
            "IndexCompaniesResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/toz/gold/quote",
            null,
            null,
            false,
            typeof(GetStockQuoteResponse),
            "PreciousMetalQuoteResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/toz/gold/history",
            null,
            null,
            false,
            typeof(GetStockHistoryResponse),
            "PreciousMetalHistoryResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/toz/silver/quote",
            null,
            null,
            false,
            typeof(GetStockQuoteResponse),
            "PreciousMetalQuoteResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/toz/silver/history",
            null,
            null,
            false,
            typeof(GetStockHistoryResponse),
            "PreciousMetalHistoryResponse",
            ResponseEnvelopeKind.Synchronous
        ),
        new(
            "GET",
            "/market/index/{index_id}",
            null,
            null,
            false,
            typeof(GetMarketIndexResponse),
            null,
            ResponseEnvelopeKind.Raw
        ),
    ];

    private static IReadOnlyDictionary<string, Type[]> ContractTypesByName { get; } =
        ContractsAssembly
            .GetExportedTypes()
            .GroupBy(type => type.Name, StringComparer.Ordinal)
            .ToDictionary(
                group => group.Key,
                group => group.ToArray(),
                StringComparer.Ordinal
            );

    public static bool TryResolveComponentType(string componentName, out Type? type)
    {
        if (SpecialComponentMappings.TryGetValue(componentName, out type))
        {
            return true;
        }

        if (
            ContractTypesByName.TryGetValue(componentName, out var candidates)
            && candidates.Length == 1
        )
        {
            type = candidates[0];
            return true;
        }

        type = null;
        return false;
    }

    public static Type ResolveComponentType(string componentName)
    {
        if (TryResolveComponentType(componentName, out var type))
        {
            return type!;
        }

        throw new InvalidOperationException(
            $"OpenAPI component '{componentName}' has no unambiguous .NET contract mapping."
        );
    }
}
