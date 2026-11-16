import asyncio
import datetime
import urllib.parse
import zoneinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bs4
import pandas as pd
import pytest
from playwright import async_api as playwright_async_api

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


class FakeControlLocator:
    def __init__(self, *, count=0, items=None, on_click=None, on_evaluate=None, click_error=None):
        self._count = count
        self._items = items
        self._on_click = on_click
        self._on_evaluate = on_evaluate
        self._click_error = click_error

    async def count(self):
        return self._count

    def nth(self, index):
        return self._items[index] if self._items is not None else self

    async def click(self):
        if self._click_error is not None:
            raise self._click_error
        if self._on_click is not None:
            self._on_click()

    async def evaluate(self, _script):
        if self._on_evaluate is not None:
            self._on_evaluate()


class FakeTipRanksPage:
    def __init__(self, *, ad_mode=None, controls=False, interaction_error=None):
        self.visible_ads = set()
        if ad_mode == "primary":
            self.visible_ads.update({"primary-1", "primary-2"})
        elif ad_mode == "fallback":
            self.visible_ads.update({"footer", "header"})
        self.controls = controls
        self.interaction_error = interaction_error
        self.column_menu_open = False
        self.exchange_requested = False
        self.exchange_column_selected = False

    def _hide_ad(self, ad_name):
        self.visible_ads.discard(ad_name)

    def _open_columns(self):
        self.column_menu_open = True

    def _request_exchange(self):
        if self.column_menu_open:
            self.exchange_requested = True

    def _save_columns(self):
        if self.exchange_requested:
            self.exchange_column_selected = True

    def locator(self, selector):
        if selector == "div[data-google-query-id]":
            ads = sorted(ad for ad in self.visible_ads if ad.startswith("primary"))
            items = [
                FakeControlLocator(count=1, on_evaluate=lambda ad_name=ad_name: self._hide_ad(ad_name))
                for ad_name in ads
            ]
            return FakeControlLocator(count=len(items), items=items)
        if selector == "div[id='AdThrive_Footer_1_desktop']":
            return FakeControlLocator(
                count=int("footer" in self.visible_ads),
                on_evaluate=lambda: self._hide_ad("footer"),
            )
        if selector == "div[id='AdThrive_Header_1_desktop']":
            return FakeControlLocator(
                count=int("header" in self.visible_ads),
                on_evaluate=lambda: self._hide_ad("header"),
            )
        if selector == "button[data-id='select-columns-button']":
            return FakeControlLocator(count=int(self.controls), on_click=self._open_columns)
        if selector == "label[title='Exchange Name']":
            return FakeControlLocator(
                count=int(self.controls),
                on_click=self._request_exchange,
                click_error=self.interaction_error,
            )
        if selector == "button[id='save']":
            return FakeControlLocator(count=int(self.controls), on_click=self._save_columns)
        return FakeControlLocator()


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
    def test_asx_includes_today_and_the_inclusive_end_date_with_nullable_fields(self):
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
        assert pd.isna(nullable_row["Div Yield"])
        assert pd.isna(nullable_row["Market Cap"])

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

        assert result.empty
        assert list(result.columns) == DIVIDEND_COLUMNS

    def test_asx_propagates_source_normalization_failures(self):
        page = _table_html(
            ["Name", "Company", "Dividend Amount"],
            [["BAD", "Bad Amount Ltd", "not-money"]],
        )

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.fetch_multi_webpages_content_playwright",
                new_callable=AsyncMock,
                return_value=[page],
            ),
            pytest.raises(ValueError),
        ):
            asyncio.run(crawler_div.scrape_dividends_asx(datetime.date(2026, 11, 16)))

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

        assert result["Ticker"].tolist() == ["KNOWN", "UNKNOWN"]
        assert result["Exchange"].tolist() == ["NASDAQ", "N/A"]
        assert result["Currency"].tolist() == ["USD", "USD"]

    def test_vn_uses_the_two_working_day_boundary_and_normalizes_cash_dividends(self):
        source_data = pd.DataFrame(
            [
                {
                    "Mã CK": "VNM",
                    "Sàn": "hose",
                    "Ngày GDKHQ▼": "12/11/2026",
                    "Ngày thực hiện": "N/A",
                    "Tỷ lệ": "15%",
                }
            ]
        )

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new=_vn_range_scraper(
                    source_data,
                    expected_start=datetime.date(2026, 11, 12),
                    expected_end=datetime.date(2026, 11, 12),
                ),
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 12)))

        assert list(result.columns) == DIVIDEND_COLUMNS
        row = result.iloc[0]
        assert row.drop(labels=["Payment Date", "Market Cap"]).to_dict() == {
            "Ticker": "VNM",
            "Company": "VNM",
            "Ex-Div Date": "2026-11-12",
            "Div Amount": 1500.0,
            "Div Yield": 0.15,
            "Exchange": "HOSE",
            "Currency": "VND",
        }
        assert pd.isna(row["Payment Date"])
        assert pd.isna(row["Market Cap"])

    def test_vn_end_date_before_the_two_working_day_boundary_returns_empty(self):
        source_data = pd.DataFrame(
            [
                {
                    "Mã CK": "TOO_LATE",
                    "Sàn": "HOSE",
                    "Ngày GDKHQ▼": "12/11/2026",
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
            result = asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 11)))

        assert result.empty
        assert list(result.columns) == DIVIDEND_COLUMNS

    @pytest.mark.parametrize(
        "source_row",
        [
            {
                "Sàn": "HOSE",
                "Ngày GDKHQ▼": "12/11/2026",
                "Tỷ lệ": "15%",
            },
            {
                "Mã CK": "VNM",
                "Sàn": "HOSE",
                "Ngày GDKHQ▼": "not-a-date",
                "Tỷ lệ": "15%",
            },
            {
                "Mã CK": "VNM",
                "Sàn": "HOSE",
                "Ngày GDKHQ▼": "12/11/2026",
                "Tỷ lệ": "not-a-rate",
            },
        ],
        ids=["missing-ticker", "malformed-ex-date", "malformed-yield"],
    )
    def test_vn_propagates_required_source_normalization_failures(self, source_row):
        source_data = pd.DataFrame([source_row])

        with (
            patch("app.services.crawler_div.datetime.datetime", _fixed_datetime(datetime.datetime(2026, 11, 16, 9))),
            patch(
                "app.services.crawler_div.crawler_core.scrape_data_table_playwright",
                new=_vn_range_scraper(
                    source_data,
                    expected_start=datetime.date(2026, 11, 12),
                    expected_end=datetime.date(2026, 11, 12),
                ),
            ),
            patch("app.services.crawler_div.random.uniform", return_value=0.0),
            pytest.raises(ValueError),
        ):
            asyncio.run(crawler_div.scrape_dividends_vn(datetime.date(2026, 11, 12)))

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


class TestEarningsCallback:
    def test_missing_controls_leave_the_page_unchanged(self):
        page = FakeTipRanksPage()
        initial_state = (set(page.visible_ads), page.exchange_column_selected)

        result = asyncio.run(crawler_earnings.tipranks_after_load_func(page))

        assert result is None
        assert (page.visible_ads, page.exchange_column_selected) == initial_state

    @pytest.mark.parametrize("ad_mode", ["primary", "fallback"])
    def test_hides_present_ads_and_selects_the_exchange_column(self, ad_mode):
        page = FakeTipRanksPage(ad_mode=ad_mode, controls=True)

        asyncio.run(crawler_earnings.tipranks_after_load_func(page))

        assert page.visible_ads == set()
        assert page.exchange_column_selected is True

    def test_playwright_interaction_errors_are_propagated(self):
        failure = playwright_async_api.Error("interaction failed")
        page = FakeTipRanksPage(controls=True, interaction_error=failure)

        with pytest.raises(playwright_async_api.Error):
            asyncio.run(crawler_earnings.tipranks_after_load_func(page))


class TestEarningsCrawlers:
    def test_default_end_date_is_resolved_at_call_time_and_is_inclusive(self):
        pages = [
            pd.DataFrame(
                [
                    {
                        "Name": "AAPL",
                        "Company Name": "Apple",
                        "Exchange Name": "NASDAQ",
                        "Market Cap": "$3T",
                    }
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "Name": "MSFT",
                        "Company Name": "Microsoft",
                        "Exchange Name": "NASDAQ",
                        "Market Cap": "$3T",
                    }
                ]
            ),
        ]

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table",
                new_callable=AsyncMock,
                side_effect=pages,
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_earnings.scrape_earnings_from_tipranks("https://example.test/earnings/{date}"))

        assert list(result.columns) == ["Symbol", "Announcement Date", "Company Name", "Exchange Name"]
        assert result.to_dict(orient="records") == [
            {
                "Symbol": "AAPL",
                "Announcement Date": "2026-11-16",
                "Company Name": "Apple",
                "Exchange Name": "NASDAQ",
            },
            {
                "Symbol": "MSFT",
                "Announcement Date": "2026-11-17",
                "Company Name": "Microsoft",
                "Exchange Name": "NASDAQ",
            },
        ]

    def test_weekend_start_and_failed_page_do_not_hide_a_later_weekday(self):
        tuesday_page = pd.DataFrame(
            [
                {
                    "Name": "MSFT",
                    "Company Name": "Microsoft",
                    "Exchange Name": "NASDAQ",
                }
            ]
        )

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 14, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table",
                new_callable=AsyncMock,
                side_effect=[pd.DataFrame(), tuesday_page],
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 17),
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

    def test_end_date_before_the_first_eligible_day_returns_empty(self):
        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table",
                new_callable=AsyncMock,
                side_effect=AssertionError("no date is eligible"),
            ),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 15),
                )
            )

        assert result.empty

    def test_invalid_timezone_is_propagated(self):
        with pytest.raises(zoneinfo.ZoneInfoNotFoundError):
            asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                    tz_name="Invalid/Timezone",
                )
            )

    def test_nonempty_table_without_a_symbol_is_rejected(self):
        page = pd.DataFrame([{"Company Name": "Missing Symbol Ltd"}])

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table",
                new_callable=AsyncMock,
                return_value=page,
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
            pytest.raises(ValueError),
        ):
            asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                )
            )

    def test_http_mode_does_not_run_the_browser_callback(self):
        async def browser_only_callback(_page):
            raise AssertionError("HTTP mode must not run a browser callback")

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table",
                new_callable=AsyncMock,
                return_value=pd.DataFrame([{"Name": "AAPL"}]),
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                    after_load_func_async=browser_only_callback,
                )
            )

        assert result["Symbol"].tolist() == ["AAPL"]

    def test_playwright_wrapper_uses_callback_visible_page_state(self):
        async def prepare(page):
            page.prepared = True

        async def scrape_rendered_page(_url, *, after_load_func_async=None):
            page = SimpleNamespace(prepared=False)
            await after_load_func_async(page)
            symbol = "READY" if page.prepared else "NOT_READY"
            return pd.DataFrame([{"Name": symbol}])

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table_playwright",
                new=scrape_rendered_page,
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(
                crawler_earnings.scrape_earnings_from_tipranks_playwright(
                    "https://example.test/earnings/{date}",
                    end_date=datetime.date(2026, 11, 16),
                    after_load_func_async=prepare,
                )
            )

        assert result["Symbol"].tolist() == ["READY"]

    def test_asx_wrapper_returns_normalized_rows(self):
        page = pd.DataFrame([{"Name": "CBA", "Company Name": "Commonwealth Bank"}])

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table",
                new_callable=AsyncMock,
                return_value=page,
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_earnings.scrape_earnings_asx(datetime.date(2026, 11, 16)))

        assert result.to_dict(orient="records") == [
            {
                "Symbol": "CBA",
                "Announcement Date": "2026-11-16",
                "Company Name": "Commonwealth Bank",
            }
        ]

    def test_us_wrapper_requests_and_returns_the_exchange_column(self):
        async def scrape_rendered_page(_url, *, after_load_func_async=None):
            page = FakeTipRanksPage(ad_mode="primary", controls=True)
            await after_load_func_async(page)
            data = {"Name": ["MSFT"], "Company Name": ["Microsoft"]}
            if page.exchange_column_selected:
                data["Exchange Name"] = ["NASDAQ"]
            return pd.DataFrame(data)

        with (
            patch(
                "app.services.crawler_earnings.datetime.datetime",
                _fixed_datetime(datetime.datetime(2026, 11, 16, 9)),
            ),
            patch(
                "app.services.crawler_earnings.crawler_core.scrape_data_table_playwright",
                new=scrape_rendered_page,
            ),
            patch("app.services.crawler_earnings.random.uniform", return_value=0.0),
        ):
            result = asyncio.run(crawler_earnings.scrape_earnings_us(datetime.date(2026, 11, 16)))

        assert result.to_dict(orient="records") == [
            {
                "Symbol": "MSFT",
                "Announcement Date": "2026-11-16",
                "Company Name": "Microsoft",
                "Exchange Name": "NASDAQ",
            }
        ]
