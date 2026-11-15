import asyncio
import datetime
import zoneinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services import crawler_core, crawler_div, crawler_earnings

DIVIDEND_COLUMNS = [
    "Ticker",
    "Company",
    "Ex-Div Date",
    "Payment Date",
    "Div Amount",
    "Div Yield",
    "Market Cap",
    "Exchange",
    "Currency",
]


class FakeHttpResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeLocator:
    def __init__(self, count: int = 0):
        self._count = count
        self.click_count = 0
        self.evaluate_count = 0

    async def count(self):
        return self._count

    def nth(self, _index):
        return self

    async def click(self):
        self.click_count += 1

    async def evaluate(self, _script):
        self.evaluate_count += 1


class FakeBrowserPage:
    def __init__(self, browser):
        self.browser = browser
        self.url = ""
        self.close_count = 0
        self.locators = {}

    async def goto(self, url, timeout):
        self.url = url
        self.browser.visited_urls.append(url)
        status = self.browser.next_status(url)
        return None if status is None else SimpleNamespace(status=status)

    async def content(self):
        content = self.browser.html_by_url.get(self.url, self.browser.default_html)
        if isinstance(content, Exception):
            raise content
        return content

    async def close(self):
        self.close_count += 1

    def locator(self, selector):
        return self.locators.setdefault(selector, FakeLocator())


class FakeBrowser:
    def __init__(self, *, html_by_url=None, status_by_url=None, default_html="<html></html>"):
        self.html_by_url = html_by_url or {}
        self.status_by_url = status_by_url or {}
        self.default_html = default_html
        self.visited_urls = []
        self.pages = []
        self.close_count = 0

    def next_status(self, url):
        status = self.status_by_url.get(url, 200)
        if isinstance(status, list):
            return status.pop(0)
        return status

    async def new_page(self, **_kwargs):
        page = FakeBrowserPage(self)
        self.pages.append(page)
        return page

    async def close(self):
        self.close_count += 1


class FakePlaywrightContext:
    def __init__(self, browser):
        self.browser = browser
        self.playwright = MagicMock()
        self.playwright.webkit.launch = AsyncMock(return_value=browser)

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, *_args):
        return None


def _playwright_boundary(browser):
    context = FakePlaywrightContext(browser)
    return patch("app.services.crawler_core.playwright_async_api.async_playwright", return_value=context), context


def _table_html(headers, rows, *, table_id=None):
    table_attr = f' id="{table_id}"' if table_id else ""
    header_html = "".join(f"<th>{header}</th>" for header in headers)
    rows_html = "".join(f"<tr>{''.join(f'<td>{value}</td>' for value in row)}</tr>" for row in rows)
    return f"<table{table_attr}><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>"


@pytest.fixture(autouse=True)
def cache_boundary():
    with (
        patch("app.services.crawler_core.cache.get", new_callable=AsyncMock, return_value=None) as cache_get,
        patch("app.services.crawler_core.cache.set", new_callable=AsyncMock, return_value=True) as cache_set,
    ):
        yield SimpleNamespace(get=cache_get, set=cache_set)


class TestTableExtraction:
    def test_extracts_clean_text_from_selected_table(self):
        html = _table_html(["Ignored"], [["first"]], table_id="events") + _table_html(
            ["Name", "Value"], [["  Alpha\n Ltd  ", "10"]], table_id="events"
        )

        result = crawler_core.extract_data_table_from_html(
            html,
            table_attr_filter={"id": "events"},
            filter_skip=1,
        )

        assert result.to_dict(orient="records") == [{"Name": "Alpha Ltd", "Value": "10"}]

    def test_can_preserve_cell_html(self):
        html = _table_html(["Name"], [["<a href='/stocks/a'>Alpha</a>"]])

        result = crawler_core.extract_data_table_from_html(html, raw_cell_content=True)

        assert result.iloc[0, 0] == '<a href="/stocks/a">Alpha</a>'

    @pytest.mark.parametrize("html", ["<html></html>", "<table><tr><th>Name</th></tr></table>"])
    def test_returns_empty_when_no_matching_rows_exist(self, html):
        assert crawler_core.extract_data_table_from_html(html).empty

    def test_rejects_negative_table_skip(self):
        with pytest.raises(ValueError, match="filter_skip"):
            crawler_core.extract_data_table_from_html("<table></table>", filter_skip=-1)


class TestHttpFetching:
    def test_returns_cached_html_without_requesting_network(self, cache_boundary):
        cache_boundary.get.return_value = "<html>cached</html>"

        with patch("app.services.crawler_core.cloudscraper.create_scraper") as create_scraper:
            result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test"))

        assert result == "<html>cached</html>"
        create_scraper.assert_not_called()

    def test_fetches_and_caches_successful_html(self, cache_boundary):
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(200, "<html>fresh</html>")

        with patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper):
            result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test"))

        assert result == "<html>fresh</html>"
        assert scraper.get.call_count == 1
        assert scraper.get.call_args.args[0] == "https://example.test"
        cache_boundary.set.assert_awaited_once()

    def test_client_errors_are_not_retried(self):
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(429)

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_core.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test", retries=3))

        assert result is None
        assert scraper.get.call_count == 1
        sleep.assert_not_awaited()

    def test_retries_means_total_attempts(self):
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(503)

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_core.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test", retries=2))

        assert result is None
        assert scraper.get.call_count == 2
        sleep.assert_awaited_once()

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [({"retries": 0}, "retries"), ({"backoff_factor": -0.1}, "backoff_factor")],
    )
    def test_rejects_invalid_retry_configuration(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            asyncio.run(crawler_core.fetch_webpage_content("https://example.test", **kwargs))


class TestBrowserFetching:
    def test_fetches_page_runs_callback_and_caches_html(self, cache_boundary):
        browser = FakeBrowser(default_html="<html>browser</html>")
        callback = AsyncMock()
        playwright_patch, _context = _playwright_boundary(browser)

        with playwright_patch:
            result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(
                    "https://example.test",
                    after_load_func_async=callback,
                )
            )

        assert result == "<html>browser</html>"
        callback.assert_awaited_once_with(browser.pages[0])
        assert browser.close_count == 1
        cache_boundary.set.assert_awaited_once()

    def test_client_error_is_not_read_or_retried(self, cache_boundary):
        browser = FakeBrowser(status_by_url={"https://example.test": 404})
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            playwright_patch,
            patch("app.services.crawler_core.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content_playwright("https://example.test", retries=2))

        assert result is None
        assert browser.visited_urls == ["https://example.test"]
        sleep.assert_not_awaited()
        cache_boundary.set.assert_not_awaited()

    def test_server_error_consumes_each_configured_attempt(self):
        url = "https://example.test"
        browser = FakeBrowser(
            html_by_url={url: "<html>recovered</html>"},
            status_by_url={url: [503, 200]},
        )
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            playwright_patch,
            patch("app.services.crawler_core.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content_playwright(url, retries=2))

        assert result == "<html>recovered</html>"
        assert browser.visited_urls == [url, url]
        sleep.assert_awaited_once()

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [({"retries": 0}, "retries"), ({"backoff_factor": -0.1}, "backoff_factor")],
    )
    def test_invalid_configuration_is_rejected_before_browser_launch(self, cache_boundary, kwargs, message):
        with (
            patch("app.services.crawler_core.playwright_async_api.async_playwright") as playwright,
            pytest.raises(ValueError, match=message),
        ):
            asyncio.run(crawler_core.fetch_webpage_content_playwright("https://example.test", **kwargs))

        playwright.assert_not_called()
        cache_boundary.get.assert_not_awaited()

    def test_multi_fetch_is_serial_ordered_and_does_not_retry_failed_pages(self, cache_boundary):
        urls = [
            "https://example.test/first",
            "https://example.test/failure",
            "https://example.test/cached",
        ]
        cached_key = crawler_core.cache.generate_key("crawler", "playwright", "", urls[2])
        cache_boundary.get.side_effect = lambda key: "<html>cached</html>" if key == cached_key else None
        browser = FakeBrowser(
            html_by_url={urls[0]: "<html>first</html>"},
            status_by_url={urls[1]: 503},
        )
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            playwright_patch,
            patch("app.services.crawler_core.asyncio.sleep", new_callable=AsyncMock) as sleep,
        ):
            result = asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    urls,
                    delay_between_requests=0.25,
                )
            )

        assert result == ["<html>first</html>", None, "<html>cached</html>"]
        assert browser.visited_urls == urls[:2]
        assert [page.close_count for page in browser.pages] == [1, 1]
        assert sleep.await_count == 2

    def test_multi_fetch_empty_input_does_not_start_browser(self):
        with patch("app.services.crawler_core.playwright_async_api.async_playwright") as playwright:
            result = asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([]))

        assert result == []
        playwright.assert_not_called()

    def test_multi_fetch_rejects_negative_delay(self):
        with pytest.raises(ValueError, match="delay_between_requests"):
            asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    ["https://example.test"],
                    delay_between_requests=-1,
                )
            )


class TestTableScraping:
    @pytest.mark.parametrize(
        ("public_function", "fetch_target"),
        [
            (
                crawler_core.scrape_data_table,
                "app.services.crawler_core.fetch_webpage_content_fallback_to_playwright",
            ),
            (
                crawler_core.scrape_data_table_playwright,
                "app.services.crawler_core.fetch_webpage_content_playwright",
            ),
        ],
    )
    def test_negative_filter_skip_is_rejected_before_fetch(self, public_function, fetch_target):
        with (
            patch(fetch_target, new_callable=AsyncMock) as fetch,
            pytest.raises(ValueError, match="filter_skip"),
        ):
            asyncio.run(public_function("https://example.test", filter_skip=-1))

        fetch.assert_not_awaited()

    def test_scrape_data_table_uses_real_fetch_and_extraction(self):
        html = _table_html(["Name", "Value"], [["Alpha", "10"]])
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(200, html)

        with patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper):
            result = asyncio.run(crawler_core.scrape_data_table("https://example.test"))

        assert result.to_dict(orient="records") == [{"Name": "Alpha", "Value": "10"}]

    def test_scrape_data_table_playwright_uses_real_fetch_and_extraction(self):
        url = "https://example.test/events"
        browser = FakeBrowser(
            html_by_url={url: _table_html(["Ticker", "Amount"], [["ABC", "1.25"]], table_id="events")}
        )
        playwright_patch, _context = _playwright_boundary(browser)

        with playwright_patch:
            result = asyncio.run(
                crawler_core.scrape_data_table_playwright(
                    url,
                    table_attr_filter={"id": "events"},
                )
            )

        assert result.to_dict(orient="records") == [{"Ticker": "ABC", "Amount": "1.25"}]

    def test_fallback_uses_browser_after_http_attempts_fail(self):
        url = "https://example.test"
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(503)
        browser = FakeBrowser(html_by_url={url: "<html>browser</html>"})
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            playwright_patch,
            patch("app.services.crawler_core.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content_fallback_to_playwright(url))

        assert result == "<html>browser</html>"
        assert scraper.get.call_count == 2
        assert browser.visited_urls == [url]


class TestDividendCrawlers:
    def test_asx_rows_follow_the_canonical_contract(self):
        today = datetime.datetime.now(zoneinfo.ZoneInfo("Australia/Sydney")).date()
        url = f"https://www.tipranks.com/calendars/dividends/{today.isoformat()}/australia"
        html = _table_html(
            ["Name", "Company", "Dividend Amount", "Dividend Yield", "Market Cap", "Payment Date"],
            [["CBA", "Commonwealth Bank", "AU$2.50", "4.00%", "$200B", "In 10 Days"]],
        )
        browser = FakeBrowser(html_by_url={url: html})
        playwright_patch, _context = _playwright_boundary(browser)

        with playwright_patch:
            result = asyncio.run(crawler_div.scrape_dividends_asx(today))

        assert list(result.columns) == DIVIDEND_COLUMNS
        assert result.iloc[0].to_dict() == {
            "Ticker": "CBA",
            "Company": "Commonwealth Bank",
            "Ex-Div Date": today.isoformat(),
            "Payment Date": (today + datetime.timedelta(days=10)).isoformat(),
            "Div Amount": 2.5,
            "Div Yield": 0.04,
            "Market Cap": 200_000_000_000,
            "Exchange": "ASX",
            "Currency": "AUD",
        }

    @pytest.mark.parametrize(
        ("headers", "row", "message"),
        [
            (
                ["Name", "Company", "Dividend Amount"],
                ["BAD", "Bad Amount Ltd", "not-money"],
                "invalid dividend amount",
            ),
            (
                ["Name", "Company"],
                ["BAD", "Missing Amount Ltd"],
                "missing columns",
            ),
        ],
    )
    def test_asx_rejects_malformed_required_dividend_values(self, headers, row, message):
        today = datetime.datetime.now(zoneinfo.ZoneInfo("Australia/Sydney")).date()
        url = f"https://www.tipranks.com/calendars/dividends/{today.isoformat()}/australia"
        browser = FakeBrowser(html_by_url={url: _table_html(headers, [row])})
        playwright_patch, _context = _playwright_boundary(browser)

        with playwright_patch, pytest.raises(ValueError, match=message):
            asyncio.run(crawler_div.scrape_dividends_asx(today))

    def test_us_rows_resolve_tickers_from_multiple_loaded_indexes(self):
        today = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
        url = f"https://www.tipranks.com/calendars/dividends/{today.isoformat()}"
        index_store = crawler_div.market.market_indices
        selected_companies = []
        selected_codes = set()
        for index_name in ("NASDAQ100", "SP600"):
            for company in index_store.indices[index_name].values():
                _exchange, code = company.extract_exchange_code()
                if code not in selected_codes:
                    selected_companies.append(company)
                    selected_codes.add(code)
                    break

        assert len(selected_companies) == 2
        source_rows = []
        expected_exchanges = {}
        for company in selected_companies:
            exchange, ticker = company.extract_exchange_code()
            source_rows.append([ticker, company.name, "$0.25", "0.50%", "$3T", "Next Month"])
            expected_exchanges[ticker] = exchange

        html = _table_html(
            ["Name", "Company", "Dividend Amount", "Dividend Yield", "Market Cap", "Payment Date"],
            source_rows,
        )
        browser = FakeBrowser(html_by_url={url: html})
        playwright_patch, _context = _playwright_boundary(browser)

        with playwright_patch:
            result = asyncio.run(crawler_div.scrape_dividends_us(today))

        assert list(result.columns) == DIVIDEND_COLUMNS
        assert result.set_index("Ticker")["Exchange"].to_dict() == expected_exchanges
        assert result["Currency"].tolist() == ["USD", "USD"]
        assert result["Payment Date"].tolist() == [
            (today + datetime.timedelta(days=30)).isoformat(),
            (today + datetime.timedelta(days=30)).isoformat(),
        ]

    def test_vn_rows_are_cash_dividends_in_the_canonical_contract(self):
        today = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")).date()
        start_date = today
        for _ in range(2):
            start_date -= datetime.timedelta(days=1)
            if start_date.weekday() >= 5:
                start_date -= datetime.timedelta(days=start_date.weekday() - 4)
        url_template = "https://finance.vietstock.vn/lich-su-kien.htm?from={start}&to={end}&page={page}&tab=1&group=13"
        first_url = url_template.format(start=start_date, end=today, page=1)
        second_url = url_template.format(start=start_date, end=today, page=2)
        html = _table_html(
            ["STT", "Mã CK", "Sàn", "Ngày GDKHQ▼", "Ngày ĐKCC", "Ngày thực hiện", "Tỷ lệ", "Nội dung sự kiện"],
            [["1", "VNM", "hose", "20/11/2026", "21/11/2026", "15/12/2026", "15%", "Cash dividend"]],
            table_id="event-content",
        )
        browser = FakeBrowser(
            html_by_url={first_url: html, second_url: "<html></html>"},
        )
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            playwright_patch,
            patch("app.services.crawler_div.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_vn(today))

        assert list(result.columns) == DIVIDEND_COLUMNS
        row = result.iloc[0]
        assert row.drop(labels=["Market Cap"]).to_dict() == {
            "Ticker": "VNM",
            "Company": "VNM",
            "Ex-Div Date": "2026-11-20",
            "Payment Date": "2026-12-15",
            "Div Amount": 1500.0,
            "Div Yield": 0.15,
            "Exchange": "HOSE",
            "Currency": "VND",
        }
        assert pd.isna(row["Market Cap"])

    @pytest.mark.parametrize(
        "source_row",
        [
            {
                "Sàn": "HOSE",
                "Ngày GDKHQ▼": "20/11/2026",
                "Ngày thực hiện": "15/12/2026",
                "Tỷ lệ": "15%",
            },
            {
                "Mã CK": "VNM",
                "Sàn": "HOSE",
                "Ngày GDKHQ▼": "not-a-date",
                "Ngày thực hiện": "15/12/2026",
                "Tỷ lệ": "15%",
            },
            {
                "Mã CK": "VNM",
                "Sàn": "HOSE",
                "Ngày GDKHQ▼": "20/11/2026",
                "Ngày thực hiện": "15/12/2026",
                "Tỷ lệ": "not-a-rate",
            },
        ],
        ids=["missing-ticker", "malformed-ex-date", "malformed-yield"],
    )
    def test_vn_rejects_missing_or_malformed_required_values(self, source_row):
        source_data = pd.DataFrame([source_row])
        today = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")).date()

        with (
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new_callable=AsyncMock,
                side_effect=[source_data, pd.DataFrame()],
            ),
            patch("app.services.crawler_div.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ValueError),
        ):
            asyncio.run(crawler_div.scrape_dividends_vn(today))

    def test_no_rows_return_canonical_empty_frames(self):
        browser = FakeBrowser(default_html="<html></html>")
        playwright_patch, _context = _playwright_boundary(browser)
        dates = {
            "asx": datetime.datetime.now(zoneinfo.ZoneInfo("Australia/Sydney")).date(),
            "us": datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date(),
            "vn": datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")).date(),
        }

        with (
            playwright_patch,
            patch("app.services.crawler_div.asyncio.sleep", new_callable=AsyncMock),
        ):
            results = [
                asyncio.run(crawler_div.scrape_dividends_asx(dates["asx"])),
                asyncio.run(crawler_div.scrape_dividends_us(dates["us"])),
                asyncio.run(crawler_div.scrape_dividends_vn(dates["vn"])),
            ]

        assert all(result.empty for result in results)
        assert all(list(result.columns) == DIVIDEND_COLUMNS for result in results)


class TestEarningsCrawlers:
    def test_tipranks_callback_accepts_missing_controls(self):
        page = FakeBrowserPage(FakeBrowser())

        asyncio.run(crawler_earnings.tipranks_after_load_func(page))

        assert page.locators
        assert all(locator.click_count == 0 for locator in page.locators.values())
        assert all(locator.evaluate_count == 0 for locator in page.locators.values())

    def test_tipranks_callback_hides_ads_and_selects_exchange_column(self):
        page = FakeBrowserPage(FakeBrowser())
        ads = FakeLocator(count=2)
        select_columns = FakeLocator(count=1)
        exchange_name = FakeLocator(count=1)
        save = FakeLocator(count=1)
        page.locators = {
            "div[data-google-query-id]": ads,
            "button[data-id='select-columns-button']": select_columns,
            "label[title='Exchange Name']": exchange_name,
            "button[id='save']": save,
        }

        asyncio.run(crawler_earnings.tipranks_after_load_func(page))

        assert ads.evaluate_count == 2
        assert select_columns.click_count == 1
        assert exchange_name.click_count == 1
        assert save.click_count == 1

    def test_default_end_date_is_resolved_when_called(self):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 16, 9, 0)
                return value.replace(tzinfo=tz) if tz else value

        html = _table_html(
            ["Name", "Company Name", "Exchange Name", "Market Cap"],
            [["AAPL", "Apple Inc.", "NASDAQ", "$3T"]],
        )
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(200, html)

        with (
            patch("app.services.crawler_earnings.datetime.datetime", FixedDateTime),
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_earnings.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                )
            )

        assert result["Announcement Date"].tolist() == ["2026-11-16", "2026-11-17"]
        assert list(result.columns) == ["Symbol", "Announcement Date", "Company Name", "Exchange Name"]

    def test_weekend_start_moves_to_monday_and_continues_after_failed_page(self):
        class WeekendDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 14, 9, 0)
                return value.replace(tzinfo=tz) if tz else value

        monday_url = "https://example.test/earnings/2026-11-16"
        tuesday_url = "https://example.test/earnings/2026-11-17"
        tuesday_html = _table_html(
            ["Name", "Company Name", "Exchange Name"],
            [["MSFT", "Microsoft", "NASDAQ"]],
        )
        scraper = MagicMock()
        scraper.get.side_effect = lambda url, **_kwargs: (
            FakeHttpResponse(503) if url == monday_url else FakeHttpResponse(200, tuesday_html)
        )
        browser = FakeBrowser(status_by_url={monday_url: [503, 503]})
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            patch("app.services.crawler_earnings.datetime.datetime", WeekendDateTime),
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            playwright_patch,
            patch("app.services.crawler_earnings.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                )
            )

        assert result.to_dict(orient="records") == [
            {
                "Symbol": "MSFT",
                "Announcement Date": "2026-11-17",
                "Company Name": "Microsoft",
                "Exchange Name": "NASDAQ",
            }
        ]
        assert [call.args[0] for call in scraper.get.call_args_list] == [monday_url, monday_url, tuesday_url]
        assert browser.visited_urls == [monday_url, monday_url]

    def test_playwright_wrapper_returns_normalized_rows(self):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 16, 9, 0)
                return value.replace(tzinfo=tz) if tz else value

        url = "https://example.test/earnings/2026-11-16"
        browser = FakeBrowser(
            html_by_url={
                url: _table_html(
                    ["Name", "Company Name", "Exchange Name"],
                    [["MSFT", "Microsoft", "NASDAQ"]],
                )
            }
        )
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            patch("app.services.crawler_earnings.datetime.datetime", FixedDateTime),
            playwright_patch,
            patch("app.services.crawler_earnings.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks_playwright(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                )
            )

        assert result.to_dict(orient="records") == [
            {
                "Symbol": "MSFT",
                "Announcement Date": "2026-11-16",
                "Company Name": "Microsoft",
                "Exchange Name": "NASDAQ",
            }
        ]

    def test_market_wrappers_use_their_expected_sources(self):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 16, 9, 0)
                return value.replace(tzinfo=tz) if tz else value

        html = _table_html(
            ["Name", "Company Name", "Exchange Name"],
            [["CBA", "Commonwealth Bank", "ASX"]],
        )
        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(200, html)
        us_url = "https://www.tipranks.com/calendars/earnings/2026-11-16"
        browser = FakeBrowser(html_by_url={us_url: html})
        playwright_patch, _context = _playwright_boundary(browser)

        with (
            patch("app.services.crawler_earnings.datetime.datetime", FixedDateTime),
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            playwright_patch,
            patch("app.services.crawler_earnings.asyncio.sleep", new_callable=AsyncMock),
        ):
            asx_result = asyncio.run(crawler_earnings.scrape_earnings_asx(datetime.date(2026, 11, 16)))
            us_result = asyncio.run(crawler_earnings.scrape_earnings_us(datetime.date(2026, 11, 16)))

        asx_url = "https://www.tipranks.com/calendars/earnings/2026-11-16/australia"
        assert scraper.get.call_args.args[0] == asx_url
        assert browser.visited_urls == [us_url]
        assert asx_result.iloc[0]["Symbol"] == "CBA"
        assert us_result.iloc[0]["Symbol"] == "CBA"

    def test_empty_pages_return_an_empty_frame(self):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 16, 9, 0)
                return value.replace(tzinfo=tz) if tz else value

        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(200, "<html></html>")

        with (
            patch("app.services.crawler_earnings.datetime.datetime", FixedDateTime),
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_earnings.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                )
            )

        assert result.empty

    def test_nonempty_table_without_symbol_is_rejected(self):
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                value = cls(2026, 11, 16, 9, 0)
                return value.replace(tzinfo=tz) if tz else value

        scraper = MagicMock()
        scraper.get.return_value = FakeHttpResponse(
            200,
            _table_html(["Company Name"], [["Missing Symbol Ltd"]]),
        )

        with (
            patch("app.services.crawler_earnings.datetime.datetime", FixedDateTime),
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_earnings.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(ValueError, match="Name column"),
        ):
            asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                )
            )
