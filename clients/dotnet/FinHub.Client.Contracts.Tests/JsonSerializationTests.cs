using System.Text.Json;
using FinHub.Client.Models.AI;
using FinHub.Client.Models.Dividends;
using FinHub.Client.Models.Events;
using FinHub.Client.Models.Listings;
using FinHub.Client.Models.Portfolios;
using FinHub.Client.Models.Stocks;
using FinHub.Client.Models.Tickers;
using FinHub.Client.Schemas;
using FinHub.Client.Schemas.AIVendors;
using FinHub.Client.Schemas.DividendAnalysis;
using FinHub.Client.Schemas.Events;
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
    public void Async_response_preserves_task_metadata_without_duplicate_extra_fields()
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
    public void Completed_async_response_converts_without_losing_payload_or_metadata()
    {
        var earnings = new UpcomingEarningsEvent
        {
            Symbol = "NASDAQ:TEST",
            Timestamp = 1_725_148_800,
            TimestampStr = "2024-09-01T00:00:00Z",
            ReportPeriod = "Q3 2024",
        };
        var taskInfo = new AsyncTaskInfo
        {
            TaskId = "task-123",
            State = TaskState.Completed,
        };
        var debugInfo = new Dictionary<string, string>
        {
            ["trace_id"] = "trace-123",
        };
        var response = new GetUpcomingEarningsAsyncResponse
        {
            Status = 200,
            Message = "Task completed.",
            Data = [earnings],
            Extra = taskInfo,
            DebugInfo = debugInfo,
        };

        var synchronousResponse = response.ToApiResp();

        Assert.Equal(response.Status, synchronousResponse.Status);
        Assert.Equal(response.Message, synchronousResponse.Message);
        Assert.Same(response.Data, synchronousResponse.Data);
        Assert.Same(taskInfo, synchronousResponse.Extra);
        Assert.Same(debugInfo, synchronousResponse.DebugInfo);
    }

    [Fact]
    public void Upcoming_dividend_response_allows_an_omitted_payment_date()
    {
        const string json =
            """
            {
              "status": 200,
              "message": "ok",
              "data": [
                {
                  "symbol": "ASX:TEST",
                  "timestamp_str": "2026-11-20 00:00:00+11:00",
                  "amount": 1.25,
                  "currency": "AUD"
                }
              ]
            }
            """;

        var response = JsonSerializer.Deserialize<GetUpcomingDividendsResponse>(json);

        Assert.NotNull(response);
        Assert.NotNull(response.Data);
        Assert.Null(Assert.Single(response.Data).PaymentDate);
    }

    [Fact]
    public void Ineligible_dividend_strategy_allows_omitted_estimates()
    {
        const string json =
            """
            {
              "strategy": "DividendCapture",
              "eligibility": "Ineligible",
              "ineligibility_reason": "The ex-dividend date has passed.",
              "confidence": 80,
              "risk": 50,
              "rationale": "The strategy is no longer available.",
              "risk_factors": [],
              "assumptions": [],
              "data_gaps": [],
              "reference_ids": ["source-1"]
            }
            """;

        var assessment = JsonSerializer.Deserialize<DividendStrategyAssessment>(json);

        Assert.NotNull(assessment);
        Assert.Equal(DividendStrategyEligibility.Ineligible, assessment.Eligibility);
        Assert.Null(assessment.ExpectedEntryPrice);
        Assert.Null(assessment.RecoveryDays);
    }

    [Fact]
    public void Earnings_financial_fields_preserve_signed_EPS_and_large_whole_unit_amounts()
    {
        const string json =
            """
            {
              "symbol": "NASDAQ:TEST",
              "timestamp_str": "2026-11-20 00:00:00-05:00",
              "market_cap": 200000000000,
              "eps": -2.65,
              "eps_forecast": -2.08,
              "revenue": 27067000000,
              "revenue_forecast": 4001000000,
              "currency": "USD"
            }
            """;

        var earnings = JsonSerializer.Deserialize<UpcomingEarningsEvent>(json);

        Assert.NotNull(earnings);
        Assert.Equal(200_000_000_000L, earnings.MarketCap);
        Assert.Equal(-2.65m, earnings.Eps);
        Assert.Equal(-2.08m, earnings.EpsForecast);
        Assert.Equal(27_067_000_000L, earnings.Revenue);
        Assert.Equal(4_001_000_000L, earnings.RevenueForecast);
        Assert.Equal("USD", earnings.Currency);
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
    public void Event_DateUTC_falls_back_to_timestamp_when_timestamp_str_is_invalid()
    {
        const long timestamp = 1_725_148_800;
        const string withInvalidTimestampStr =
            """
            {
              "symbol": "NASDAQ:TEST",
              "timestamp": 1725148800,
              "timestamp_str": "not-a-timestamp"
            }
            """;

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
    public void Listing_event_supports_fixed_and_ranged_decimal_issue_prices()
    {
        const string rangedPriceJson =
            """
            {
              "symbol": "ASX:RANGE",
              "timestamp_str": "2026-11-16",
              "issue_price": 0.20,
              "issue_price_upper": 0.25,
              "currency": "AUD",
              "capital_to_raise": 1000000
            }
            """;
        const string fixedPriceJson =
            """
            {
              "symbol": "ASX:FIXED",
              "timestamp_str": "2026-11-16",
              "issue_price": 1.50,
              "currency": "AUD",
              "capital_to_raise": null
            }
            """;

        Assert.Equal(
            typeof(decimal?),
            typeof(ListingEvent).GetProperty(nameof(ListingEvent.IssuePrice))!.PropertyType
        );
        Assert.Equal(
            typeof(decimal?),
            typeof(ListingEvent)
                .GetProperty(nameof(ListingEvent.IssuePriceUpper))!
                .PropertyType
        );

        var rangedPrice = JsonSerializer.Deserialize<ListingEvent>(rangedPriceJson);
        var fixedPrice = JsonSerializer.Deserialize<ListingEvent>(fixedPriceJson);

        Assert.NotNull(rangedPrice);
        Assert.Equal(0.20m, rangedPrice.IssuePrice);
        Assert.Equal(0.25m, rangedPrice.IssuePriceUpper);
        Assert.NotNull(fixedPrice);
        Assert.Equal(1.50m, fixedPrice.IssuePrice);
        Assert.Null(fixedPrice.IssuePriceUpper);

        using var serialized = JsonDocument.Parse(
            JsonSerializer.Serialize(rangedPrice)
        );
        Assert.Equal(
            0.20m,
            serialized.RootElement.GetProperty("issue_price").GetDecimal()
        );
        Assert.Equal(
            0.25m,
            serialized.RootElement.GetProperty("issue_price_upper").GetDecimal()
        );
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
              "overall_data_quality": "High",
              "data_gaps": [],
              "validation_warnings": [],
              "references": []
            }
            """;

        var result = JsonSerializer.Deserialize<IPortfolioAnalysisResult>(json);

        var construction = Assert.IsType<PortfolioConstruction>(result);
        Assert.Equal("PortfolioConstruction", construction.ResultType);
        Assert.Null(construction.ActionPlan);
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
