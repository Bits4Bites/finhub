from app.models import market as models_market


def test_company_brief_info_extracts_exchange_qualified_symbol_and_serializes():
    company = models_market.CompanyBriefInfo(
        symbol="ASX:CBA",
        name="Commonwealth Bank of Australia",
        sector="Financial Services",
        market_cap=200_000_000_000,
        country="AU",
    )

    assert company.extract_exchange_code() == ("ASX", "CBA")
    assert company.model_dump(mode="json") == {
        "symbol": "ASX:CBA",
        "name": "Commonwealth Bank of Australia",
        "sector": "Financial Services",
        "market_cap": 200_000_000_000,
        "country": "AU",
    }


def test_company_brief_info_returns_unqualified_symbol_as_code():
    company = models_market.CompanyBriefInfo(symbol="CBA.AX")

    assert company.extract_exchange_code() == ("", "CBA.AX")
