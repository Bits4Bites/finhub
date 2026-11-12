"""Unit tests for the event routers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.models import events_listings as models_events_listings
from app.models.event import UpcomingDividendEvent, UpcomingEarningsEvent
from app.routers import events_listings as router_events_listings
from app.schemas import async_task
from app.schemas import events_listings as schemas_events_listings

client = TestClient(app)


# ===========================================================================
# Tests for GET /events/upcoming_dividends
# ===========================================================================


class TestUpcomingDividends:
    def test_redirects_through_shared_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(
                config.settings_finhub_proxy,
                "url_web_crawl_node",
                "https://proxy.example/finhub/",
            ),
        ):
            resp = client.get(
                "/events/upcoming_dividends",
                params={"country": "AU", "index": "ASX200"},
                follow_redirects=False,
            )

        assert resp.status_code == 307
        assert (
            resp.headers["location"] == "https://proxy.example/finhub/events/upcoming_dividends?country=AU&index=ASX200"
        )

    @patch("app.routers.events.services_event.get_asx_upcoming_dividends_events", new_callable=AsyncMock)
    def test_au_returns_dividends(self, mock_get):
        event = UpcomingDividendEvent.model_construct(
            symbol="ASX:CBA",
            company_name="CBA",
            timestamp_str="2026-06-10",
            amount=2.0,
            dividend_yield=0.03,
            payment_date="2026-07-01",
        )
        mock_get.return_value = [event]

        resp = client.get("/events/upcoming_dividends", params={"country": "AU", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:CBA"
        assert body["data"][0]["timestamp_str"] == "2026-06-10"
        assert "date" not in body["data"][0]
        mock_get.assert_called_once_with("")

    @patch("app.routers.events.services_event.get_us_upcoming_dividends_events", new_callable=AsyncMock)
    def test_us_returns_dividends(self, mock_get):
        mock_get.return_value = []

        resp = client.get("/events/upcoming_dividends", params={"country": "US", "index": "SP500"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"] == []
        mock_get.assert_called_once_with("SP500")

    @patch("app.routers.events.services_event.get_vn_upcoming_dividends_events", new_callable=AsyncMock)
    def test_vn_returns_dividends(self, mock_get):
        mock_get.return_value = []

        resp = client.get("/events/upcoming_dividends", params={"country": "VN", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        mock_get.assert_called_once_with("")

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/upcoming_dividends", params={"country": "JP", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    def test_missing_country_returns_422(self):
        resp = client.get("/events/upcoming_dividends")
        assert resp.status_code == 422


# ===========================================================================
# Tests for GET /events/start_upcoming_dividends_async and /events/poll_upcoming_dividends_async
# ===========================================================================


class TestUpcomingDividendsAsync:
    def test_redirects_through_shared_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(
                config.settings_finhub_proxy,
                "url_web_crawl_node",
                "https://proxy.example/finhub/",
            ),
        ):
            resp = client.get(
                "/events/poll_upcoming_dividends_async",
                params={"task_id": "task-123"},
                follow_redirects=False,
            )

        assert resp.status_code == 307
        assert (
            resp.headers["location"]
            == "https://proxy.example/finhub/events/poll_upcoming_dividends_async?task_id=task-123"
        )

    def test_starts_task(self):
        with (
            patch("app.routers.async_task._generate_task_id", return_value="task-123"),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.events._run_upcoming_dividends_event_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get(
                "/events/start_upcoming_dividends_async",
                params={"country": "AU", "index": "ASX200"},
            )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": 202,
            "message": "Task started",
            "extra": {"task_id": "task-123", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-123",
            {"task_type": "upcoming_dividends", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_run_task.assert_awaited_once_with("task-123", "AU", "ASX200")

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "upcoming_dividends", "state": async_task.TASK_STATE_RUNNING}
        with patch(
            "app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry
        ) as mock_cache_get:
            resp = client.get("/events/poll_upcoming_dividends_async", params={"task_id": "task-123"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-123", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-123")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/events/poll_upcoming_dividends_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "upcoming_dividends",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": [
                    {
                        "symbol": "ASX:CBA",
                        "company_name": "CBA",
                        "timestamp_str": "2026-06-10",
                        "amount": 2.0,
                        "payment_date": "2026-07-01",
                    }
                ],
            },
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/events/poll_upcoming_dividends_async", params={"task_id": "task-123"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"][0]["symbol"] == "ASX:CBA"
        assert body["extra"] == {"task_id": "task-123", "state": async_task.TASK_STATE_COMPLETED}

    def test_background_task_caches_result(self):
        from app.routers import events
        from app.schemas import events as schemas_event

        result = schemas_event.UpcomingDividendsResponse(status=200, message="ok", data=[])
        with (
            patch(
                "app.routers.events._get_upcoming_dividends_event_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(events._run_upcoming_dividends_event_task("task-123", "AU", "ASX200"))

        mock_cache_set.assert_awaited_once_with(
            "task-123",
            {
                "task_type": "upcoming_dividends",
                "state": async_task.TASK_STATE_COMPLETED,
                "result": {"status": 200, "message": "ok", "data": [], "extra": None},
            },
            ttl=3600,
        )


# ===========================================================================
# Tests for GET /events/upcoming_earnings
# ===========================================================================


class TestUpcomingEarnings:
    def test_redirects_through_shared_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(
                config.settings_finhub_proxy,
                "url_web_crawl_node",
                "https://proxy.example/finhub/",
            ),
        ):
            resp = client.get(
                "/events/upcoming_earnings",
                params={"country": "US", "index": "SP500"},
                follow_redirects=False,
            )

        assert resp.status_code == 307
        assert (
            resp.headers["location"] == "https://proxy.example/finhub/events/upcoming_earnings?country=US&index=SP500"
        )

    @patch("app.routers.events.services_event.get_asx_upcoming_earnings_events", new_callable=AsyncMock)
    def test_au_returns_earnings(self, mock_get):
        event = UpcomingEarningsEvent.model_construct(
            symbol="ASX:BHP",
            company_name="BHP Group",
            timestamp_str="2026-08-15",
        )
        mock_get.return_value = [event]

        resp = client.get("/events/upcoming_earnings", params={"country": "AU", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:BHP"
        assert body["data"][0]["timestamp_str"] == "2026-08-15"
        assert "date" not in body["data"][0]
        mock_get.assert_called_once_with("")

    @patch("app.routers.events.services_event.get_us_upcoming_earnings_events", new_callable=AsyncMock)
    def test_us_returns_earnings(self, mock_get):
        mock_get.return_value = []

        resp = client.get("/events/upcoming_earnings", params={"country": "US", "index": "NASDAQ100"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"] == []
        mock_get.assert_called_once_with("NASDAQ100")

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/upcoming_earnings", params={"country": "JP", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    def test_missing_country_returns_422(self):
        resp = client.get("/events/upcoming_earnings")
        assert resp.status_code == 422


# ===========================================================================
# Tests for GET /events/start_upcoming_earnings_async and /events/poll_upcoming_earnings_async
# ===========================================================================


class TestUpcomingEarningsAsync:
    def test_redirects_through_shared_proxy_handler(self):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(
                config.settings_finhub_proxy,
                "url_web_crawl_node",
                "https://proxy.example/finhub/",
            ),
        ):
            resp = client.get(
                "/events/poll_upcoming_earnings_async",
                params={"task_id": "task-456"},
                follow_redirects=False,
            )

        assert resp.status_code == 307
        assert (
            resp.headers["location"]
            == "https://proxy.example/finhub/events/poll_upcoming_earnings_async?task_id=task-456"
        )

    def test_starts_task(self):
        with (
            patch("app.routers.async_task._generate_task_id", return_value="task-456"),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.events._run_upcoming_earnings_event_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get(
                "/events/start_upcoming_earnings_async",
                params={"country": "US", "index": "SP500"},
            )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": 202,
            "message": "Task started",
            "extra": {"task_id": "task-456", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-456",
            {"task_type": "upcoming_earnings", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_run_task.assert_awaited_once_with("task-456", "US", "SP500")

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "upcoming_earnings", "state": async_task.TASK_STATE_RUNNING}
        with patch(
            "app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry
        ) as mock_cache_get:
            resp = client.get("/events/poll_upcoming_earnings_async", params={"task_id": "task-456"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-456", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-456")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/events/poll_upcoming_earnings_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "upcoming_earnings",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": [
                    {
                        "symbol": "NASDAQ:AAPL",
                        "company_name": "Apple Inc.",
                        "timestamp_str": "2026-08-15",
                    }
                ],
            },
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/events/poll_upcoming_earnings_async", params={"task_id": "task-456"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"][0]["symbol"] == "NASDAQ:AAPL"
        assert body["extra"] == {"task_id": "task-456", "state": async_task.TASK_STATE_COMPLETED}

    def test_background_task_caches_result(self):
        from app.routers import events
        from app.schemas import events as schemas_event

        result = schemas_event.UpcomingEarningsResponse(status=200, message="ok", data=[])
        with (
            patch(
                "app.routers.events._get_upcoming_earnings_event_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(events._run_upcoming_earnings_event_task("task-456", "US", "SP500"))

        mock_cache_set.assert_awaited_once_with(
            "task-456",
            {
                "task_type": "upcoming_earnings",
                "state": async_task.TASK_STATE_COMPLETED,
                "result": {"status": 200, "message": "ok", "data": [], "extra": None},
            },
            ttl=3600,
        )


# ===========================================================================
# Tests for GET /events/new_listings
# ===========================================================================


class TestNewListings:
    @pytest.mark.parametrize("country", ["AU", "US"])
    @pytest.mark.parametrize("endpoint", ["new_listings", "start_new_listings_async"])
    def test_redirects_market_through_ai_task_node(self, country, endpoint):
        with (
            patch.object(config.settings_finhub_proxy, "proxy_mode", "Redirect"),
            patch.object(config.settings_finhub_proxy, "url_ai_task_node", "https://proxy.example/finhub/"),
            patch("app.routers.events_listings._get_new_listings_result", new_callable=AsyncMock) as mock_get_result,
            patch(
                "app.routers.events_listings.router_async_task.start_task", new_callable=AsyncMock
            ) as mock_start_task,
        ):
            resp = client.get(f"/events/{endpoint}", params={"country": country}, follow_redirects=False)

        assert resp.status_code == 307
        assert resp.headers["location"] == f"https://proxy.example/finhub/events/{endpoint}?country={country}"
        mock_get_result.assert_not_awaited()
        mock_start_task.assert_not_awaited()

    @pytest.mark.parametrize(
        ("country", "symbol", "currency"),
        [
            ("AU", "ASX:XYZ", "AUD"),
            ("Australia", "ASX:XYZ", "AUD"),
            ("US", "NASDAQ:XYZ", "USD"),
            ("USA", "NYSE:XYZ", "USD"),
        ],
    )
    @pytest.mark.parametrize("issue_price_upper", [None, 3.0])
    def test_supported_country_returns_listings(self, country, symbol, currency, issue_price_upper):
        event = models_events_listings.ListingEvent(
            symbol=symbol,
            exchange=symbol.split(":", 1)[0],
            company_name="XYZ Corp",
            timestamp_str="2026-06-20",
            issue_price=2.5,
            issue_price_upper=issue_price_upper,
            currency=currency,
            capital_to_raise=5_000_000,
        )
        with (
            patch(
                "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings", new_callable=AsyncMock
            ) as mock_asx,
            patch(
                "app.routers.events_listings.services_us_listings.ai_get_us_new_listings", new_callable=AsyncMock
            ) as mock_us,
        ):
            mock_get, mock_other = (mock_asx, mock_us) if currency == "AUD" else (mock_us, mock_asx)
            mock_get.return_value = [event]
            resp = client.get("/events/new_listings", params={"country": country})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == symbol
        assert body["data"][0]["exchange"] == symbol.split(":", 1)[0]
        assert body["data"][0]["currency"] == currency
        assert body["data"][0]["timestamp_str"] == "2026-06-20"
        assert body["data"][0]["issue_price"] == 2.5
        if issue_price_upper is None:
            assert "issue_price_upper" not in body["data"][0]
        else:
            assert body["data"][0]["issue_price_upper"] == issue_price_upper
        assert "date" not in body["data"][0]
        mock_get.assert_awaited_once_with()
        mock_other.assert_not_awaited()

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/new_listings", params={"country": "JP"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    @patch("app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings", new_callable=AsyncMock)
    def test_empty_country_defaults_unsupported(self, mock_get):
        resp = client.get("/events/new_listings", params={"country": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501


# ===========================================================================
# Tests for GET /events/start_new_listings_async and /events/poll_new_listings_async
# ===========================================================================


class TestNewListingsAsync:
    @pytest.mark.parametrize(
        ("country", "canonical_country"),
        [
            ("AU", "AU"),
            (" au ", "AU"),
            ("Australia", "AU"),
            ("US", "US"),
            ("us", "US"),
            ("United States", "US"),
        ],
    )
    def test_starts_task(self, country, canonical_country):
        with (
            patch(
                "app.routers.async_task._generate_task_id",
                return_value="task-789",
            ) as mock_generate_task_id,
            patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.events_listings._run_new_listings_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get("/events/start_new_listings_async", params={"country": country})

        assert resp.status_code == 202
        assert resp.json() == {
            "status": 202,
            "message": "Task started",
            "extra": {"task_id": "task-789", "state": async_task.TASK_STATE_RUNNING},
        }
        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {"task_type": "new_listings", "state": async_task.TASK_STATE_RUNNING},
            ttl=3600,
        )
        mock_generate_task_id.assert_called_once_with("new_listings", canonical_country)
        mock_run_task.assert_awaited_once_with("task-789", canonical_country)

    @pytest.mark.parametrize("country", ["", "JP"])
    def test_rejects_unsupported_country_before_starting_task(self, country):
        with (
            patch(
                "app.routers.events_listings.router_async_task.start_task", new_callable=AsyncMock
            ) as mock_start_task,
            patch("app.routers.events_listings._run_new_listings_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get("/events/start_new_listings_async", params={"country": country})

        assert resp.status_code == 422
        assert resp.json()["message"] == "New listings supports only country 'AU' and 'US'"
        mock_start_task.assert_not_awaited()
        mock_run_task.assert_not_awaited()

    @pytest.mark.parametrize("country", ["AU", "US"])
    def test_duplicate_start_returns_existing_task_without_scheduling(self, country):
        task_entry = {"task_type": "new_listings", "state": async_task.TASK_STATE_RUNNING}
        with (
            patch("app.routers.async_task._generate_task_id", return_value="task-789"),
            patch(
                "app.routers.async_task.cache.get",
                new_callable=AsyncMock,
                return_value=task_entry,
            ) as mock_cache_get,
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock) as mock_cache_set,
            patch("app.routers.events_listings._run_new_listings_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get("/events/start_new_listings_async", params={"country": country})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {
            "task_id": "task-789",
            "state": async_task.TASK_STATE_RUNNING,
        }
        assert mock_cache_get.await_count == 2
        mock_cache_set.assert_not_awaited()
        mock_run_task.assert_not_awaited()

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "new_listings", "state": async_task.TASK_STATE_RUNNING}
        with patch(
            "app.routers.async_task.cache.get",
            new_callable=AsyncMock,
            return_value=task_entry,
        ) as mock_cache_get:
            resp = client.get("/events/poll_new_listings_async", params={"task_id": "task-789"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-789")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/events/poll_new_listings_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    @pytest.mark.parametrize(("symbol", "currency"), [("ASX:XYZ", "AUD"), ("NASDAQ:XYZ", "USD")])
    def test_poll_returns_completed_result(self, symbol, currency):
        task_entry = {
            "task_type": "new_listings",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": [
                    {
                        "symbol": symbol,
                        "company_name": "XYZ Corp",
                        "timestamp_str": "2026-06-20",
                        "issue_price": 2.5,
                        "currency": currency,
                        "capital_to_raise": 5_000_000,
                    }
                ],
            },
        }
        with patch("app.routers.async_task.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/events/poll_new_listings_async", params={"task_id": "task-789"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"][0]["symbol"] == symbol
        assert body["data"][0]["currency"] == currency
        assert body["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_COMPLETED}

    @pytest.mark.parametrize("country", ["AU", "US"])
    def test_background_task_caches_result(self, country):
        result = schemas_events_listings.ListingsResponse(status=200, message="ok", data=[])
        with (
            patch(
                "app.routers.events_listings._get_new_listings_result",
                new_callable=AsyncMock,
                return_value=result,
            ) as mock_get_result,
            patch(
                "app.routers.async_task.cache.set",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_cache_set,
        ):
            asyncio.run(router_events_listings._run_new_listings_task("task-789", country))

        mock_get_result.assert_awaited_once_with(country)
        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {
                "task_type": "new_listings",
                "state": async_task.TASK_STATE_COMPLETED,
                "result": {"status": 200, "message": "ok", "data": [], "extra": None},
            },
            ttl=3600,
        )

    @pytest.mark.parametrize("failed_country", [None, "AU", "US"])
    def test_market_tasks_are_isolated_and_aliases_reuse_results(self, failed_country):
        events = {
            "AU": models_events_listings.ListingEvent(
                symbol="ASX:XYZ",
                exchange="ASX",
                timestamp_str="2026-11-12 00:00:00+11:00",
                issue_price=2.5,
                currency="AUD",
                capital_to_raise=5_000_000,
                analysis_status="Skipped",
            ),
            "US": models_events_listings.ListingEvent(
                symbol="NASDAQ:IPO",
                exchange="NASDAQ",
                timestamp_str="2026-11-12 00:00:00-05:00",
                issue_price=None,
                currency="USD",
                capital_to_raise=None,
                analysis_status="Skipped",
            ),
        }
        task_entries = {}

        async def store_task(task_id, entry, *, ttl):
            task_entries[task_id] = entry
            return True

        with (
            patch(
                "app.routers.events_listings.services_asx_listings.ai_get_asx_new_listings",
                new_callable=AsyncMock,
                return_value=[events["AU"]],
            ) as mock_asx,
            patch(
                "app.routers.events_listings.services_us_listings.ai_get_us_new_listings",
                new_callable=AsyncMock,
                return_value=[events["US"]],
            ) as mock_us,
            patch("app.routers.async_task.cache.get", new_callable=AsyncMock, side_effect=task_entries.get),
            patch("app.routers.async_task.cache.set", new_callable=AsyncMock, side_effect=store_task),
        ):
            if failed_country is not None:
                failed_service = mock_asx if failed_country == "AU" else mock_us
                failed_service.side_effect = RuntimeError("Market source unavailable")

            task_ids = {}
            for country in events:
                started = client.get("/events/start_new_listings_async", params={"country": country})
                assert started.status_code == 202
                task_ids[country] = started.json()["extra"]["task_id"]

            assert task_ids["AU"] != task_ids["US"]
            for country, alias in (("AU", "Australia"), ("US", "United States")):
                task_id = task_ids[country]
                polled = client.get("/events/poll_new_listings_async", params={"task_id": task_id})
                repeated = client.get("/events/start_new_listings_async", params={"country": alias})
                assert repeated.status_code == polled.status_code
                assert repeated.json() == polled.json()
                if country == failed_country:
                    assert polled.status_code == 500
                    assert polled.json()["extra"] == {"task_id": task_id, "state": async_task.TASK_STATE_FAILED}
                    assert "data" not in polled.json()
                else:
                    assert polled.status_code == 200
                    assert polled.json()["data"] == [events[country].model_dump(mode="json", exclude_none=True)]
                    assert polled.json()["extra"] == {
                        "task_id": task_id,
                        "state": async_task.TASK_STATE_COMPLETED,
                    }

        mock_asx.assert_awaited_once_with()
        mock_us.assert_awaited_once_with()
