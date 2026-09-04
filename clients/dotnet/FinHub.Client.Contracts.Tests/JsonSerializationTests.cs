using System.Text.Json;
using FinHub.Client.Models.AI;
using FinHub.Client.Models.Events;
using FinHub.Client.Models.Listings;
using FinHub.Client.Models.Portfolios;
using FinHub.Client.Models.Stocks;
using FinHub.Client.Models.Tickers;
using FinHub.Client.Schemas;
using FinHub.Client.Schemas.AIVendors;
using FinHub.Client.Schemas.DividendAnalysis;
using FinHub.Client.Schemas.MarketIndex;
using FinHub.Client.Schemas.Stocks;
using FinHub.Client.Schemas.TickerAnalysis;
using MyPo.Shared.Api;
using Xunit;

namespace FinHub.Client.Contracts.Tests;

public sealed class JsonSerializationTests
{
    [Fact]
    public void Optional_non_nullable_vendor_data_uses_its_OpenAPI_default()
    {
        const string json = """{"status":200,"message":"OK"}""";

        var response = JsonSerializer.Deserialize<GetAIVendorsResponse>(json);

        Assert.NotNull(response);
        Assert.IsAssignableFrom<ApiResp<IReadOnlyDictionary<string, AIVendorInfo>>>(
            response
        );
        Assert.Empty(response.Data);
    }

    [Fact]
    public void Synchronous_response_uses_the_shared_untyped_extra_contract()
    {
        const string json =
            """
            {
              "status": 200,
              "message": "OK",
              "extra": {
                "source": "cache"
              }
            }
            """;

        var response = JsonSerializer.Deserialize<GetStockQuoteResponse>(json);

        Assert.NotNull(response);
        Assert.IsType<JsonElement>(response.Extra);
        Assert.Equal(
            "cache",
            response.ExtraAs<Dictionary<string, string>>()?["source"]
        );
    }

    [Fact]
    public void Async_response_deserializes_required_task_metadata()
    {
        const string json =
            """
            {
              "status": 202,
              "message": "Task started.",
              "extra": {
                "task_id": "task-123",
                "state": "RUNNING"
              }
            }
            """;

        var response = JsonSerializer.Deserialize<AnalyzeTickerAsyncResponse>(json);

        Assert.NotNull(response);
        Assert.Equal(202, response.Status);
        Assert.Null(response.Data);
        Assert.Equal("task-123", response.Extra.TaskId);
        Assert.Equal(TaskState.Running, response.Extra.State);

        var sharedResponse = Assert.IsAssignableFrom<ApiResp>(response);
        Assert.Same(response.Extra, sharedResponse.Extra);
        Assert.Equal("task-123", response.ExtraAs<AsyncTaskInfo>()?.TaskId);

        using var serialized = JsonDocument.Parse(JsonSerializer.Serialize(response));
        Assert.Single(
            serialized.RootElement.EnumerateObject(),
            property => property.NameEquals("extra")
        );
    }

    [Fact]
    public void Required_listing_members_accept_nullable_values_but_not_omission()
    {
        const string withNulls =
            """
            {
              "symbol": "ASX:TEST",
              "timestamp_str": "2026-09-01",
              "issue_price": null,
              "currency": "AUD",
              "capital_to_raise": null
            }
            """;
        const string missingTimestampStr =
            """
            {
              "symbol": "ASX:TEST",
              "issue_price": null,
              "currency": "AUD",
              "capital_to_raise": null
            }
            """;
        const string missingIssuePrice =
            """
            {
              "symbol": "ASX:TEST",
              "timestamp_str": "2026-09-01",
              "currency": "AUD",
              "capital_to_raise": null
            }
            """;
        const string missingCapitalToRaise =
            """
            {
              "symbol": "ASX:TEST",
              "timestamp_str": "2026-09-01",
              "issue_price": null,
              "currency": "AUD"
            }
            """;

        var listing = JsonSerializer.Deserialize<ListingEvent>(withNulls);

        Assert.NotNull(listing);
        Assert.Equal("2026-09-01", listing.TimestampStr);
        Assert.Null(listing.IssuePrice);
        Assert.Null(listing.CapitalToRaise);
        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<ListingEvent>(missingTimestampStr)
        );
        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<ListingEvent>(missingIssuePrice)
        );
        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<ListingEvent>(missingCapitalToRaise)
        );
    }

    [Fact]
    public void Event_DateUTC_parses_timestamp_str_and_normalizes_to_UTC()
    {
        const string json =
            """
            {
              "symbol": "NASDAQ:TEST",
              "timestamp": 0,
              "timestamp_str": "2026-09-01T10:30:00+10:00"
            }
            """;

        var marketEvent = JsonSerializer.Deserialize<UpcomingEarningsEvent>(json);

        Assert.NotNull(marketEvent);
        Assert.Equal(
            new DateTimeOffset(2026, 9, 1, 0, 30, 0, TimeSpan.Zero),
            marketEvent.DateUTC
        );
        Assert.Equal(TimeSpan.Zero, marketEvent.DateUTC.Offset);
    }

    [Fact]
    public void Event_requires_timestamp_str_and_DateUTC_falls_back_to_timestamp_when_invalid()
    {
        const long timestamp = 1_725_148_800;
        const string withoutTimestampStr =
            """{"symbol":"NASDAQ:TEST","timestamp":1725148800}""";
        const string withInvalidTimestampStr =
            """
            {
              "symbol": "NASDAQ:TEST",
              "timestamp": 1725148800,
              "timestamp_str": "not-a-timestamp"
            }
            """;

        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<UpcomingEarningsEvent>(withoutTimestampStr)
        );
        var withInvalidString = JsonSerializer.Deserialize<UpcomingEarningsEvent>(
            withInvalidTimestampStr
        );
        var expected = DateTimeOffset.FromUnixTimeSeconds(timestamp).ToUniversalTime();

        Assert.NotNull(withInvalidString);
        Assert.Equal(expected, withInvalidString.DateUTC);
        Assert.Equal(TimeSpan.Zero, withInvalidString.DateUTC.Offset);
    }

    [Fact]
    public void Date_and_int64_contract_choices_deserialize_without_narrowing()
    {
        const string requestJson =
            """
            {
              "symbol": "NASDAQ:AAPL",
              "ex_date": "2026-08-10",
              "dividend_amount": 0.26
            }
            """;
        const string historyJson =
            """
            {
              "timestamp": 5000000000,
              "timestamp_str": "2128-06-11T08:53:20Z",
              "volume": 4000000000
            }
            """;

        var request = JsonSerializer.Deserialize<AnalyzeDividendEventRequest>(requestJson);
        var history = JsonSerializer.Deserialize<HistoryPoint>(historyJson);

        Assert.NotNull(request);
        Assert.Equal(new DateOnly(2026, 8, 10), request.ExDate);
        Assert.NotNull(history);
        Assert.Equal(5_000_000_000L, history.Timestamp);
        Assert.Equal(4_000_000_000L, history.Volume);
    }

    [Fact]
    public void Non_identifier_enum_values_use_their_exact_wire_literals()
    {
        var assetType = JsonSerializer.Deserialize<TickerAssetType>("\"MUTUAL FUND\"");
        var listingHorizon = JsonSerializer.Deserialize<ListingHorizon>("\"IPO Day\"");
        var rebalance = JsonSerializer.Deserialize<PortfolioSpotlightRebalanceFlag>(
            "\"YES\""
        );

        Assert.Equal(TickerAssetType.MutualFund, assetType);
        Assert.Equal("\"MUTUAL FUND\"", JsonSerializer.Serialize(assetType));
        Assert.Equal(ListingHorizon.IpoDay, listingHorizon);
        Assert.Equal("\"IPO Day\"", JsonSerializer.Serialize(listingHorizon));
        Assert.Equal(PortfolioSpotlightRebalanceFlag.Yes, rebalance);
        Assert.Equal("\"YES\"", JsonSerializer.Serialize(rebalance));
        Assert.Throws<JsonException>(
            () => JsonSerializer.Deserialize<TickerAssetType>("\"FUTURE_TYPE\"")
        );
    }

    [Fact]
    public void Portfolio_union_converter_uses_the_OpenAPI_discriminator()
    {
        const string json =
            """
            {
              "result_type": "PortfolioConstruction",
              "as_of": "2026-08-25T10:00:00Z",
              "construction_status": "Complete",
              "construction_mode": "Scratch",
              "country": "US",
              "investor_theme": "Durable growth",
              "summary": "Diversified target allocation.",
              "verified_seed_holdings": [],
              "target_portfolio": [],
              "action_plan": null,
              "overall_data_quality": "High",
              "data_gaps": [],
              "validation_warnings": [],
              "references": []
            }
            """;

        var result = JsonSerializer.Deserialize<IPortfolioAnalysisResult>(json);

        var construction = Assert.IsType<PortfolioConstruction>(result);
        Assert.Equal("PortfolioConstruction", construction.ResultType);
        Assert.Throws<JsonException>(
            () =>
                JsonSerializer.Deserialize<IPortfolioAnalysisResult>(
                    """{"result_type":"UnknownResult"}"""
                )
        );
    }

    [Fact]
    public void Every_checked_in_market_index_payload_deserializes_as_the_raw_contract()
    {
        var directory = Path.Combine(AppContext.BaseDirectory, "TestData", "Indices");
        var files = Directory.GetFiles(directory, "*.json").Order(StringComparer.Ordinal).ToArray();

        Assert.NotEmpty(files);
        foreach (var file in files)
        {
            var response = JsonSerializer.Deserialize<GetMarketIndexResponse>(
                File.ReadAllText(file)
            );

            Assert.True(
                response is not null && response.Data.Count > 0,
                $"Raw market-index payload '{Path.GetFileName(file)}' did not deserialize."
            );
        }
    }
}
