"""Black-box contract tests for the public event routes."""

import contextlib
import types
import unittest.mock

import fastapi
import fastapi.testclient
import pytest

from app import config, main
from app.models import event as models_event
from app.models import events_listings as models_events_listings
from app.routers import events as router_events
from app.routers import events_div as router_events_div
from app.routers import events_listings as router_events_listings
from app.schemas import async_task

client = fastapi.testclient.TestClient(main.app)


class _TaskStore:
    def __init__(self) -> None:
        self._entries: dict[str, types.SimpleNamespace] = {}
        self._identities: dict[tuple[object, ...], str] = {}
        self._next_id = 1

    def _new_task_id(self) -> str:
        task_id = f"opaque-task-{self._next_id}"
        self._next_id += 1
        return task_id

    def put(
        self,
        task_id: str,
        task_type: str,
        state: async_task.TaskState,
        *,
        result: object | None = None,
        message: str | None = None,
        corrupt: bool = False,
    ) -> None:
        serialized_result = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        self._entries[task_id] = types.SimpleNamespace(
            task_type=task_type,
            state=state,
            result=serialized_result,
            message=message,
            corrupt=corrupt,
        )

    def seed(
        self,
        task_type: str,
        *task_input: object,
        state: async_task.TaskState,
        result: object | None = None,
        message: str | None = None,
    ) -> str:
        identity = (task_type, *task_input)
        task_id = self._identities.setdefault(identity, self._new_task_id())
        self.put(task_id, task_type, state, result=result, message=message)
        return task_id

    def expire(self, task_id: str) -> None:
        self._entries.pop(task_id, None)

    async def start_task(self, task_type: str, *task_input: object) -> tuple[str, bool]:
        identity = (task_type, *task_input)
        task_id = self._identities.get(identity)
        if task_id is not None and task_id in self._entries:
            return task_id, False

        if task_id is None:
            task_id = self._new_task_id()
            self._identities[identity] = task_id
        self.put(task_id, task_type, async_task.TASK_STATE_RUNNING)
        return task_id, True

    async def complete_task(
        self,
        task_id: str,
        task_type: str,
        result: object,
        *,
        status_code: int | None = None,
        message: str | None = None,
    ) -> None:
        del status_code
        self.put(
            task_id,
            task_type,
            async_task.TASK_STATE_COMPLETED,
            result=result,
            message=message,
        )

    async def fail_task(
        self,
        task_id: str,
        task_type: str,
        *,
        status_code: int | None = None,
        message: str = "Task failed",
        result: object | None = None,
    ) -> None:
        del status_code
        self.put(
            task_id,
            task_type,
            async_task.TASK_STATE_FAILED,
            result=result,
            message=message,
        )

    async def load_task(self, task_id: str, task_type: str) -> types.SimpleNamespace:
        task_entry = self._entries.get(task_id)
        if task_entry is None or task_entry.task_type != task_type:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        if task_entry.corrupt:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid task state",
            )
        return task_entry


@contextlib.contextmanager
def _use_task_store(task_store: _TaskStore):
    with (
        unittest.mock.patch.object(
            router_events.router_async_task,
            "start_task",
            new=task_store.start_task,
        ),
        unittest.mock.patch.object(
            router_events.router_async_task,
            "complete_task",
            new=task_store.complete_task,
        ),
        unittest.mock.patch.object(
            router_events.router_async_task,
            "fail_task",
            new=task_store.fail_task,
        ),
        unittest.mock.patch.object(
            router_events.router_async_task,
            "load_task",
            new=task_store.load_task,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def _disable_event_proxy():
    with (
        unittest.mock.patch.object(config.settings_finhub_proxy, "proxy_mode", ""),
        unittest.mock.patch.object(config.settings_finhub_proxy, "url_web_crawl_node", ""),
        unittest.mock.patch.object(config.settings_finhub_proxy, "url_ai_task_node", ""),
    ):
        yield


def _dividend_event(
    symbol: str = "ASX:CBA",
    *,
    timestamp_str: str = "2026-06-10 00:00:00+10:00",
    amount: float = 1.25,
) -> models_event.UpcomingDividendEvent:
    return models_event.UpcomingDividendEvent(
        symbol=symbol,
        exchange=symbol.split(":", 1)[0],
        company_name="Example Dividend Co",
        timestamp_str=timestamp_str,
        status="declared",
        amount=amount,
        dividend_yield=0.03,
        currency="AUD" if symbol.startswith("ASX:") else "USD",
        payment_date=None,
    )


def _earnings_event(symbol: str = "NASDAQ:AAPL") -> models_event.UpcomingEarningsEvent:
    return models_event.UpcomingEarningsEvent(
        symbol=symbol,
        exchange=symbol.split(":", 1)[0],
        company_name="Example Earnings Co",
        timestamp_str="2026-08-15 00:00:00-04:00",
        status="estimated",
        report_period=None,
    )


def _listing_event(
    symbol: str,
    timestamp_str: str,
    *,
    analysis_status: models_events_listings.ListingAnalysisStatus = "Skipped",
    issue_price: float | None = None,
    analysis_error: str | None = None,
) -> models_events_listings.ListingEvent:
    return models_events_listings.ListingEvent(
        symbol=symbol,
        exchange=symbol.split(":", 1)[0],
        company_name=f"{symbol} Holdings",
        timestamp_str=timestamp_str,
        issue_price=issue_price,
        currency="AUD" if symbol.startswith("ASX:") else "USD",
        capital_to_raise=None,
        analysis_status=analysis_status,
        analysis_error=analysis_error,
    )


@pytest.mark.parametrize(
    ("endpoint", "params", "node_setting", "expected_location"),
    [
        (
            "/events/upcoming_dividends",
            {"country": "AU", "index": "ASX200"},
            "url_web_crawl_node",
            "https://proxy.example/finhub/events/upcoming_dividends?country=AU&index=ASX200",
        ),
        (
            "/events/start_upcoming_dividends_async",
            {"country": "AU", "index": "ASX200"},
            "url_web_crawl_node",
            "https://proxy.example/finhub/events/start_upcoming_dividends_async?country=AU&index=ASX200",
        ),
        (
            "/events/poll_upcoming_dividends_async",
            {"task_id": "task-1"},
            "url_web_crawl_node",
            "https://proxy.example/finhub/events/poll_upcoming_dividends_async?task_id=task-1",
        ),
        (
            "/events/upcoming_earnings",
            {"country": "US", "index": "SP500"},
            "url_web_crawl_node",
            "https://proxy.example/finhub/events/upcoming_earnings?country=US&index=SP500",
        ),
        (
            "/events/start_upcoming_earnings_async",
            {"country": "US", "index": "SP500"},
            "url_web_crawl_node",
            "https://proxy.example/finhub/events/start_upcoming_earnings_async?country=US&index=SP500",
        ),
        (
            "/events/poll_upcoming_earnings_async",
            {"task_id": "task-2"},
            "url_web_crawl_node",
            "https://proxy.example/finhub/events/poll_upcoming_earnings_async?task_id=task-2",
        ),
        (
            "/events/new_listings",
            {"country": "AU"},
            "url_ai_task_node",
            "https://proxy.example/finhub/events/new_listings?country=AU",
        ),
        (
            "/events/start_new_listings_async",
            {"country": "US"},
            "url_ai_task_node",
            "https://proxy.example/finhub/events/start_new_listings_async?country=US",
        ),
        (
            "/events/poll_new_listings_async",
            {"task_id": "task-3"},
            "url_ai_task_node",
            "https://proxy.example/finhub/events/poll_new_listings_async?task_id=task-3",
        ),
    ],
)
def test_event_routes_use_their_configured_proxy(endpoint, params, node_setting, expected_location):
    with (
        unittest.mock.patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
        unittest.mock.patch.object(
            config.settings_finhub_proxy,
            node_setting,
            "https://proxy.example/finhub/",
        ),
    ):
        response = client.get(endpoint, params=params, follow_redirects=False)

    assert response.status_code == fastapi.status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers["location"] == expected_location


class TestUpcomingDividends:
    @pytest.mark.parametrize(
        ("country", "index", "service_name", "symbol"),
        [
            (" Australia ", "asx200", "get_asx_upcoming_dividends_events", "ASX:CBA"),
            ("u.s.a.", "sp500", "get_us_upcoming_dividends_events", "NASDAQ:AAPL"),
            ("vNm", "vn30", "get_vn_upcoming_dividends_events", "HOSE:FPT"),
        ],
    )
    def test_country_aliases_and_index_case_return_market_results(self, country, index, service_name, symbol):
        event = _dividend_event(symbol)
        service = unittest.mock.AsyncMock(return_value=[event])
        with (
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                service_name,
                new=service,
            ),
            unittest.mock.patch.object(
                router_events_div.asset_utils,
                "is_in_index",
                return_value=False,
            ),
        ):
            response = client.get(
                "/events/upcoming_dividends",
                params={"country": country, "index": index},
            )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_200_OK
        assert [item["symbol"] for item in response.json()["data"]] == [symbol]
        assert "analysis" not in response.json()["data"][0]
        service.assert_awaited_once_with(index)

    def test_major_index_event_includes_dividend_analysis(self):
        event = _dividend_event("NASDAQ:AAPL")
        analysis = models_event.DividendEventAnalysis(
            symbol="NASDAQ:AAPL",
            exchange="NASDAQ",
            company_name="Apple",
            timestamp_str="2026-06-10",
            price=200.0,
            div_amount=event.amount,
            div_yield=0.00625,
        )
        service = unittest.mock.AsyncMock(return_value=[event])
        analyse = unittest.mock.AsyncMock(return_value=analysis)

        def is_in_index(*, index: str, symbol: str) -> bool:
            return index == "SP500" and symbol == event.symbol

        with (
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                "get_us_upcoming_dividends_events",
                new=service,
            ),
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                "analyse_dividend_event",
                new=analyse,
            ),
            unittest.mock.patch.object(
                router_events_div.asset_utils,
                "is_in_index",
                side_effect=is_in_index,
            ),
        ):
            response = client.get(
                "/events/upcoming_dividends",
                params={"country": " usa ", "index": "sp500"},
            )

        assert response.status_code == fastapi.status.HTTP_200_OK
        returned_analysis = response.json()["data"][0]["analysis"]
        assert returned_analysis["symbol"] == "NASDAQ:AAPL"
        assert returned_analysis["price"] == 200.0
        analyse.assert_awaited_once_with(
            symbol="NASDAQ:AAPL",
            div_amount=1.25,
            ex_date="2026-06-10",
        )

    def test_unavailable_major_index_analysis_is_omitted(self):
        event = _dividend_event("NASDAQ:AAPL")
        service = unittest.mock.AsyncMock(return_value=[event])
        analyse = unittest.mock.AsyncMock(return_value=None)
        with (
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                "get_us_upcoming_dividends_events",
                new=service,
            ),
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                "analyse_dividend_event",
                new=analyse,
            ),
            unittest.mock.patch.object(
                router_events_div.asset_utils,
                "is_in_index",
                return_value=True,
            ),
        ):
            response = client.get(
                "/events/upcoming_dividends",
                params={"country": "US", "index": "SP500"},
            )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert "analysis" not in response.json()["data"][0]
        analyse.assert_awaited_once()

    def test_dividend_analysis_failure_returns_public_500_envelope(self):
        event = _dividend_event("NASDAQ:AAPL")
        service = unittest.mock.AsyncMock(return_value=[event])
        analyse = unittest.mock.AsyncMock(side_effect=RuntimeError("Analysis unavailable"))
        with (
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                "get_us_upcoming_dividends_events",
                new=service,
            ),
            unittest.mock.patch.object(
                router_events_div.services_events_div,
                "analyse_dividend_event",
                new=analyse,
            ),
            unittest.mock.patch.object(
                router_events_div.asset_utils,
                "is_in_index",
                return_value=True,
            ),
        ):
            response = client.get(
                "/events/upcoming_dividends",
                params={"country": "US", "index": "SP500"},
            )

        assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json()["status"] == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "data" not in response.json()

    @pytest.mark.parametrize(
        ("country", "index"),
        [
            ("AU", "SP500"),
            ("US", "ASX200"),
            ("Vietnam", "NOT-AN-INDEX"),
        ],
    )
    def test_invalid_or_cross_market_index_returns_empty_data(self, country, index):
        response = client.get(
            "/events/upcoming_dividends",
            params={"country": country, "index": index},
        )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_200_OK
        assert response.json()["data"] == []

    @pytest.mark.parametrize("country", ["JP", ""])
    def test_unsupported_country_returns_501_envelope(self, country):
        response = client.get(
            "/events/upcoming_dividends",
            params={"country": country},
        )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_501_NOT_IMPLEMENTED
        assert "data" not in response.json()

    def test_omitted_country_is_rejected_by_request_validation(self):
        response = client.get("/events/upcoming_dividends")

        assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


class TestUpcomingEarnings:
    @pytest.mark.parametrize(
        ("country", "index", "service_name", "symbol"),
        [
            (" aUsTrAlIa ", "asx300", "get_asx_upcoming_earnings_events", "ASX:BHP"),
            ("U.S.", "nasdaq100", "get_us_upcoming_earnings_events", "NASDAQ:AAPL"),
        ],
    )
    def test_country_aliases_and_index_case_return_market_results(self, country, index, service_name, symbol):
        event = _earnings_event(symbol)
        service = unittest.mock.AsyncMock(return_value=[event])
        with unittest.mock.patch.object(
            router_events.services_event,
            service_name,
            new=service,
        ):
            response = client.get(
                "/events/upcoming_earnings",
                params={"country": country, "index": index},
            )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_200_OK
        assert [item["symbol"] for item in response.json()["data"]] == [symbol]
        assert "report_period" not in response.json()["data"][0]
        service.assert_awaited_once_with(index)

    @pytest.mark.parametrize(
        ("country", "index"),
        [
            ("Australia", "SP500"),
            ("United States", "ASX200"),
            ("US", "NOT-AN-INDEX"),
        ],
    )
    def test_invalid_or_cross_market_index_returns_empty_data(self, country, index):
        response = client.get(
            "/events/upcoming_earnings",
            params={"country": country, "index": index},
        )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_200_OK
        assert response.json()["data"] == []

    @pytest.mark.parametrize("country", ["VN", ""])
    def test_unsupported_country_returns_501_envelope(self, country):
        response = client.get(
            "/events/upcoming_earnings",
            params={"country": country},
        )

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_501_NOT_IMPLEMENTED
        assert "data" not in response.json()

    def test_omitted_country_is_rejected_by_request_validation(self):
        response = client.get("/events/upcoming_earnings")

        assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


class TestNewListings:
    @pytest.mark.parametrize(
        ("country", "service_name", "symbol"),
        [
            (" aUsTrAlIa ", "ai_get_asx_new_listings", "ASX:IPO"),
            ("U.S.A.", "ai_get_us_new_listings", "NASDAQ:IPO"),
        ],
    )
    def test_country_aliases_and_case_return_market_results(self, country, service_name, symbol):
        event = _listing_event(symbol, "2026-12-01", issue_price=2.5)
        asx_service = unittest.mock.AsyncMock(return_value=[])
        us_service = unittest.mock.AsyncMock(return_value=[])
        selected_service = asx_service if service_name == "ai_get_asx_new_listings" else us_service
        selected_service.return_value = [event]

        with (
            unittest.mock.patch.object(
                router_events_listings.services_asx_listings,
                "ai_get_asx_new_listings",
                new=asx_service,
            ),
            unittest.mock.patch.object(
                router_events_listings.services_us_listings,
                "ai_get_us_new_listings",
                new=us_service,
            ),
        ):
            response = client.get("/events/new_listings", params={"country": country})

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_200_OK
        assert [item["symbol"] for item in response.json()["data"]] == [symbol]
        selected_service.assert_awaited_once_with()
        other_service = us_service if selected_service is asx_service else asx_service
        other_service.assert_not_awaited()

    def test_order_nullable_fields_and_analysis_attempt_outcomes_are_preserved(self):
        events = [
            _listing_event("ASX:AAA", "2026-12-01", analysis_status="Skipped"),
            _listing_event("ASX:BBB", "2026-12-01", analysis_status="Completed", issue_price=1.0),
            _listing_event("ASX:CCC", "2026-12-02", analysis_status="Completed", issue_price=1.5),
            _listing_event("ASX:DDD", "2026-12-03", analysis_status="Completed", issue_price=2.0),
            _listing_event("ASX:EEE", "2026-12-04", analysis_status="Completed", issue_price=2.5),
            _listing_event(
                "ASX:FFF",
                "2026-12-05",
                analysis_status="Failed",
                analysis_error="Analysis unavailable",
            ),
            _listing_event("ASX:GGG", "2026-12-06", analysis_status="Skipped"),
        ]
        service = unittest.mock.AsyncMock(return_value=events)
        with unittest.mock.patch.object(
            router_events_listings.services_asx_listings,
            "ai_get_asx_new_listings",
            new=service,
        ):
            response = client.get("/events/new_listings", params={"country": "AU"})

        assert response.status_code == fastapi.status.HTTP_200_OK
        data = response.json()["data"]
        assert [item["symbol"] for item in data] == [event.symbol for event in events]
        assert [item["analysis_status"] for item in data] == [
            "Skipped",
            "Completed",
            "Completed",
            "Completed",
            "Completed",
            "Failed",
            "Skipped",
        ]
        assert data[5]["analysis_error"] == "Analysis unavailable"
        assert "issue_price" not in data[5]
        assert "capital_to_raise" not in data[5]
        assert "analysis" not in data[5]

    @pytest.mark.parametrize("country", [None, "", "JP"])
    def test_omitted_or_unsupported_country_returns_501_envelope(self, country):
        params = {} if country is None else {"country": country}
        response = client.get("/events/new_listings", params=params)

        assert response.status_code == fastapi.status.HTTP_200_OK
        assert response.json()["status"] == fastapi.status.HTTP_501_NOT_IMPLEMENTED
        assert "data" not in response.json()


@pytest.mark.parametrize(
    ("service_path", "endpoint", "params"),
    [
        (
            "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
            "/events/upcoming_dividends",
            {"country": "AU"},
        ),
        (
            "app.routers.events.services_event.get_us_upcoming_earnings_events",
            "/events/upcoming_earnings",
            {"country": "US"},
        ),
        (
            "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
            "/events/new_listings",
            {"country": "AU"},
        ),
    ],
)
def test_synchronous_service_failure_returns_public_500_envelope(service_path, endpoint, params):
    service = unittest.mock.AsyncMock(side_effect=RuntimeError("Source unavailable"))
    with unittest.mock.patch(service_path, new=service):
        response = client.get(endpoint, params=params)

    assert response.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["status"] == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "data" not in response.json()


_ASYNC_SUCCESS_CASES = [
    (
        "/events/start_upcoming_dividends_async",
        "/events/poll_upcoming_dividends_async",
        {"country": " Australia ", "index": "asx200"},
        {"country": "AUS", "index": "ASX200"},
        "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
        _dividend_event("ASX:CBA"),
    ),
    (
        "/events/start_upcoming_earnings_async",
        "/events/poll_upcoming_earnings_async",
        {"country": "u.s.a.", "index": "sp500"},
        {"country": "United States", "index": "SP500"},
        "app.routers.events.services_event.get_us_upcoming_earnings_events",
        _earnings_event("NASDAQ:AAPL"),
    ),
    (
        "/events/start_new_listings_async",
        "/events/poll_new_listings_async",
        {"country": " australia "},
        {"country": "AUS"},
        "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
        _listing_event("ASX:IPO", "2026-12-01", issue_price=2.5),
    ),
]


@pytest.mark.parametrize(
    (
        "start_endpoint",
        "poll_endpoint",
        "start_params",
        "duplicate_params",
        "service_path",
        "event",
    ),
    _ASYNC_SUCCESS_CASES,
)
def test_start_to_poll_workflow_and_completed_duplicate_reuse(
    start_endpoint,
    poll_endpoint,
    start_params,
    duplicate_params,
    service_path,
    event,
):
    task_store = _TaskStore()
    service = unittest.mock.AsyncMock(return_value=[event])
    with (
        _use_task_store(task_store),
        unittest.mock.patch(service_path, new=service),
        unittest.mock.patch.object(
            router_events_div.asset_utils,
            "is_in_index",
            return_value=False,
        ),
    ):
        started = client.get(start_endpoint, params=start_params)
        task_id = started.json()["extra"]["task_id"]
        polled = client.get(poll_endpoint, params={"task_id": f"  {task_id}  "})
        duplicate = client.get(start_endpoint, params=duplicate_params)

    assert started.status_code == fastapi.status.HTTP_202_ACCEPTED
    assert started.json()["status"] == fastapi.status.HTTP_202_ACCEPTED
    assert started.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
    assert polled.status_code == fastapi.status.HTTP_200_OK
    assert polled.json()["status"] == fastapi.status.HTTP_200_OK
    assert polled.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_COMPLETED,
    }
    assert [item["symbol"] for item in polled.json()["data"]] == [event.symbol]
    assert duplicate.status_code == fastapi.status.HTTP_200_OK
    assert duplicate.json() == polled.json()
    service.assert_awaited_once()


@pytest.mark.parametrize(
    ("start_endpoint", "poll_endpoint", "start_params", "duplicate_params", "service_path"),
    [
        (
            "/events/start_upcoming_dividends_async",
            "/events/poll_upcoming_dividends_async",
            {"country": "AU", "index": "ASX200"},
            {"country": "Australia", "index": "asx200"},
            "app.routers.events_div.services_events_div.get_asx_upcoming_dividends_events",
        ),
        (
            "/events/start_upcoming_earnings_async",
            "/events/poll_upcoming_earnings_async",
            {"country": "US", "index": "SP500"},
            {"country": "USA", "index": "sp500"},
            "app.routers.events.services_event.get_us_upcoming_earnings_events",
        ),
        (
            "/events/start_new_listings_async",
            "/events/poll_new_listings_async",
            {"country": "US"},
            {"country": "United States"},
            "app.routers.events_listings.services_us_listings.ai_get_us_new_listings",
        ),
    ],
)
def test_background_service_failure_polls_and_deduplicates_as_failed(
    start_endpoint,
    poll_endpoint,
    start_params,
    duplicate_params,
    service_path,
):
    task_store = _TaskStore()
    service = unittest.mock.AsyncMock(side_effect=RuntimeError("Source unavailable"))
    with (
        _use_task_store(task_store),
        unittest.mock.patch(service_path, new=service),
    ):
        started = client.get(start_endpoint, params=start_params)
        task_id = started.json()["extra"]["task_id"]
        polled = client.get(poll_endpoint, params={"task_id": task_id})
        duplicate = client.get(start_endpoint, params=duplicate_params)

    assert started.status_code == fastapi.status.HTTP_202_ACCEPTED
    assert polled.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert polled.json()["status"] == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert polled.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_FAILED,
    }
    assert "data" not in polled.json()
    assert duplicate.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert duplicate.json() == polled.json()
    service.assert_awaited_once()


@pytest.mark.parametrize(
    ("start_endpoint", "poll_endpoint", "params"),
    [
        (
            "/events/start_upcoming_dividends_async",
            "/events/poll_upcoming_dividends_async",
            {},
        ),
        (
            "/events/start_upcoming_dividends_async",
            "/events/poll_upcoming_dividends_async",
            {"country": "JP"},
        ),
        (
            "/events/start_upcoming_earnings_async",
            "/events/poll_upcoming_earnings_async",
            {},
        ),
        (
            "/events/start_upcoming_earnings_async",
            "/events/poll_upcoming_earnings_async",
            {"country": "VN"},
        ),
    ],
)
def test_omitted_or_unsupported_async_country_completes_with_501(
    start_endpoint,
    poll_endpoint,
    params,
):
    task_store = _TaskStore()
    with _use_task_store(task_store):
        started = client.get(start_endpoint, params=params)
        task_id = started.json()["extra"]["task_id"]
        polled = client.get(poll_endpoint, params={"task_id": task_id})
        duplicate = client.get(start_endpoint, params=params)

    assert started.status_code == fastapi.status.HTTP_202_ACCEPTED
    assert polled.status_code == fastapi.status.HTTP_200_OK
    assert polled.json()["status"] == fastapi.status.HTTP_501_NOT_IMPLEMENTED
    assert polled.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_COMPLETED,
    }
    assert "data" not in polled.json()
    assert duplicate.status_code == fastapi.status.HTTP_200_OK
    assert duplicate.json() == polled.json()


@pytest.mark.parametrize(
    ("start_endpoint", "params", "task_type", "task_input"),
    [
        (
            "/events/start_upcoming_dividends_async",
            {"country": "Australia", "index": "asx200"},
            "upcoming_dividends",
            ("AU", "ASX200"),
        ),
        (
            "/events/start_upcoming_earnings_async",
            {"country": "United States", "index": "sp500"},
            "upcoming_earnings",
            ("US", "SP500"),
        ),
        (
            "/events/start_new_listings_async",
            {"country": "Australia"},
            "new_listings",
            ("AU",),
        ),
    ],
)
def test_duplicate_running_start_returns_existing_running_state(
    start_endpoint,
    params,
    task_type,
    task_input,
):
    task_store = _TaskStore()
    task_id = task_store.seed(
        task_type,
        *task_input,
        state=async_task.TASK_STATE_RUNNING,
    )
    with _use_task_store(task_store):
        response = client.get(start_endpoint, params=params)

    assert response.status_code == fastapi.status.HTTP_202_ACCEPTED
    assert response.json()["status"] == fastapi.status.HTTP_202_ACCEPTED
    assert response.json()["extra"] == {
        "task_id": task_id,
        "state": async_task.TASK_STATE_RUNNING,
    }


@pytest.mark.parametrize(
    ("poll_endpoint", "task_type"),
    [
        ("/events/poll_upcoming_dividends_async", "upcoming_dividends"),
        ("/events/poll_upcoming_earnings_async", "upcoming_earnings"),
        ("/events/poll_new_listings_async", "new_listings"),
    ],
)
def test_poll_reports_running_expired_wrong_type_and_corrupt_states(poll_endpoint, task_type):
    task_store = _TaskStore()
    task_store.put("running-task", task_type, async_task.TASK_STATE_RUNNING)
    task_store.put("wrong-type-task", "another-task-type", async_task.TASK_STATE_RUNNING)
    task_store.put(
        "corrupt-task",
        task_type,
        async_task.TASK_STATE_RUNNING,
        corrupt=True,
    )
    task_store.put(
        "malformed-result-task",
        task_type,
        async_task.TASK_STATE_COMPLETED,
        result={"status": fastapi.status.HTTP_200_OK},
    )

    with _use_task_store(task_store):
        running = client.get(
            poll_endpoint,
            params={"task_id": "  running-task  "},
        )
        task_store.expire("running-task")
        expired = client.get(poll_endpoint, params={"task_id": "running-task"})
        wrong_type = client.get(
            poll_endpoint,
            params={"task_id": "wrong-type-task"},
        )
        corrupt = client.get(poll_endpoint, params={"task_id": "corrupt-task"})
        malformed_result = client.get(
            poll_endpoint,
            params={"task_id": "malformed-result-task"},
        )

    assert running.status_code == fastapi.status.HTTP_202_ACCEPTED
    assert running.json()["extra"]["state"] == async_task.TASK_STATE_RUNNING
    assert expired.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert expired.json()["status"] == fastapi.status.HTTP_404_NOT_FOUND
    assert wrong_type.status_code == fastapi.status.HTTP_404_NOT_FOUND
    assert wrong_type.json()["status"] == fastapi.status.HTTP_404_NOT_FOUND
    assert corrupt.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert corrupt.json()["status"] == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert malformed_result.status_code == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    assert malformed_result.json()["status"] == fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.parametrize(
    "poll_endpoint",
    [
        "/events/poll_upcoming_dividends_async",
        "/events/poll_upcoming_earnings_async",
        "/events/poll_new_listings_async",
    ],
)
def test_poll_requires_task_id(poll_endpoint):
    response = client.get(poll_endpoint)

    assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT


class TestNewListingsAsyncValidation:
    def test_country_is_required_in_openapi(self):
        main.app.openapi_schema = None
        response = client.get("/openapi.json")

        assert response.status_code == fastapi.status.HTTP_200_OK
        parameters = response.json()["paths"]["/events/start_new_listings_async"]["get"]["parameters"]
        country_parameter = next(parameter for parameter in parameters if parameter["name"] == "country")
        assert country_parameter["required"] is True

    def test_omitted_country_is_rejected(self):
        response = client.get("/events/start_new_listings_async")

        assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.parametrize("country", ["", "JP", "Vietnam"])
    def test_unsupported_country_is_rejected_before_task_creation(self, country):
        task_store = _TaskStore()
        with _use_task_store(task_store):
            response = client.get(
                "/events/start_new_listings_async",
                params={"country": country},
            )

        assert response.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["status"] == fastapi.status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_australian_and_us_tasks_remain_distinct(self):
        task_store = _TaskStore()
        au_event = _listing_event("ASX:IPO", "2026-12-01", issue_price=2.5)
        us_event = _listing_event("NASDAQ:IPO", "2026-12-02", issue_price=10.0)
        au_service = unittest.mock.AsyncMock(return_value=[au_event])
        us_service = unittest.mock.AsyncMock(return_value=[us_event])

        with (
            _use_task_store(task_store),
            unittest.mock.patch.object(
                router_events_listings.services_asx_listings,
                "ai_get_asx_new_listings",
                new=au_service,
            ),
            unittest.mock.patch.object(
                router_events_listings.services_us_listings,
                "ai_get_us_new_listings",
                new=us_service,
            ),
        ):
            au_started = client.get(
                "/events/start_new_listings_async",
                params={"country": "Australia"},
            )
            us_started = client.get(
                "/events/start_new_listings_async",
                params={"country": "United States"},
            )
            au_task_id = au_started.json()["extra"]["task_id"]
            us_task_id = us_started.json()["extra"]["task_id"]
            au_polled = client.get(
                "/events/poll_new_listings_async",
                params={"task_id": au_task_id},
            )
            us_polled = client.get(
                "/events/poll_new_listings_async",
                params={"task_id": us_task_id},
            )

        assert au_started.status_code == fastapi.status.HTTP_202_ACCEPTED
        assert us_started.status_code == fastapi.status.HTTP_202_ACCEPTED
        assert au_task_id != us_task_id
        assert [item["symbol"] for item in au_polled.json()["data"]] == ["ASX:IPO"]
        assert [item["symbol"] for item in us_polled.json()["data"]] == ["NASDAQ:IPO"]
        au_service.assert_awaited_once_with()
        us_service.assert_awaited_once_with()
