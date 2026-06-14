import asyncio
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from app.services import crawler


class TestCrawlerTableExtraction:
    def test_extract_data_table_from_html(self):
        html = """
        <table>
          <thead><tr><th>Name</th><th>Value</th></tr></thead>
          <tbody><tr><td>Alpha</td><td>10</td></tr></tbody>
        </table>
        """

        result = crawler.extract_data_table_from_html(html)

        assert list(result.columns) == ["Name", "Value"]
        assert result.iloc[0].to_dict() == {"Name": "Alpha", "Value": "10"}


class TestCrawlerFetching:
    def test_fetch_webpage_content_returns_text(self):
        fake_response = SimpleNamespace(text="ok", raise_for_status=lambda: None)
        fake_scraper = MagicMock()
        fake_scraper.get.return_value = fake_response

        with patch("app.services.crawler.cloudscraper.create_scraper", return_value=fake_scraper):
            result = asyncio.run(crawler.fetch_webpage_content("https://example.test"))

        assert result == "ok"
        fake_scraper.get.assert_called_once()


class TestCrawlerScrape:
    def test_scrape_data_table_uses_fetch_and_parse(self):
        expected = pd.DataFrame({"Name": ["Alpha"]})

        with (
            patch(
                "app.services.crawler.fetch_webpage_content", new_callable=AsyncMock, return_value="<table></table>"
            ) as mock_fetch,
            patch("app.services.crawler.extract_data_table_from_html", return_value=expected) as mock_extract,
        ):
            result = asyncio.run(crawler.scrape_data_table("https://example.test"))

        assert result.equals(expected)
        mock_fetch.assert_awaited_once_with("https://example.test")
        mock_extract.assert_called_once_with("<table></table>", raw_cell_content=False, table_attr_filter=None)

    def test_scrape_dividends_from_tipranks_adds_ex_dividend_date(self):
        expected = pd.DataFrame({"Name": ["A"]})

        with (
            patch(
                "app.services.crawler.scrape_data_table_playwright", new_callable=AsyncMock, return_value=expected
            ) as mock_scrape,
            patch("app.services.crawler.time.sleep"),
        ):
            result = asyncio.run(
                crawler.scrape_dividends_from_tipranks(
                    "https://example.test/{date}",
                    end_date=datetime.date.today(),
                    tz_name="UTC",
                    use_playwright=True,
                )
            )

        assert "Ex-Dividend Date" in result.columns
        mock_scrape.assert_awaited()

    def test_scrape_dividends_asx_adds_exchange_name(self):
        expected = pd.DataFrame({"Name": ["A"]})

        with patch(
            "app.services.crawler.scrape_dividends_from_tipranks", new_callable=AsyncMock, return_value=expected
        ) as mock_scrape:
            result = asyncio.run(crawler.scrape_dividends_asx(datetime.date.today()))

        assert result.equals(pd.DataFrame({"Name": ["A"], "Exchange Name": ["ASX"]}))
        mock_scrape.assert_awaited_once()

    def test_scrape_dividends_us_uses_playwright_wrapper(self):
        expected = pd.DataFrame({"Name": ["A"]})

        with patch(
            "app.services.crawler.scrape_dividends_from_tipranks_playwright",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_scrape:
            result = asyncio.run(crawler.scrape_dividends_us(datetime.date.today()))

        assert result.equals(expected)
        mock_scrape.assert_awaited_once()

    def test_scrape_earnings_from_tipranks_adds_announcement_date(self):
        expected = pd.DataFrame({"Name": ["A"]})

        with (
            patch(
                "app.services.crawler.scrape_data_table", new_callable=AsyncMock, return_value=expected
            ) as mock_scrape,
            patch("app.services.crawler.time.sleep"),
        ):
            result = asyncio.run(
                crawler.scrape_earnings_from_tipranks(
                    "https://example.test/{date}",
                    end_date=datetime.date.today() + datetime.timedelta(days=7),
                    tz_name="UTC",
                )
            )

        assert "Announcement Date" in result.columns
        mock_scrape.assert_awaited()

    def test_scrape_earnings_asx_uses_earnings_path(self):
        expected = pd.DataFrame({"Name": ["A"]})

        with patch(
            "app.services.crawler.scrape_earnings_from_tipranks", new_callable=AsyncMock, return_value=expected
        ) as mock_scrape:
            result = asyncio.run(crawler.scrape_earnings_asx(datetime.date.today()))

        assert result.equals(expected)
        mock_scrape.assert_awaited_once()

    def test_scrape_earnings_us_uses_playwright_wrapper(self):
        expected = pd.DataFrame({"Name": ["A"]})

        with patch(
            "app.services.crawler.scrape_earnings_from_tipranks_playwright",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_scrape:
            result = asyncio.run(crawler.scrape_earnings_us(datetime.date.today()))

        assert result.equals(expected)
        mock_scrape.assert_awaited_once()


class FakeLocator:
    def __init__(self, count=0, click=None):
        self._count = count
        self._click = click

    async def count(self):
        return self._count

    async def evaluate(self, *args, **kwargs):
        return None

    async def click(self):
        if self._click is not None:
            self._click()


class FakePage:
    def __init__(self):
        self.calls = []

    def locator(self, selector):
        self.calls.append(selector)
        return FakeLocator(count=0)


class TestCrawlerUiHelper:
    def test_tipranks_after_load_func_handles_missing_elements(self):
        page = FakePage()

        asyncio.run(crawler.tipranks_after_load_func(page))

        assert page.calls
