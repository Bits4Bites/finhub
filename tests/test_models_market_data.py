import types

from app.models import market_data as models_market_data


def _ticker_info(**overrides) -> types.SimpleNamespace:
    info = {
        "currency": "USD",
        "regularMarketPrice": 100.0,
        "regularMarketChange": 0.0,
        "regularMarketChangePercent": 1.5,
        "regularMarketOpen": None,
        "regularMarketDayHigh": 110.0,
        "regularMarketDayLow": 0.0,
        "fiftyTwoWeekHigh": 150.0,
        "fiftyTwoWeekLow": 75.0,
        "regularMarketVolume": 1_000,
        "bid": 99.0,
        "bidSize": 10,
        "ask": 101.0,
        "askSize": 20,
        "marketCap": 1_000,
        "trailingEps": 0.0,
        "epsTrailingTwelveMonths": 9.0,
        "forwardEps": None,
        "trailingPE": 20.0,
        "forwardPE": 18.0,
        "beta": 0.0,
        "beta3Year": 1.2,
        "recommendationKey": "hold",
        "targetHighPrice": 130.0,
        "targetLowPrice": 90.0,
        "targetMeanPrice": 110.0,
        "targetMedianPrice": 108.0,
    }
    info.update(overrides)
    return types.SimpleNamespace(info=info)


def test_history_point_to_currency_converts_only_monetary_values_and_returns_copy():
    point = models_market_data.HistoryPoint(
        timestamp=1_700_000_000,
        timestamp_str="2026-01-02 10:00:00+11:00",
        currency="USD",
        open=0.0,
        high=12.0,
        low=0.0,
        close=10.0,
        volume=250,
        dividends=0.0,
        rsi14=55.0,
        dvt=0.0,
    )

    converted = point.to_currency("AUD", 1.5)

    assert converted is not point
    assert converted.model_dump(mode="json") == {
        "timestamp": 1_700_000_000,
        "timestamp_str": "2026-01-02 10:00:00+11:00",
        "currency": "AUD",
        "open": 0.0,
        "high": 18.0,
        "low": 0.0,
        "close": 15.0,
        "volume": 250,
        "dividends": 0.0,
        "rsi14": 55.0,
        "dvt": 0.0,
    }
    assert point.currency == "USD"
    assert point.close == 10.0


def test_history_point_to_currency_preserves_unavailable_values():
    point = models_market_data.HistoryPoint(
        timestamp=1_700_000_000,
        timestamp_str="2026-01-02 10:00:00+11:00",
        currency="USD",
        dividends=None,
        rsi14=None,
        dvt=None,
    )

    converted = point.to_currency("AUD", 1.5)

    assert converted.dividends is None
    assert converted.rsi14 is None
    assert converted.dvt is None


def test_stock_quote_constructor_extracts_all_documented_fields():
    quote = models_market_data.StockQuote(_ticker_info())

    assert quote.model_dump(mode="json") == {
        "currency": "USD",
        "market_price": 100.0,
        "market_price_change": 0.0,
        "market_price_change_percent": 1.5,
        "market_open": None,
        "market_day_high": 110.0,
        "market_day_low": 0.0,
        "fifty_two_week_high": 150.0,
        "fifty_two_week_low": 75.0,
        "market_volume": 1_000,
        "bid": 99.0,
        "bid_size": 10,
        "ask": 101.0,
        "ask_size": 20,
        "market_cap": 1_000,
        "trailing_eps": 0.0,
        "forward_eps": None,
        "trailing_p_e": 20.0,
        "forward_p_e": 18.0,
        "beta": 0.0,
        "recommendation_key": "hold",
        "target_high_price": 130.0,
        "target_low_price": 90.0,
        "target_mean_price": 110.0,
        "target_median_price": 108.0,
    }


def test_stock_quote_constructor_uses_trailing_eps_before_fallback():
    quote = models_market_data.StockQuote(_ticker_info(trailingEps=3.25, epsTrailingTwelveMonths=9.0))

    assert quote.trailing_eps == 3.25


def test_stock_quote_constructor_uses_trailing_eps_fallback_when_unavailable():
    quote = models_market_data.StockQuote(_ticker_info(trailingEps=None, epsTrailingTwelveMonths=2.75))

    assert quote.trailing_eps == 2.75


def test_stock_quote_constructor_preserves_zero_trailing_eps_and_beta():
    quote = models_market_data.StockQuote(
        _ticker_info(
            trailingEps=0.0,
            epsTrailingTwelveMonths=2.75,
            beta=0.0,
            beta3Year=1.2,
        )
    )

    assert quote.trailing_eps == 0.0
    assert quote.beta == 0.0


def test_stock_quote_to_currency_converts_monetary_values_and_preserves_indicators():
    quote = models_market_data.StockQuote(_ticker_info())

    converted = quote.to_currency("AUD", 1.5)

    assert converted is not quote
    assert converted.model_dump(mode="json") == {
        "currency": "AUD",
        "market_price": 150.0,
        "market_price_change": 0.0,
        "market_price_change_percent": 1.5,
        "market_open": None,
        "market_day_high": 165.0,
        "market_day_low": 0.0,
        "fifty_two_week_high": 225.0,
        "fifty_two_week_low": 112.5,
        "market_volume": 1_000,
        "bid": 148.5,
        "bid_size": 10,
        "ask": 151.5,
        "ask_size": 20,
        "market_cap": 1_500,
        "trailing_eps": 0.0,
        "forward_eps": None,
        "trailing_p_e": 20.0,
        "forward_p_e": 18.0,
        "beta": 0.0,
        "recommendation_key": "hold",
        "target_high_price": 195.0,
        "target_low_price": 135.0,
        "target_mean_price": 165.0,
        "target_median_price": 162.0,
    }
    assert quote.currency == "USD"
    assert quote.market_price == 100.0
