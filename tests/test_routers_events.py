"""Unit tests for app.routers.events module."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.event import ListingEvent, UpcomingDividendEvent, UpcomingEarningsEvent
from app.schemas import async_task

client = TestClient(app)


# ===========================================================================
# Tests for GET /events/upcoming_dividends
# ===========================================================================


class TestUpcomingDividends:
    @patch("app.routers.events.services_event.get_asx_upcoming_dividends_events", new_callable=AsyncMock)
    def test_au_returns_dividends(self, mock_get):
        event = UpcomingDividendEvent.model_construct(
            symbol="ASX:CBA",
            company_name="CBA",
            date="2026-06-10",
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
# Tests for GET /events/upcoming_dividends_async
# ===========================================================================


class TestUpcomingDividendsAsync:
    def test_starts_task(self):
        with (
            patch("app.routers.events.uuid.uuid4", return_value="task-123"),
            patch("app.routers.events.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.events._run_upcoming_dividends_event_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get(
                "/events/upcoming_dividends_async",
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
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=task_entry) as mock_cache_get:
            resp = client.get("/events/upcoming_dividends_async", params={"task_id": "task-123"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-123", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-123")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/events/upcoming_dividends_async", params={"task_id": "missing"})

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
                        "date": "2026-06-10",
                        "amount": 2.0,
                        "payment_date": "2026-07-01",
                    }
                ],
            },
        }
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/events/upcoming_dividends_async", params={"task_id": "task-123"})

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
            patch("app.routers.events.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
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
    @patch("app.routers.events.services_event.get_asx_upcoming_earnings_events", new_callable=AsyncMock)
    def test_au_returns_earnings(self, mock_get):
        event = UpcomingEarningsEvent.model_construct(
            symbol="ASX:BHP",
            company_name="BHP Group",
            date="2026-08-15",
        )
        mock_get.return_value = [event]

        resp = client.get("/events/upcoming_earnings", params={"country": "AU", "index": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:BHP"
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
# Tests for GET /events/upcoming_earnings_async
# ===========================================================================


class TestUpcomingEarningsAsync:
    def test_starts_task(self):
        with (
            patch("app.routers.events.uuid.uuid4", return_value="task-456"),
            patch("app.routers.events.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.events._run_upcoming_earnings_event_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get(
                "/events/upcoming_earnings_async",
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
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=task_entry) as mock_cache_get:
            resp = client.get("/events/upcoming_earnings_async", params={"task_id": "task-456"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-456", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-456")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/events/upcoming_earnings_async", params={"task_id": "missing"})

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
                        "date": "2026-08-15",
                    }
                ],
            },
        }
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/events/upcoming_earnings_async", params={"task_id": "task-456"})

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
            patch("app.routers.events.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
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
    @patch("app.routers.events.services_asx_listings.ai_get_asx_new_listings", new_callable=AsyncMock)
    def test_au_returns_listings(self, mock_get):
        event = ListingEvent.model_construct(
            symbol="ASX:XYZ",
            company_name="XYZ Corp",
            date="2026-06-20",
            price=2.5,
        )
        mock_get.return_value = [event]

        resp = client.get("/events/new_listings", params={"country": "AU"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["message"] == "ok"
        assert len(body["data"]) == 1
        assert body["data"][0]["symbol"] == "ASX:XYZ"
        mock_get.assert_called_once()

    def test_unsupported_country_returns_501(self):
        resp = client.get("/events/new_listings", params={"country": "JP"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501
        assert "Unsupported" in body["message"]

    @patch("app.routers.events.services_asx_listings.ai_get_asx_new_listings", new_callable=AsyncMock)
    def test_empty_country_defaults_unsupported(self, mock_get):
        resp = client.get("/events/new_listings", params={"country": ""})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 501


# ===========================================================================
# Tests for GET /events/new_listings_async
# ===========================================================================


class TestNewListingsAsync:
    def test_starts_task(self):
        with (
            patch("app.routers.events.uuid.uuid4", return_value="task-789"),
            patch("app.routers.events.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
            patch("app.routers.events._run_new_listings_task", new_callable=AsyncMock) as mock_run_task,
        ):
            resp = client.get("/events/new_listings_async", params={"country": "AU"})

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
        mock_run_task.assert_awaited_once_with("task-789", "AU")

    def test_poll_returns_running_status(self):
        task_entry = {"task_type": "new_listings", "state": async_task.TASK_STATE_RUNNING}
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=task_entry) as mock_cache_get:
            resp = client.get("/events/new_listings_async", params={"task_id": "task-789"})

        assert resp.status_code == 202
        assert resp.json()["message"] == "Task is running"
        assert resp.json()["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_RUNNING}
        mock_cache_get.assert_awaited_once_with("task-789")

    def test_poll_returns_404_for_missing_task(self):
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=None):
            resp = client.get("/events/new_listings_async", params={"task_id": "missing"})

        assert resp.status_code == 404
        assert resp.json() == {"status": 404, "message": "Task not found"}

    def test_poll_returns_completed_result(self):
        task_entry = {
            "task_type": "new_listings",
            "state": async_task.TASK_STATE_COMPLETED,
            "result": {
                "status": 200,
                "message": "ok",
                "data": [
                    {
                        "symbol": "ASX:XYZ",
                        "company_name": "XYZ Corp",
                        "date": "2026-06-20",
                        "price": 2.5,
                    }
                ],
            },
        }
        with patch("app.routers.events.cache.get", new_callable=AsyncMock, return_value=task_entry):
            resp = client.get("/events/new_listings_async", params={"task_id": "task-789"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == 200
        assert body["data"][0]["symbol"] == "ASX:XYZ"
        assert body["extra"] == {"task_id": "task-789", "state": async_task.TASK_STATE_COMPLETED}

    def test_background_task_caches_result(self):
        from app.routers import events
        from app.schemas import events as schemas_event

        result = schemas_event.ListingsResponse(status=200, message="ok", data=[])
        with (
            patch(
                "app.routers.events._get_new_listings_result",
                new_callable=AsyncMock,
                return_value=result,
            ),
            patch("app.routers.events.cache.set", new_callable=AsyncMock, return_value=True) as mock_cache_set,
        ):
            asyncio.run(events._run_new_listings_task("task-789", "AU"))

        mock_cache_set.assert_awaited_once_with(
            "task-789",
            {
                "task_type": "new_listings",
                "state": async_task.TASK_STATE_COMPLETED,
                "result": {"status": 200, "message": "ok", "data": [], "extra": None},
            },
            ttl=3600,
        )
