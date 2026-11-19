import asyncio
import datetime
import urllib.parse
import zoneinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bs4
import pandas as pd
import pytest

from app.services import crawler_core, crawler_div, crawler_earnings, events_div

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
EARNINGS_COLUMNS = [
    "Announcement Date",
    "Exchange",
    "Ticker",
    "Company",
    "Market Cap",
    "EPS",
    "EPS Forecast",
    "Revenue",
    "Revenue Forecast",
    "Currency",
]


class FakeCache:
    def __init__(self):
        self.values = {}
        self.now = 0.0

    async def get(self, key):
        cached = self.values.get(key)
        if cached is None:
            return None
        value, expires_at = cached
        if self.now >= expires_at:
            self.values.pop(key)
            return None
        return value

    async def set(self, key, value, *, ttl):
        self.values[key] = (value, self.now + ttl)
        return True

    def advance(self, seconds):
        self.now += seconds


class FakeHttpResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError


class FakeHttpScraper:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def get(self, _url, **_kwargs):
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeBrowserPage:
    def __init__(self, browser):
        self.browser = browser
        self.url = ""
        self.prepared = False

    async def goto(self, url, timeout):
        self.url = url
        status = self.browser.next_status(url)
        if isinstance(status, BaseException):
            raise status
        return None if status is None else SimpleNamespace(status=status)

    async def content(self):
        content = self.browser.content_for(self.url)
        if isinstance(content, BaseException):
            raise content
        return content(self) if callable(content) else content

    async def close(self):
        self.browser.release_page(self)


class FakeBrowser:
    def __init__(
        self,
        *,
        html_by_url=None,
        status_by_url=None,
        default_html="<html></html>",
        close_error=None,
        enforce_non_overlapping_pages=False,
    ):
        self.html_by_url = html_by_url or {}
        self.status_by_url = {
            url: list(statuses) if isinstance(statuses, list) else statuses
            for url, statuses in (status_by_url or {}).items()
        }
        self.default_html = default_html
        self.close_error = close_error
        self.enforce_non_overlapping_pages = enforce_non_overlapping_pages
        self.active_page = None

    def next_status(self, url):
        status = self.status_by_url.get(url, 200)
        if isinstance(status, list):
            return status.pop(0) if len(status) > 1 else status[0]
        return status

    def content_for(self, url):
        return self.html_by_url.get(url, self.default_html)

    async def new_page(self, **_kwargs):
        if self.enforce_non_overlapping_pages and self.active_page is not None:
            raise RuntimeError("previous page is still active")
        page = FakeBrowserPage(self)
        self.active_page = page
        return page

    def release_page(self, page):
        if self.active_page is page:
            self.active_page = None

    async def close(self):
        self.active_page = None
        if self.close_error is not None:
            raise self.close_error


class FakePlaywrightContext:
    def __init__(self, browser=None, *, launch_error=None):
        launch = AsyncMock(side_effect=launch_error) if launch_error else AsyncMock(return_value=browser)
        self.playwright = SimpleNamespace(webkit=SimpleNamespace(launch=launch))

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, *_args):
        return None


class FakeCompany:
    def __init__(self, exchange, ticker):
        self.exchange = exchange
        self.ticker = ticker

    def extract_exchange_code(self):
        return self.exchange, self.ticker


def _playwright_boundary(browser=None, *, launch_error=None):
    context = FakePlaywrightContext(browser, launch_error=launch_error)
    return patch("app.services.crawler_core.playwright_async_api.async_playwright", return_value=context)


def _table_html(headers, rows, *, table_id=None):
    table_attr = f' id="{table_id}"' if table_id else ""
    header_html = "".join(f"<th>{header}</th>" for header in headers)
    rows_html = "".join(f"<tr>{''.join(f'<td>{value}</td>' for value in row)}</tr>" for row in rows)
    return f"<table{table_attr}><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>"


def _fixed_datetime(value):
    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return value.replace(tzinfo=tz) if tz else value

    return FixedDateTime


def _vn_range_scraper(source_data, *, expected_start=None, expected_end=None):
    async def scrape(url, **_kwargs):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        start_date = datetime.date.fromisoformat(query["from"][0])
        end_date = datetime.date.fromisoformat(query["to"][0])
        page = int(query["page"][0])
        if page != 1:
            return pd.DataFrame()
        if expected_start is not None or expected_end is not None:
            return source_data if start_date == expected_start and end_date == expected_end else pd.DataFrame()
        return source_data if start_date <= end_date else pd.DataFrame()

    return scrape


@pytest.fixture(autouse=True)
def cache_boundary():
    fake_cache = FakeCache()
    with (
        patch("app.services.crawler_core.cache.get", new=fake_cache.get),
        patch("app.services.crawler_core.cache.set", new=fake_cache.set),
    ):
        yield fake_cache


class TestTableExtraction:
    def test_extracts_clean_text_from_the_selected_table(self):
        html = _table_html(["Ignored"], [["first"]], table_id="events") + _table_html(
            ["Name", "Value"],
            [["  Alpha\n Ltd  ", "10"]],
            table_id="events",
        )

        result = crawler_core.extract_data_table_from_html(
            html,
            table_attr_filter={"id": "events"},
            filter_skip=1,
        )

        assert result.to_dict(orient="records") == [{"Name": "Alpha Ltd", "Value": "10"}]

    def test_preserves_cell_html_when_requested(self):
        html = _table_html(["Name"], [["<a href='/stocks/a'>Alpha</a>"]])

        result = crawler_core.extract_data_table_from_html(html, raw_cell_content=True)

        fragment = bs4.BeautifulSoup(result.iloc[0]["Name"], "html.parser")
        link = fragment.find("a")
        assert link is not None
        assert link.get("href") == "/stocks/a"
        assert link.get_text(strip=True) == "Alpha"

    @pytest.mark.parametrize("html", ["<html></html>", "<table><tr><th>Name</th></tr></table>"])
    def test_returns_empty_when_no_matching_rows_exist(self, html):
        assert crawler_core.extract_data_table_from_html(html).empty

    def test_rejects_negative_table_skip(self):
        with pytest.raises(ValueError):
            crawler_core.extract_data_table_from_html("<table></table>", filter_skip=-1)


class TestHttpFetching:
    def test_successful_html_is_reused_from_cache(self):
        scraper = FakeHttpScraper(
            [
                FakeHttpResponse(200, "<html>fresh</html>"),
                RuntimeError("network should no longer be needed"),
            ]
        )

        with patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper):
            first_result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page"))
            cached_result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page"))

        assert first_result == "<html>fresh</html>"
        assert cached_result == first_result

    def test_expired_cache_refetches_http_content(self, cache_boundary):
        scraper = FakeHttpScraper(
            [
                FakeHttpResponse(200, "<html>first</html>"),
                FakeHttpResponse(200, "<html>refetched</html>"),
            ]
        )

        with patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper):
            first_result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page", cache_ttl=10))
            cache_boundary.advance(11)
            refetched_result = asyncio.run(
                crawler_core.fetch_webpage_content("https://example.test/page", cache_ttl=10)
            )

        assert first_result == "<html>first</html>"
        assert refetched_result == "<html>refetched</html>"

    def test_retryable_http_failure_can_recover(self):
        scraper = FakeHttpScraper(
            [
                FakeHttpResponse(503),
                FakeHttpResponse(200, "<html>recovered</html>"),
            ]
        )

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content(
                    "https://example.test/page",
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result == "<html>recovered</html>"

    def test_transport_failure_can_recover(self):
        scraper = FakeHttpScraper(
            [
                OSError("connection reset"),
                FakeHttpResponse(200, "<html>recovered</html>"),
            ]
        )

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content(
                    "https://example.test/page",
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result == "<html>recovered</html>"

    def test_transport_failure_is_not_cached(self):
        scraper = FakeHttpScraper(
            [
                OSError("connection reset"),
                FakeHttpResponse(200, "<html>later success</html>"),
            ]
        )

        with patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper):
            failed_result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page", retries=1))
            recovered_result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page", retries=1))

        assert failed_result is None
        assert recovered_result == "<html>later success</html>"

    def test_client_failure_is_non_retryable(self):
        scraper = FakeHttpScraper(
            [
                FakeHttpResponse(429),
                FakeHttpResponse(200, "<html>late success</html>"),
            ]
        )

        with patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper):
            result = asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page", retries=3))

        assert result is None

    def test_exhausted_retryable_failures_return_none(self):
        scraper = FakeHttpScraper([FakeHttpResponse(503)])

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content(
                    "https://example.test/page",
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result is None

    @pytest.mark.parametrize("kwargs", [{"retries": 0}, {"backoff_factor": -0.1}])
    def test_rejects_invalid_retry_configuration(self, kwargs):
        with pytest.raises(ValueError):
            asyncio.run(crawler_core.fetch_webpage_content("https://example.test/page", **kwargs))


class TestBrowserFetching:
    def test_callback_prepares_captured_html_and_success_is_cached(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(
            html_by_url={url: lambda page: "<html>prepared</html>" if page.prepared else "<html>unprepared</html>"}
        )

        async def prepare(page):
            page.prepared = True

        with _playwright_boundary(browser):
            first_result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(url, after_load_func_async=prepare)
            )
            browser.html_by_url[url] = RuntimeError("page should no longer be needed")
            cached_result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(url, after_load_func_async=prepare)
            )

        assert first_result == "<html>prepared</html>"
        assert cached_result == first_result

    def test_expired_cache_refetches_browser_content(self, cache_boundary):
        url = "https://example.test/rendered"
        browser = FakeBrowser(html_by_url={url: "<html>first</html>"})

        with _playwright_boundary(browser):
            first_result = asyncio.run(crawler_core.fetch_webpage_content_playwright(url, cache_ttl=10))
            browser.html_by_url[url] = "<html>refetched</html>"
            cache_boundary.advance(11)
            refetched_result = asyncio.run(crawler_core.fetch_webpage_content_playwright(url, cache_ttl=10))

        assert first_result == "<html>first</html>"
        assert refetched_result == "<html>refetched</html>"

    def test_retryable_browser_failure_can_recover(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(
            html_by_url={url: "<html>recovered</html>"},
            status_by_url={url: [503, 200]},
        )

        with (
            _playwright_boundary(browser),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(
                    url,
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result == "<html>recovered</html>"

    def test_navigation_failure_can_recover(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(
            html_by_url={url: "<html>recovered</html>"},
            status_by_url={url: [RuntimeError("navigation failed"), 200]},
        )

        with (
            _playwright_boundary(browser),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(
                    url,
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result == "<html>recovered</html>"

    def test_browser_client_failure_is_non_retryable(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(
            html_by_url={url: "<html>late success</html>"},
            status_by_url={url: [404, 200]},
        )

        with _playwright_boundary(browser):
            result = asyncio.run(crawler_core.fetch_webpage_content_playwright(url, retries=2))

        assert result is None

    def test_callback_failure_can_recover_on_a_later_attempt(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(
            html_by_url={url: lambda page: "<html>prepared</html>" if page.prepared else "<html>unprepared</html>"}
        )
        outcomes = [RuntimeError("temporary callback failure"), None]

        async def prepare(page):
            outcome = outcomes.pop(0)
            if outcome is not None:
                raise outcome
            page.prepared = True

        with (
            _playwright_boundary(browser),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(
                    url,
                    after_load_func_async=prepare,
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result == "<html>prepared</html>"

    def test_exhausted_browser_failures_return_none(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(status_by_url={url: 503})

        with (
            _playwright_boundary(browser),
            patch("app.services.crawler_core.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_core.fetch_webpage_content_playwright(
                    url,
                    retries=2,
                    backoff_factor=0,
                )
            )

        assert result is None

    def test_failed_page_content_is_not_cached(self):
        url = "https://example.test/rendered"
        browser = FakeBrowser(html_by_url={url: RuntimeError("content unavailable")})

        with _playwright_boundary(browser):
            failed_result = asyncio.run(crawler_core.fetch_webpage_content_playwright(url, retries=1))
            browser.html_by_url[url] = "<html>later success</html>"
            recovered_result = asyncio.run(crawler_core.fetch_webpage_content_playwright(url, retries=1))

        assert failed_result is None
        assert recovered_result == "<html>later success</html>"

    @pytest.mark.parametrize("kwargs", [{"retries": 0}, {"backoff_factor": -0.1}])
    def test_rejects_invalid_browser_retry_configuration(self, kwargs):
        with pytest.raises(ValueError):
            asyncio.run(crawler_core.fetch_webpage_content_playwright("https://example.test/rendered", **kwargs))


class TestMultiBrowserFetching:
    def test_preserves_input_order_across_fresh_cached_and_failed_pages(self):
        cached_url = "https://example.test/cached"
        with _playwright_boundary(FakeBrowser(html_by_url={cached_url: "<html>cached</html>"})):
            assert asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([cached_url])) == [
                "<html>cached</html>"
            ]

        fresh_url = "https://example.test/fresh"
        failed_url = "https://example.test/failed"
        browser = FakeBrowser(
            html_by_url={fresh_url: "<html>fresh</html>"},
            status_by_url={failed_url: 503},
        )

        with _playwright_boundary(browser):
            result = asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    [fresh_url, cached_url, failed_url],
                )
            )

        assert result == ["<html>fresh</html>", "<html>cached</html>", None]

    def test_pages_have_ordered_non_overlapping_lifetimes(self):
        urls = [
            "https://example.test/first",
            "https://example.test/second",
            "https://example.test/third",
        ]
        browser = FakeBrowser(
            html_by_url={
                urls[0]: "<html>first</html>",
                urls[1]: "<html>second</html>",
                urls[2]: "<html>third</html>",
            },
            enforce_non_overlapping_pages=True,
        )

        with _playwright_boundary(browser):
            result = asyncio.run(crawler_core.fetch_multi_webpages_content_playwright(urls))

        assert result == [
            "<html>first</html>",
            "<html>second</html>",
            "<html>third</html>",
        ]

    @pytest.mark.parametrize("failure_mode", ["navigation", "http", "callback", "page-read"])
    def test_one_page_failure_does_not_stop_later_pages(self, failure_mode):
        failed_url = "https://example.test/failed"
        later_url = "https://example.test/later"
        status_by_url = {}
        html_by_url = {later_url: "<html>later</html>"}
        if failure_mode == "navigation":
            status_by_url[failed_url] = None
        elif failure_mode == "http":
            status_by_url[failed_url] = 503
        elif failure_mode == "page-read":
            html_by_url[failed_url] = RuntimeError("cannot read page")
        else:
            html_by_url[failed_url] = "<html>unused</html>"
        browser = FakeBrowser(html_by_url=html_by_url, status_by_url=status_by_url)

        async def prepare(page):
            if failure_mode == "callback" and page.url == failed_url:
                raise RuntimeError("cannot prepare page")

        with _playwright_boundary(browser):
            result = asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    [failed_url, later_url],
                    after_load_func_async=prepare,
                )
            )

        assert result == [None, "<html>later</html>"]

    def test_failed_page_gets_one_attempt_then_can_succeed_on_a_later_fetch(self):
        failed_url = "https://example.test/failed"
        later_url = "https://example.test/later"
        browser = FakeBrowser(
            html_by_url={
                failed_url: "<html>recovered</html>",
                later_url: "<html>later</html>",
            },
            status_by_url={failed_url: [503, 200]},
        )

        with _playwright_boundary(browser):
            first_result = asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([failed_url, later_url]))
        with _playwright_boundary(browser):
            recovered_result = asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([failed_url]))

        assert first_result == [None, "<html>later</html>"]
        assert recovered_result == ["<html>recovered</html>"]

    def test_expired_cache_refetches_multi_page_content(self, cache_boundary):
        url = "https://example.test/page"
        browser = FakeBrowser(html_by_url={url: "<html>first</html>"})

        with _playwright_boundary(browser):
            first_result = asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([url], cache_ttl=10))
            browser.html_by_url[url] = "<html>refetched</html>"
            cache_boundary.advance(11)
            refetched_result = asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([url], cache_ttl=10))

        assert first_result == ["<html>first</html>"]
        assert refetched_result == ["<html>refetched</html>"]

    def test_negative_delay_has_the_same_business_outcome_as_zero_delay(self, cache_boundary):
        urls = ["https://example.test/first", "https://example.test/second"]
        html_by_url = {
            urls[0]: "<html>first</html>",
            urls[1]: "<html>second</html>",
        }
        contexts = [
            FakePlaywrightContext(FakeBrowser(html_by_url=html_by_url)),
            FakePlaywrightContext(FakeBrowser(html_by_url=html_by_url)),
        ]

        with patch(
            "app.services.crawler_core.playwright_async_api.async_playwright",
            side_effect=contexts,
        ):
            negative_result = asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    urls,
                    delay_between_requests=-1,
                )
            )
            cache_boundary.values.clear()
            zero_result = asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    urls,
                    delay_between_requests=0,
                )
            )

        assert negative_result == zero_result == ["<html>first</html>", "<html>second</html>"]

    def test_positive_delay_sampling_respects_a_sub_tenth_maximum(self):
        urls = ["https://example.test/first", "https://example.test/second"]
        browser = FakeBrowser(
            html_by_url={
                urls[0]: "<html>first</html>",
                urls[1]: "<html>second</html>",
            }
        )

        def bounded_sampler(minimum, maximum):
            if minimum < 0 or minimum > maximum or maximum > 0.05:
                raise ValueError("sample outside configured delay range")
            return 0.0

        with (
            _playwright_boundary(browser),
            patch("app.services.crawler_core.random.uniform", new=bounded_sampler),
        ):
            result = asyncio.run(
                crawler_core.fetch_multi_webpages_content_playwright(
                    urls,
                    delay_between_requests=0.05,
                )
            )

        assert result == ["<html>first</html>", "<html>second</html>"]

    def test_empty_input_returns_empty_output(self):
        assert asyncio.run(crawler_core.fetch_multi_webpages_content_playwright([])) == []

    def test_browser_startup_failure_is_propagated(self):
        failure = RuntimeError("browser startup failed")

        with _playwright_boundary(launch_error=failure), pytest.raises(RuntimeError):
            asyncio.run(crawler_core.fetch_multi_webpages_content_playwright(["https://example.test/page"]))

    def test_browser_close_failure_is_propagated(self):
        failure = RuntimeError("browser close failed")
        browser = FakeBrowser(default_html="<html>page</html>", close_error=failure)

        with _playwright_boundary(browser), pytest.raises(RuntimeError):
            asyncio.run(crawler_core.fetch_multi_webpages_content_playwright(["https://example.test/page"]))


class TestFallbackFetching:
    def test_http_html_is_returned_without_browser_fallback(self):
        scraper = FakeHttpScraper([FakeHttpResponse(200, "<html>http</html>")])

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            patch(
                "app.services.crawler_core.playwright_async_api.async_playwright",
                side_effect=AssertionError("browser fallback should not be needed"),
            ),
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content_fallback_to_playwright("https://example.test/page"))

        assert result == "<html>http</html>"

    def test_non_retryable_http_failure_can_recover_with_browser(self):
        url = "https://example.test/page"
        scraper = FakeHttpScraper(
            [
                FakeHttpResponse(404),
                FakeHttpResponse(200, "<html>late http success</html>"),
            ]
        )
        browser = FakeBrowser(html_by_url={url: "<html>browser</html>"})

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            _playwright_boundary(browser),
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content_fallback_to_playwright(url))

        assert result == "<html>browser</html>"

    def test_returns_none_when_both_strategies_fail(self):
        url = "https://example.test/page"
        scraper = FakeHttpScraper([FakeHttpResponse(404)])
        browser = FakeBrowser(status_by_url={url: 404})

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            _playwright_boundary(browser),
        ):
            result = asyncio.run(crawler_core.fetch_webpage_content_fallback_to_playwright(url))

        assert result is None

    def test_expired_fallback_cache_refetches_browser_content(self, cache_boundary):
        url = "https://example.test/page"
        scraper = FakeHttpScraper([FakeHttpResponse(404)])
        browser = FakeBrowser(html_by_url={url: "<html>first</html>"})

        with (
            patch("app.services.crawler_core.cloudscraper.create_scraper", return_value=scraper),
            _playwright_boundary(browser),
        ):
            first_result = asyncio.run(crawler_core.fetch_webpage_content_fallback_to_playwright(url, cache_ttl=10))
            browser.html_by_url[url] = "<html>refetched</html>"
            cache_boundary.advance(11)
            refetched_result = asyncio.run(crawler_core.fetch_webpage_content_fallback_to_playwright(url, cache_ttl=10))

        assert first_result == "<html>first</html>"
        assert refetched_result == "<html>refetched</html>"


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
    def test_negative_filter_skip_is_rejected_before_fetching(self, public_function, fetch_target):
        with (
            patch(fetch_target, new_callable=AsyncMock, side_effect=AssertionError("source should not be contacted")),
            pytest.raises(ValueError),
        ):
            asyncio.run(public_function("https://example.test/table", filter_skip=-1))

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
    def test_returns_selected_table_from_fetched_html(self, public_function, fetch_target):
        html = _table_html(["Name", "Value"], [["Alpha", "10"]], table_id="events")

        with patch(fetch_target, new_callable=AsyncMock, return_value=html):
            result = asyncio.run(
                public_function(
                    "https://example.test/table",
                    table_attr_filter={"id": "events"},
                )
            )

        assert result.to_dict(orient="records") == [{"Name": "Alpha", "Value": "10"}]

    def test_http_table_wrapper_forwards_raw_content_filter_and_skip_options(self):
        html = _table_html(["Name"], [["Ignored"]], table_id="events") + _table_html(
            ["Name"],
            [["<a href='/stocks/a'>Alpha</a>"]],
            table_id="events",
        )

        with patch(
            "app.services.crawler_core.fetch_webpage_content_fallback_to_playwright",
            new_callable=AsyncMock,
            return_value=html,
        ):
            result = asyncio.run(
                crawler_core.scrape_data_table(
                    "https://example.test/table",
                    raw_cell_content=True,
                    table_attr_filter={"id": "events"},
                    filter_skip=1,
                )
            )

        fragment = bs4.BeautifulSoup(result.iloc[0]["Name"], "html.parser")
        link = fragment.find("a")
        assert link is not None
        assert link.get("href") == "/stocks/a"
        assert link.get_text(strip=True) == "Alpha"

    def test_browser_table_wrapper_forwards_callback_and_extraction_options(self):
        async def prepare(page):
            page.prepared = True

        async def fetch_rendered(_url, *, after_load_func_async=None):
            page = SimpleNamespace(prepared=False)
            await after_load_func_async(page)
            visible_value = "READY" if page.prepared else "NOT_READY"
            return _table_html(["State"], [["Ignored"]], table_id="events") + _table_html(
                ["State"],
                [[f"<strong>{visible_value}</strong>"]],
                table_id="events",
            )

        with patch(
            "app.services.crawler_core.fetch_webpage_content_playwright",
            new=fetch_rendered,
        ):
            result = asyncio.run(
                crawler_core.scrape_data_table_playwright(
                    "https://example.test/table",
                    raw_cell_content=True,
                    after_load_func_async=prepare,
                    table_attr_filter={"id": "events"},
                    filter_skip=1,
                )
            )

        fragment = bs4.BeautifulSoup(result.iloc[0]["State"], "html.parser")
        assert fragment.get_text(strip=True) == "READY"

    @pytest.mark.parametrize(
        ("public_function", "fetch_target", "html"),
        [
            (
                crawler_core.scrape_data_table,
                "app.services.crawler_core.fetch_webpage_content_fallback_to_playwright",
                None,
            ),
            (
                crawler_core.scrape_data_table,
                "app.services.crawler_core.fetch_webpage_content_fallback_to_playwright",
                "<html></html>",
            ),
            (
                crawler_core.scrape_data_table_playwright,
                "app.services.crawler_core.fetch_webpage_content_playwright",
                None,
            ),
            (
                crawler_core.scrape_data_table_playwright,
                "app.services.crawler_core.fetch_webpage_content_playwright",
                "<html></html>",
            ),
        ],
        ids=["http-fetch-failed", "http-no-table", "browser-fetch-failed", "browser-no-table"],
    )
    def test_failed_or_tableless_scrapes_return_empty_frames(self, public_function, fetch_target, html):
        with patch(fetch_target, new_callable=AsyncMock, return_value=html):
            result = asyncio.run(public_function("https://example.test/table"))

        assert result.empty


class TestDividendCrawlers:
    def test_asx_includes_today_and_the_inclusive_end_date_with_zero_numeric_defaults(self):
        today = datetime.date(2026, 11, 16)
        headers = ["Name", "Company", "Dividend Amount", "Dividend Yield", "Market Cap", "Payment Date"]
        pages = [
            _table_html(
                headers,
                [["CBA", "Commonwealth Bank", "AU$2.50", "4.00%", "$200B", "2026-12-01"]],
            ),
            _table_html(
                headers,
                [["TLS", "Telstra", "AU$0.09", "N/A", "N/A", "N/A"]],
            ),
        ]

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=pages,
            ),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_asx(today + datetime.timedelta(days=1)))

        assert list(result.columns) == DIVIDEND_COLUMNS
        assert result["Ex-Div Date"].tolist() == ["2026-11-16", "2026-11-17"]
        assert result.iloc[0].to_dict() == {
            "Ticker": "CBA",
            "Company": "Commonwealth Bank",
            "Ex-Div Date": "2026-11-16",
            "Payment Date": "2026-12-01",
            "Div Amount": 2.5,
            "Div Yield": 0.04,
            "Market Cap": 200_000_000_000,
            "Exchange": "ASX",
            "Currency": "AUD",
        }
        nullable_row = result.iloc[1]
        assert nullable_row["Ticker"] == "TLS"
        assert nullable_row["Div Amount"] == 0.09
        assert pd.isna(nullable_row["Payment Date"])
        assert nullable_row["Div Yield"] == 0.0
        assert nullable_row["Market Cap"] == 0

    def test_asx_keeps_later_dates_after_an_earlier_page_fails(self):
        today = datetime.date(2026, 11, 16)
        later_page = _table_html(
            ["Name", "Company", "Dividend Amount"],
            [["TLS", "Telstra", "AU$0.09"]],
        )

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[None, later_page],
            ),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_asx(today + datetime.timedelta(days=1)))

        assert result["Ticker"].tolist() == ["TLS"]
        assert result["Ex-Div Date"].tolist() == ["2026-11-17"]
        assert result["Payment Date"].isna().all()
        assert result[["Div Yield", "Market Cap"]].eq(0).all().all()

    @pytest.mark.parametrize(
        "public_function",
        [crawler_div.scrape_dividends_asx, crawler_div.scrape_dividends_us, crawler_div.scrape_dividends_vn],
        ids=["asx", "us", "vn"],
    )
    def test_missing_numeric_values_default_to_zero(self, public_function):
        missing_values = [None, pd.NA, float("nan"), "", "N/A", "NA", "NaN", "-"]
        if public_function is crawler_div.scrape_dividends_vn:
            source_data = pd.DataFrame(
                [
                    {"Mã CK": f"ZERO{i}", "Sàn": "HOSE", "Ngày GDKHQ▼": "16/11/2026", "Tỷ lệ": value}
                    for i, value in enumerate(missing_values)
                ]
            )
            table_boundary = patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new_callable=AsyncMock,
                side_effect=[source_data, pd.DataFrame()],
            )
        else:
            source_data = pd.DataFrame(
                [
                    {
                        "Name": f"ZERO{i}",
                        "Company": "Missing Values Ltd",
                        "Dividend Amount": value,
                        "Dividend Yield": value,
                        "Market Cap": value,
                    }
                    for i, value in enumerate(missing_values)
                ]
            )
            table_boundary = patch(
                "app.services.crawler_div.crawler_core.extract_data_table_from_html",
                return_value=source_data,
            )

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=["unused"],
            ),
            table_boundary,
            patch(
                "app.services.crawler_div.market.market_indices.revert_lookup_company",
                return_value=FakeCompany("NASDAQ", "ZERO"),
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(public_function(datetime.date(2026, 11, 16)))

        assert len(result) == len(missing_values)
        assert result[["Div Amount", "Div Yield", "Market Cap"]].eq(0).all().all()
        assert result["Payment Date"].isna().all()

    @pytest.mark.parametrize(
        ("public_function", "now"),
        [
            (crawler_div.scrape_dividends_asx, datetime.datetime(2026, 11, 16, 9)),
            (crawler_div.scrape_dividends_us, datetime.datetime(2026, 11, 16, 9)),
        ],
    )
    def test_end_date_before_today_returns_a_canonical_empty_frame(self, public_function, now):
        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(now)),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            result = asyncio.run(public_function(datetime.date(2026, 11, 15)))

        pd.testing.assert_frame_equal(result, pd.DataFrame(columns=DIVIDEND_COLUMNS))

    @pytest.mark.parametrize(
        "public_function",
        [crawler_div.scrape_dividends_asx, crawler_div.scrape_dividends_us],
        ids=["asx", "us"],
    )
    @pytest.mark.parametrize(
        ("headers", "row", "expected_error"),
        [
            (
                ["Name", "Company", "Dividend Amount"],
                ["BAD", "Bad Amount Ltd", "not-money"],
                "invalid amount: 'not-money'",
            ),
            (
                ["Company", "Payment Date"],
                ["Incomplete Ltd", "N/A"],
                "Dividend table is missing columns: ['Div Amount', 'Ticker']",
            ),
            (
                ["Name", "Dividend Amount"],
                [" ", "$0.25"],
                "Dividend table has missing values in required columns: ['Ticker']",
            ),
            (
                ["Name", "Dividend Amount"],
                ["BAD", "Infinity"],
                "invalid amount: 'Infinity'",
            ),
        ],
        ids=["malformed-amount", "missing-columns", "missing-ticker-value", "infinite-amount"],
    )
    def test_propagates_source_normalization_failures(self, public_function, headers, row, expected_error):
        page = _table_html(headers, [row])

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
            pytest.raises(ValueError) as exc_info,
        ):
            asyncio.run(public_function(datetime.date(2026, 11, 16)))

        assert str(exc_info.value) == expected_error

    @pytest.mark.parametrize(
        "public_function",
        [crawler_div.scrape_dividends_asx, crawler_div.scrape_dividends_us],
        ids=["asx", "us"],
    )
    @pytest.mark.parametrize(
        ("source_column", "expected_column"),
        [("Name", "Ticker"), ("Dividend Amount", "Div Amount")],
        ids=["missing-ticker", "missing-amount"],
    )
    def test_daily_pages_are_validated_before_merging(self, public_function, source_column, expected_column):
        incomplete_row = {"Name": "BBB", "Company": "Beta Ltd", "Dividend Amount": "$0.20"}
        incomplete_row.pop(source_column)
        pages = [
            _table_html(["Name", "Company", "Dividend Amount"], [["AAA", "Alpha Ltd", "$0.10"]]),
            _table_html(list(incomplete_row), [list(incomplete_row.values())]),
        ]

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=pages,
            ),
            pytest.raises(ValueError, match=rf"missing columns.*{expected_column}"),
        ):
            asyncio.run(public_function(datetime.date(2026, 11, 17)))

    def test_missing_company_names_fall_back_to_each_ticker(self):
        pages = [
            _table_html(["Name", "Company", "Dividend Amount"], [["AAA", "Alpha Ltd", "$0.10"]]),
            _table_html(["Name", "Dividend Amount"], [["BBB", "$0.20"]]),
            _table_html(["Name", "Company", "Dividend Amount"], [["CCC", " ", "$0.30"]]),
        ]

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=pages,
            ),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_asx(datetime.date(2026, 11, 18)))

        assert result["Company"].tolist() == ["Alpha Ltd", "BBB", "CCC"]

    def test_us_marks_unknown_tickers_and_uses_loaded_exchange_data_for_known_tickers(self):
        page = _table_html(
            ["Name", "Company", "Dividend Amount"],
            [
                ["KNOWN", "Known Corp", "$0.25"],
                ["UNKNOWN", "Unknown Corp", "$0.10"],
            ],
        )
        known_company = FakeCompany("NASDAQ", "KNOWN")

        def lookup(_country, ticker):
            return known_company if ticker == "KNOWN" else None

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
            patch(
                "app.services.crawler_div.market.market_indices.revert_lookup_company",
                side_effect=lookup,
            ),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_us(datetime.date(2026, 11, 16)))

        assert list(result.columns) == DIVIDEND_COLUMNS
        assert result["Ticker"].tolist() == ["KNOWN", "UNKNOWN"]
        assert result["Exchange"].tolist() == ["NASDAQ", "N/A"]
        assert result["Currency"].tolist() == ["USD", "USD"]

    def test_vn_returns_dividends_after_rendering_the_calendar(self):
        html = _table_html(
            ["Mã CK", "Sàn", "Ngày GDKHQ▼", "Tỷ lệ"],
            [["VNM", "HOSE", "16/11/2026", "15%"]],
            table_id="event-content",
        )

        def content(page):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(page.url).query)
            return html if query.get("page") == ["1"] else "<html></html>"

        browser = FakeBrowser(default_html=content)
        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            _playwright_boundary(browser),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 16)))

        assert result["Ticker"].tolist() == ["VNM"]
        assert result.iloc[0]["Div Amount"] == 1500.0
        assert pd.isna(result.iloc[0]["Payment Date"])

    @pytest.mark.parametrize(
        ("rate", "expected_amount", "expected_yield"),
        [("15%", 1500.0, 0.15), ("N/A", 0.0, 0.0)],
        ids=["reported-rate", "unavailable-rate"],
    )
    def test_vn_uses_today_as_the_boundary_and_normalizes_cash_dividends(self, rate, expected_amount, expected_yield):
        source_data = pd.DataFrame(
            [
                {
                    "Mã CK": "VNM",
                    "Sàn": "hose",
                    "Ngày GDKHQ▼": "16/11/2026",
                    "Ngày thực hiện": "N/A",
                    "Tỷ lệ": rate,
                }
            ]
        )

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new=_vn_range_scraper(
                    source_data,
                    expected_start=datetime.date(2026, 11, 16),
                    expected_end=datetime.date(2026, 11, 16),
                ),
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 16)))
            with patch(
                "app.services.events_div.services_crawler_div.scrape_dividends_vn",
                new_callable=AsyncMock,
                return_value=result,
            ):
                events = asyncio.run(events_div.get_vn_upcoming_dividends_events())

        assert list(result.columns) == DIVIDEND_COLUMNS
        row = result.iloc[0]
        assert row.drop(labels=["Payment Date", "Market Cap", "Div Amount", "Div Yield"]).to_dict() == {
            "Ticker": "VNM",
            "Company": "VNM",
            "Ex-Div Date": "2026-11-16",
            "Exchange": "HOSE",
            "Currency": "VND",
        }
        assert row["Div Amount"] == expected_amount
        assert row["Div Yield"] == expected_yield
        assert pd.isna(row["Payment Date"])
        assert row["Market Cap"] == 0
        assert len(events) == 1
        assert events[0].amount == expected_amount
        assert events[0].dividend_yield == expected_yield

    def test_vn_pages_are_validated_before_merging(self):
        valid_page = pd.DataFrame([{"Mã CK": "VNM", "Sàn": "HOSE", "Ngày GDKHQ▼": "16/11/2026", "Tỷ lệ": "15%"}])
        incomplete_page = valid_page.drop(columns=["Ngày GDKHQ▼"])

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new_callable=AsyncMock,
                side_effect=[valid_page, incomplete_page, pd.DataFrame()],
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
            pytest.raises(ValueError, match="missing columns.*Ex-Div Date"),
        ):
            asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 16)))

    def test_vn_end_date_before_today_returns_empty(self):
        source_data = pd.DataFrame(
            [
                {
                    "Mã CK": "TOO_LATE",
                    "Sàn": "HOSE",
                    "Ngày GDKHQ▼": "16/11/2026",
                    "Tỷ lệ": "10%",
                }
            ]
        )

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new=_vn_range_scraper(source_data),
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 15)))

        assert result.empty
        assert list(result.columns) == DIVIDEND_COLUMNS

    @pytest.mark.parametrize(
        ("source_row", "error_pattern"),
        [
            (
                {
                    "Sàn": "HOSE",
                    "Ngày GDKHQ▼": "16/11/2026",
                    "Tỷ lệ": "15%",
                },
                r"^Dividend table is missing columns: \['Ticker'\]$",
            ),
            (
                {
                    "Mã CK": "VNM",
                    "Sàn": "HOSE",
                    "Ngày GDKHQ▼": "not-a-date",
                    "Tỷ lệ": "15%",
                },
                "not-a-date",
            ),
            (
                {
                    "Mã CK": "VNM",
                    "Sàn": "HOSE",
                    "Ngày GDKHQ▼": "16/11/2026",
                    "Tỷ lệ": "not-a-rate",
                },
                "not-a-rate",
            ),
            (
                {
                    "Mã CK": pd.NA,
                    "Sàn": " ",
                    "Ngày GDKHQ▼": pd.NA,
                    "Tỷ lệ": "15%",
                },
                "missing values.*Ex-Div Date.*Exchange.*Ticker",
            ),
            (
                {
                    "Mã CK": "VNM",
                    "Sàn": "HOSE",
                    "Ngày GDKHQ▼": "NaT",
                    "Tỷ lệ": "15%",
                },
                "invalid ex-dividend date",
            ),
        ],
        ids=["missing-ticker", "malformed-ex-date", "malformed-yield", "missing-values", "missing-date-after-parsing"],
    )
    def test_vn_propagates_required_source_normalization_failures(self, source_row, error_pattern):
        source_data = pd.DataFrame([source_row])

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new=_vn_range_scraper(
                    source_data,
                    expected_start=datetime.date(2026, 11, 16),
                    expected_end=datetime.date(2026, 11, 16),
                ),
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
            pytest.raises(ValueError, match=error_pattern),
        ):
            asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 16)))

    @pytest.mark.parametrize(
        "public_function",
        [
            crawler_div.scrape_dividends_asx,
            crawler_div.scrape_dividends_us,
            crawler_div.scrape_dividends_vn,
        ],
    )
    def test_timezone_lookup_failures_are_propagated(self, public_function):
        failure = zoneinfo.ZoneInfoNotFoundError("missing timezone")

        with (
            patch("app.services.crawler_div.zoneinfo.ZoneInfo", side_effect=failure),
            pytest.raises(zoneinfo.ZoneInfoNotFoundError),
        ):
            asyncio.run(public_function(datetime.date(2026, 11, 16)))


class TestEarningsCrawlers:
    @pytest.mark.parametrize(
        ("public_function", "exchange", "currency", "prefix"),
        [
            (crawler_earnings.scrape_earnings_asx, "ASX", "AUD", "AU$"),
            (crawler_earnings.scrape_earnings_us, "NASDAQ", "USD", "US$"),
        ],
        ids=["asx", "us"],
    )
    def test_normalizes_financial_values_and_market_metadata(self, public_function, exchange, currency, prefix):
        page = _table_html(
            ["Name", "Company", "Market Cap", "EPS / Forecast", "Revenue / Forecast", "Price"],
            [
                [
                    "KNOWN",
                    "Known Company",
                    f"{prefix}200B",
                    f"-{prefix}2.650 / {prefix}-2.08",
                    f"{prefix}27.067B / {prefix}1.001B",
                    "$100",
                ]
            ],
        )
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
            patch(
                "app.services.crawler_earnings.market.market_indices.revert_lookup_company",
                return_value=FakeCompany(exchange, "KNOWN"),
            ),
        ):
            result = asyncio.run(public_function(datetime.date(2026, 11, 16)))

        assert list(result.columns) == EARNINGS_COLUMNS
        assert result.to_dict(orient="records") == [
            {
                "Announcement Date": "2026-11-16",
                "Exchange": exchange,
                "Ticker": "KNOWN",
                "Company": "Known Company",
                "Market Cap": 200_000_000_000,
                "EPS": -2.65,
                "EPS Forecast": -2.08,
                "Revenue": 27_067_000_000,
                "Revenue Forecast": 1_001_000_000,
                "Currency": currency,
            }
        ]

    @pytest.mark.parametrize(
        "public_function",
        [crawler_earnings.scrape_earnings_asx, crawler_earnings.scrape_earnings_us],
        ids=["asx", "us"],
    )
    def test_missing_pair_components_default_independently_to_zero(self, public_function):
        cases = [
            (None, 0, 0),
            (pd.NA, 0, 0),
            (float("nan"), 0, 0),
            ("", 0, 0),
            ("N/A", 0, 0),
            ("NA", 0, 0),
            ("NaN", 0, 0),
            ("-", 0, 0),
            ("--", 0, 0),
            ("\u2014", 0, 0),
            ("/", 0, 0),
            ("NA / -", 0, 0),
            ("N/A/N/A", 0, 0),
            ("$1 / $2", 1, 2),
            ("$1 /", 1, 0),
            ("/ $2", 0, 2),
            ("N/A/$2", 0, 2),
            ("$1/n/a", 1, 0),
            ("$1", 1, 0),
        ]
        source_data = pd.DataFrame(
            [
                {"Name": f"MISSING{i}", "EPS / Forecast": value, "Revenue / Forecast": value}
                for i, (value, _, _) in enumerate(cases)
            ]
        )
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=["unused"],
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.extract_data_table_from_html",
                return_value=source_data,
            ),
            patch(
                "app.services.crawler_earnings.market.market_indices.revert_lookup_company",
                return_value=None,
            ),
        ):
            result = asyncio.run(public_function(datetime.date(2026, 11, 16)))

        assert len(result) == len(cases)
        for actual_column, forecast_column in (("EPS", "EPS Forecast"), ("Revenue", "Revenue Forecast")):
            assert result[actual_column].tolist() == [actual for _, actual, _ in cases]
            assert result[forecast_column].tolist() == [forecast for _, _, forecast in cases]
        assert result["Market Cap"].eq(0).all()

    @pytest.mark.parametrize(
        "public_function",
        [crawler_earnings.scrape_earnings_asx, crawler_earnings.scrape_earnings_us],
        ids=["asx", "us"],
    )
    @pytest.mark.parametrize("missing_value", [None, float("nan"), "N/A"], ids=["null", "nan", "marker"])
    def test_entirely_missing_pair_columns_default_to_zero(self, public_function, missing_value):
        source_data = pd.DataFrame(
            [{"Name": "EMPTY", "EPS / Forecast": missing_value, "Revenue / Forecast": missing_value}]
        )
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=["unused"],
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.extract_data_table_from_html",
                return_value=source_data,
            ),
            patch(
                "app.services.crawler_earnings.market.market_indices.revert_lookup_company",
                return_value=None,
            ),
        ):
            result = asyncio.run(public_function(datetime.date(2026, 11, 16)))

        assert len(result) == 1
        assert result[["Market Cap", "EPS", "EPS Forecast", "Revenue", "Revenue Forecast"]].eq(0).all().all()
        assert result["Company"].tolist() == ["EMPTY"]

    @pytest.mark.parametrize(
        ("pair", "expected"),
        [
            ("-1.25/-2.5", (-1.25, -2.5)),
            ("(AU$2.65) / -$2.08", (-2.65, -2.08)),
            ("\u2212$0.50 / ($0.25)", (-0.5, -0.25)),
            ("-$1.25 /", (-1.25, 0.0)),
            ("/ -$2.5", (0.0, -2.5)),
        ],
        ids=["plain", "accounting", "unicode-minus", "missing-forecast", "missing-actual"],
    )
    def test_negative_eps_values_are_retained(self, pair, expected):
        page = _table_html(["Name", "EPS / Forecast"], [["LOSS", pair]])
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
        ):
            result = asyncio.run(crawler_earnings.scrape_earnings_asx(datetime.date(2026, 11, 16)))

        assert tuple(result.loc[0, ["EPS", "EPS Forecast"]]) == expected

    def test_optional_fields_and_company_fallback_are_consistent_across_dates(self):
        pages = [
            None,
            _table_html(
                ["Name", "Company", "Market Cap", "EPS / Forecast"],
                [["AAA", "Alpha Ltd", "$1B", "$1 / $2"]],
            ),
            _table_html(["Name"], [["BBB"]]),
            _table_html(["Name", "Company"], [["CCC", " "]]),
            _table_html(["Name", "Company Name"], [["DDD", "Delta Ltd"]]),
        ]
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=pages,
            ),
        ):
            result = asyncio.run(crawler_earnings.scrape_earnings_asx(datetime.date(2026, 11, 20)))

        assert list(result.columns) == EARNINGS_COLUMNS
        assert result["Ticker"].tolist() == ["AAA", "BBB", "CCC", "DDD"]
        assert result["Company"].tolist() == ["Alpha Ltd", "BBB", "CCC", "Delta Ltd"]
        assert result["Announcement Date"].tolist() == ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
        assert result["Market Cap"].tolist() == [1_000_000_000, 0, 0, 0]
        assert result["EPS"].tolist() == [1.0, 0.0, 0.0, 0.0]
        assert result["EPS Forecast"].tolist() == [2.0, 0.0, 0.0, 0.0]
        assert result[["Revenue", "Revenue Forecast"]].eq(0).all().all()
        assert result.index.tolist() == [0, 1, 2, 3]

    @pytest.mark.parametrize(
        "public_function",
        [crawler_earnings.scrape_earnings_asx, crawler_earnings.scrape_earnings_us],
        ids=["asx", "us"],
    )
    @pytest.mark.parametrize(
        "invalid_row",
        [
            {"Company": "No Ticker Ltd"},
            {"Name": " ", "Company": "Blank Ticker Ltd"},
            {"Name": pd.NA, "Company": "Null Ticker Ltd"},
        ],
        ids=["missing-header", "blank-value", "null-value"],
    )
    def test_invalid_tickers_on_later_pages_are_rejected(self, public_function, invalid_row):
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=["first", "second"],
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.extract_data_table_from_html",
                side_effect=[pd.DataFrame([{"Name": "AAA", "Company": "Alpha Ltd"}]), pd.DataFrame([invalid_row])],
            ),
            pytest.raises(ValueError) as exc_info,
        ):
            asyncio.run(public_function(datetime.date(2026, 11, 17)))

        assert "Ticker" in str(exc_info.value)
        assert "TipRanks" not in str(exc_info.value)

    @pytest.mark.parametrize(
        "public_function",
        [crawler_earnings.scrape_earnings_asx, crawler_earnings.scrape_earnings_us],
        ids=["asx", "us"],
    )
    @pytest.mark.parametrize(
        ("column", "value"),
        [
            ("Market Cap", "not-money"),
            ("Market Cap", "Infinity"),
            ("EPS / Forecast", "$1 / bad"),
            ("EPS / Forecast", "Infinity / $1"),
            ("Revenue / Forecast", "inf / $1B"),
        ],
        ids=["invalid-cap", "infinite-cap", "invalid-eps-forecast", "infinite-eps", "infinite-revenue"],
    )
    def test_malformed_or_nonfinite_financial_values_are_rejected(self, public_function, column, value):
        page = _table_html(["Name", "Company", column], [["BAD", "Bad Data Ltd", value]])
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
            pytest.raises(ValueError),
        ):
            asyncio.run(public_function(datetime.date(2026, 11, 16)))

    @pytest.mark.parametrize(
        "public_function",
        [crawler_earnings.scrape_earnings_asx, crawler_earnings.scrape_earnings_us],
        ids=["asx", "us"],
    )
    @pytest.mark.parametrize(
        ("end_date", "pages"),
        [
            (datetime.date(2026, 11, 15), []),
            (datetime.date(2026, 11, 16), [None]),
            (
                datetime.date(2026, 11, 16),
                [_table_html(["Name"], [["Currently there are no reports available for this date."]])],
            ),
        ],
        ids=["before-today", "unavailable-page", "no-announcements"],
    )
    def test_empty_results_retain_the_canonical_columns(self, public_function, end_date, pages):
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=pages,
            ),
        ):
            result = asyncio.run(public_function(end_date))

        pd.testing.assert_frame_equal(result, pd.DataFrame(columns=EARNINGS_COLUMNS))

    def test_us_preserves_known_and_unknown_exchange_rows(self):
        page = _table_html(["Name"], [["KNOWN"], ["UNKNOWN"]])
        known_company = FakeCompany("NASDAQ", "KNOWN")
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
            patch(
                "app.services.crawler_earnings.market.market_indices.revert_lookup_company",
                side_effect=lambda _country, ticker: known_company if ticker == "KNOWN" else None,
            ),
        ):
            result = asyncio.run(crawler_earnings.scrape_earnings_us(datetime.date(2026, 11, 16)))

        assert list(result.columns) == EARNINGS_COLUMNS
        assert result["Ticker"].tolist() == ["KNOWN", "UNKNOWN"]
        assert result["Exchange"].tolist() == ["NASDAQ", "N/A"]
        assert result["Currency"].tolist() == ["USD", "USD"]

    @pytest.mark.parametrize(
        "public_function",
        [crawler_earnings.scrape_earnings_asx, crawler_earnings.scrape_earnings_us],
        ids=["asx", "us"],
    )
    def test_timezone_lookup_failures_are_propagated(self, public_function):
        with (
            patch(
                "app.services.crawler_earnings.zoneinfo.ZoneInfo",
                side_effect=zoneinfo.ZoneInfoNotFoundError("missing timezone"),
            ),
            pytest.raises(zoneinfo.ZoneInfoNotFoundError),
        ):
            asyncio.run(public_function(datetime.date(2026, 11, 16)))
