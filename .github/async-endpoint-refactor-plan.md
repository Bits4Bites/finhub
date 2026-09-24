# Async Endpoint Router Refactor Plan

Updated: 2026-09-24

Status: explicit start and poll routes implemented.

## Scope

This inventory covers features that expose both:

1. an immediate request/response endpoint, referred to below as the **sync endpoint**; and
2. a background-task start endpoint; and
3. a background-task poll endpoint.

“Sync endpoint” describes the API interaction, not the Python implementation. The current
immediate endpoints are implemented with `async def`.

Every background feature follows the same route naming contract:

- **Start:** `VERB /<prefix>/start_<feature>_async` with the feature input.
- **Poll:** `VERB /<prefix>/poll_<feature>_async?task_id={task_id}` without the original
  feature input.
- The start and poll endpoints use the same HTTP method as the sync endpoint.

## Endpoint inventory

| # | Feature | Router | Sync endpoint | Async start request | Async poll request | Task type | Proxy target |
|---|---|---|---|---|---|---|---|
| 1 | Analyze dividend event | `app/routers/ai_dividend.py` | `POST /ai/analyze_dividend_event` with `AnalyzeDividendEventRequest` body | `POST /ai/start_analyze_dividend_event_async` with request body | `POST /ai/poll_analyze_dividend_event_async?task_id={task_id}` | `analyze_dividend_event` | AI task node |
| 2 | Analyze ticker | `app/routers/ai_ticker.py` | `POST /ai/analyze_ticker` with `AnalyzeTickerRequest` body | `POST /ai/start_analyze_ticker_async` with request body | `POST /ai/poll_analyze_ticker_async?task_id={task_id}` | `analyze_ticker` | AI task node |
| 3 | Build portfolio | `app/routers/ai_portfolio_construction.py` | `POST /ai/build_portfolio` with `BuildPortfolioRequest` body | `POST /ai/start_build_portfolio_async` with request body | `POST /ai/poll_build_portfolio_async?task_id={task_id}` | `build_portfolio` | AI task node |
| 4 | Analyze portfolio | `app/routers/ai_portfolio_review.py` | `POST /ai/analyze_portfolio` with `AnalyzePortfolioRequest` body | `POST /ai/start_analyze_portfolio_async` with request body | `POST /ai/poll_analyze_portfolio_async?task_id={task_id}` | `analyze_portfolio` | AI task node |
| 5 | Spotlight portfolio | `app/routers/ai_portfolio_spotlight.py` | `POST /ai/spotlight_portfolio` with `PortfolioSpotlightRequest` body | `POST /ai/start_spotlight_portfolio_async` with request body | `POST /ai/poll_spotlight_portfolio_async?task_id={task_id}` | `spotlight_portfolio` | AI task node |
| 6 | Upcoming dividends | `app/routers/events.py` | `GET /events/upcoming_dividends?country={country}&index={index}` | `GET /events/start_upcoming_dividends_async?country={country}&index={index}` | `GET /events/poll_upcoming_dividends_async?task_id={task_id}` | `upcoming_dividends` | Web-crawl node |
| 7 | Upcoming earnings | `app/routers/events.py` | `GET /events/upcoming_earnings?country={country}&index={index}` | `GET /events/start_upcoming_earnings_async?country={country}&index={index}` | `GET /events/poll_upcoming_earnings_async?task_id={task_id}` | `upcoming_earnings` | Web-crawl node |
| 8 | New listings | `app/routers/events_listings.py` | `GET /events/new_listings?country={country}` | `GET /events/start_new_listings_async?country={country}` | `GET /events/poll_new_listings_async?task_id={task_id}` | `new_listings` | AI task node |

All eight features are registered with the API-key dependency in `app/main.py`.

## Current shared task contract

- Task orchestration is implemented in `app/routers/async_task.py`.
- Shared task response types and states are defined in `app/schemas/async_task.py`.
- Work is scheduled with FastAPI `BackgroundTasks`; there is no external worker queue.
- Task states are `RUNNING`, `COMPLETED`, and `FAILED`.
- Start and running responses use HTTP `202` and return
  `extra: {"task_id": "...", "state": "RUNNING"}`.
- Unknown, expired, or wrong-feature task IDs return HTTP `404`.
- Task entries are cached for one hour (`ASYNC_TASK_TTL = 3600`).
- Task IDs are generated from the task type and normalized input with an HMAC secret that
  is created when the application process starts.
- An identical request reuses an existing cached task rather than scheduling duplicate work.
- Duplicate starts render the existing task through a private poll helper; route handlers do
  not recursively invoke another endpoint handler.
- Poll endpoints require `task_id` as a query parameter and do not accept the original
  request body or feature query parameters.
- Completed responses return the feature data plus `extra.task_id` and
  `extra.state = "COMPLETED"`.

## Current implementation differences

These differences should be explicitly preserved or standardized during the refactor:

| Area | Current behavior |
|---|---|
| HTTP shape | Five AI features use `POST` plus a request body. Three event features use `GET` plus query parameters. |
| Failure status | Ticker and portfolio routers preserve a stored 4xx/5xx status. Upcoming-dividend, upcoming-earnings, and new-listings polling currently return `500` for every failed task. Dividend analysis can also retain a structured failed result. |
| Completion metadata | Some task runners store the result status/message in the task entry; others store only the result model. |
| Start validation | POST-based routes return `400` when the start body is missing. New listings validates `country=AU` before starting. Upcoming dividends and earnings can start with an unsupported or empty country and later store the non-success response as a completed task. |
| Duplicate-task reuse | Start routes call a private feature poll helper when `start_task` finds a cached task. |
| OpenAPI errors | Ticker, portfolio construction, and portfolio review document detailed async error responses. Dividend, spotlight, and event async routes have less complete response documentation. |
| Naming | Public async routes now consistently use `start_<feature>_async` and `poll_<feature>_async`; internal runner and response-schema names remain feature-specific. |
| Proxy routing | Upcoming dividends and earnings use the web-crawl node; all other features use the AI task node. Proxy handling happens before local start/poll handling. |

## Existing tests

| Coverage | Test file |
|---|---|
| Shared task storage, lifecycle, validation, and task IDs | `tests/test_routers_async_task.py` |
| Cross-endpoint verb and query-poll convention | `tests/test_async_endpoint_conventions.py` |
| Analyze dividend event | `tests/test_routers_ai_dividend.py` |
| Analyze ticker | `tests/test_routers_ai_ticker.py` |
| Build portfolio | `tests/test_routers_ai.py` |
| Analyze portfolio | `tests/test_routers_ai_portfolio_review.py` |
| Spotlight portfolio | `tests/test_routers_ai_portfolio_spotlight.py` |
| Upcoming dividends, upcoming earnings, and new listings | `tests/test_routers_events.py` |

`tests/test_async_endpoint_conventions.py` enumerates all eight features and verifies the
sync/start/poll verb, naming, required poll `task_id`, missing poll body, and removal of the
legacy combined route.

## Refactor checkpoints

- [ ] Define one start/poll lifecycle contract, including HTTP status propagation.
- [x] Split every background feature into explicit start and poll endpoints.
- [ ] Extract shared start, deduplication, poll, completion, and failure handling.
- [x] Preserve each feature's request normalization and proxy destination.
- [ ] Standardize missing-input and unsupported-input validation.
- [ ] Standardize async response schemas and OpenAPI error documentation.
- [x] Remove recursive endpoint calls used to switch from start to poll.
- [x] Cover all eight features in the cross-endpoint convention tests.
- [ ] Verify start, duplicate start, running poll, completed poll, failed poll, missing task,
  expired task, proxy mode, and wrong-task-type behavior for every feature.
