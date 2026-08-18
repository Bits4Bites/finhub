# AI API and Flow Review TODO

Inventory date: 2026-08-19

This file tracks the review of every API and internal flow that directly invokes an AI model, selects an AI model,
or orchestrates AI-backed work.

Status definitions:

- **Reviewed:** The flow has been assessed against every review criterion below.
- **Implemented:** All changes accepted during the review have been implemented. This does not indicate whether the
  current flow already exists.
- **Done:** The review, implementation, validation, and documentation work is complete.

## Review criteria

For each flow, assess:

- Expected output quality first. Cost and latency are secondary considerations and must not justify a design that is
  expected to produce lower-quality output.
- Whether AI stages should be introduced, removed, combined, reordered, or replaced with deterministic logic to
  improve the workflow
- Whether each AI stage has one focused objective. Prefer separate focused stages when combining distinct goals could
  overload a model or reduce output quality, even when separation requires additional AI calls.
- Whether prompt-writing and analysis responsibilities are correctly separated
- Model capability, reasoning level, and web-search policy; compare latency and cost only after quality requirements
  are satisfied
- Input validation, prompt-injection boundaries, and sensitive-data handling
- Structured-output contracts, validation, repair behavior, and failure handling
- Caching, retries, timeouts, cancellation, idempotency, and cleanup
- Test coverage and observability across stage boundaries

## Agreed cross-cutting requirements

- Treat all user inputs and all AI-model outputs as untrusted data.
- Validate AI outputs before using them as input to another model or application stage.
- Quality over cost is the governing rule for AI-flow architecture and model selection.
- Do not treat fewer AI calls as an optimization goal. Introduce, retain, or split AI stages when focused tasks are
  expected to materially improve output quality, safety, or reliability.
- Use the lowest-cost model or design only when the alternatives are expected to provide materially equivalent output
  quality, safety, and reliability. Account for added latency and trust boundaries without sacrificing quality merely
  to reduce cost.
- Sanitize AI-generated HTML before rendering it in the browser or using it in a print view.
- Use POST rather than query-string GET requests for AI streaming flows.
- Keep the current reasoning-based search-context and tool-call limits unless a later review explicitly changes them.
- Prefer focused improvements over broad technical infrastructure changes during this review cycle.

## Current AI task inventory

Task IDs below use their current code spelling, including `ASX_LISTTINGS`.

| AI task                                   | Current model   | Reasoning | Web search   | Current objective                                   |
|-------------------------------------------|-----------------|-----------|--------------|-----------------------------------------------------|
| `ANALYZE_TICKER_BUILD_PROMPT`             | `gpt-5.6-luna`  | Medium    | No (default) | Build a ticker-specific analysis prompt             |
| `ANALYZE_TICKER_EXEC`                     | `gpt-5.6-terra` | High      | Yes          | Research and analyze a ticker                       |
| `BUILD_PORTFOLIO_BUILD_PROMPT`            | `gpt-5.6-luna`  | Medium    | No (default) | Build a portfolio-construction prompt               |
| `BUILD_PORTFOLIO_EXEC`                    | `gpt-5.6-sol`   | High      | Yes          | Research and construct a portfolio                  |
| `REVIEW_PORTFOLIO_BUILD_PROMPT`           | `gpt-5.6-luna`  | Medium    | No (default) | Build a portfolio-review prompt                     |
| `REVIEW_PORTFOLIO_EXEC`                   | `gpt-5.6-sol`   | High      | Yes          | Research and review an existing portfolio           |
| `REVIEW_PORTFOLIO_SUMMARIZE`              | `gpt-5.6-luna`  | Medium    | No (default) | Summarize a portfolio review for rebalance planning |
| `REVIEW_PORTFOLIO_REBALANCE_BUILD_PROMPT` | `gpt-5.6-luna`  | Medium    | No (default) | Build a rebalance-planning prompt                   |
| `REVIEW_PORTFOLIO_REBALANCE_EXEC`         | `gpt-5.6-sol`   | High      | Yes          | Research and produce an actionable rebalance plan   |
| `SPOTLIGHT_PORTFOLIO_BUILD_PROMPT`        | `gpt-5.6-luna`  | Medium    | No (default) | Build a concise portfolio-risk prompt               |
| `SPOTLIGHT_PORTFOLIO_EXEC`                | `gpt-5.6-terra` | High      | Yes          | Research and identify urgent portfolio risks        |
| `ANALYZE_DIV_EVENT_BUILD_PROMPT`          | `gpt-5.6-luna`  | Medium    | No (default) | Build a dividend-event analysis prompt              |
| `ANALYZE_DIV_EVENT_EXEC`                  | `gpt-5.6-sol`   | High      | Yes          | Research and evaluate a dividend strategy           |
| `ASX_LISTTINGS_EXTRACT`                   | `gpt-5.6-luna`  | Low       | No (default) | Extract structured listings from scraped ASX text   |
| `ASX_LISTTINGS_BUILD_PROMPT`              | `gpt-5.6-luna`  | Medium    | No (default) | Build an ASX-listings analysis prompt               |
| `ASX_LISTTINGS_ANALYZE`                   | `gpt-5.6-terra` | High      | Yes          | Research and analyze new ASX listings               |

## Flow review backlog

### 1. Shared AI task execution and provider dispatch

- **API or flow name:** Shared AI task execution and provider dispatch
- **AI tasks involved:** All configured AI tasks
- **Primary code:** `app\services\ai_helper.py`, `app\config.py`, `ai_tasks.env`, `ai_vendors.env`
- **Summary of process flow:** Resolve a task ID to its configured vendor, tier, model, reasoning effort, and web-search
  policy; dispatch the prompt to Azure OpenAI, OpenAI, OpenRouter, or Gemini; optionally configure web search and
  structured JSON output; normalize completion, error, timing, and token-usage data into `LLMResponse`. OpenAI search
  context and maximum tool calls are selected from the configured reasoning effort.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 2. AI vendor and model discovery API

- **API or flow name:** `GET /ai/vendors`
- **AI tasks involved:** None; this is configuration discovery only
- **Primary code:** `app\routers\ai.py`, `app\config.py`
- **Summary of process flow:** Read initialized vendor, tier, and model configuration and return the available model
  catalog. The endpoint does not invoke a model, but it exposes the models from which AI task configurations select.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 3. Dividend-event analysis

- **API or flow name:** `GET /ai/analyze_dividend_event` and `GET /ai/analyze_dividend_event_async`
- **AI tasks involved:** `ANALYZE_DIV_EVENT_BUILD_PROMPT`, `ANALYZE_DIV_EVENT_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_analyze_div_event.py`,
  `app\services\event.py`
- **Summary of process flow:** Validate the ticker and calculate deterministic historical dividend-event metrics;
  combine those metrics with the user intent in a prompt-writing task; pass the generated prompt to a research-enabled
  analysis task; parse the returned JSON and copy selected fields into the dividend-event result; cache the result for
  72 hours. The async API runs the same flow as a background task and exposes start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 4. Ticker analysis

- **API or flow name:** `POST /ai/analyze_ticker` and `POST /ai/analyze_ticker_async`
- **AI tasks involved:** `ANALYZE_TICKER_BUILD_PROMPT`, `ANALYZE_TICKER_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_analyze_ticker.py`
- **Summary of process flow:** Normalize and validate the symbol through Yahoo Finance; derive asset type, exchange,
  sector, and market-cap context; ask one model to build an intent-specific prompt; pass that model output to a
  research-enabled analysis task; return the Markdown analysis and cache it for 72 hours. The async API runs the same
  flow as a background task and exposes start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 5. Portfolio construction

- **API or flow name:** `POST /ai/build_portfolio`, `POST /ai/build_portfolio_async`, and the no-holdings branch of
  `POST /ai/analyze_portfolio`
- **AI tasks involved:** `BUILD_PORTFOLIO_BUILD_PROMPT`, `BUILD_PORTFOLIO_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_build_portfolio.py`
- **Summary of process flow:** Build an investor profile from country, theme, and optional existing positions; ask one
  model to produce a self-contained portfolio-construction prompt; pass the generated prompt to a research-enabled
  model that selects securities and allocations; return the Markdown portfolio and cache it for 72 hours. Async API
  variants run the same flow as a background task and expose start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 6. Portfolio spotlight

- **API or flow name:** `POST /ai/spotlight_portfolio` and `POST /ai/spotlight_portfolio_async`
- **AI tasks involved:** `SPOTLIGHT_PORTFOLIO_BUILD_PROMPT`, `SPOTLIGHT_PORTFOLIO_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_spotlight_portfolio.py`
- **Summary of process flow:** Skip AI when the portfolio has no holdings; otherwise build an investor-and-holdings
  profile; ask one model to create a concise risk-review prompt; pass the generated prompt to a research-enabled model
  that identifies and ranks urgent risks and actions; return the Markdown response with its required final summary
  line and cache it for 72 hours. The async API runs the same flow as a background task and exposes start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 7. Portfolio analysis dispatcher

- **API or flow name:** `POST /ai/analyze_portfolio` and `POST /ai/analyze_portfolio_async`
- **AI tasks involved:** Conditionally uses `BUILD_PORTFOLIO_BUILD_PROMPT` and `BUILD_PORTFOLIO_EXEC`, or the review and
  rebalance tasks listed in entries 8 and 9
- **Primary code:** `app\routers\ai.py`
- **Summary of process flow:** Inspect the submitted allocation. If it is empty or every holding has zero shares,
  dispatch to portfolio construction. Otherwise dispatch to existing-portfolio review and optionally request a
  rebalance plan. The async API runs the selected branch as a background task and exposes start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 8. Existing-portfolio review

- **API or flow name:** Existing-holdings branch of `POST /ai/analyze_portfolio` and
  `POST /ai/analyze_portfolio_async`
- **AI tasks involved:** `REVIEW_PORTFOLIO_BUILD_PROMPT`, `REVIEW_PORTFOLIO_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_review_portfolio.py`
- **Summary of process flow:** Build an investor profile containing current positions and values; ask one model to
  create a portfolio-review prompt; pass the generated prompt to a research-enabled model; require a final
  `REBALANCE_NEEDED` decision; remove that control line before returning the review. When no rebalance plan is
  requested, cache and return the review for 72 hours.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 9. Portfolio rebalance extension

- **API or flow name:** Rebalance branch of `POST /ai/analyze_portfolio` and `POST /ai/analyze_portfolio_async`
- **AI tasks involved:** `REVIEW_PORTFOLIO_BUILD_PROMPT`, `REVIEW_PORTFOLIO_EXEC`,
  `REVIEW_PORTFOLIO_SUMMARIZE`, `REVIEW_PORTFOLIO_REBALANCE_BUILD_PROMPT`,
  `REVIEW_PORTFOLIO_REBALANCE_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_review_portfolio.py`
- **Summary of process flow:** Run the existing-portfolio review and inspect its final rebalance flag. Return
  deterministically when no major rebalance is needed. When one is needed, summarize the model-generated review,
  pass that summary to a prompt-writing task, and pass the resulting prompt to a research-enabled rebalance task.
  Return both the original review and the generated plan, then cache the combined result for 72 hours.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 10. ASX new-listings extraction and analysis

- **API or flow name:** `GET /events/new_listings` and `GET /events/new_listings_async` for country `AU`
- **AI tasks involved:** `ASX_LISTTINGS_EXTRACT`, `ASX_LISTTINGS_BUILD_PROMPT`, `ASX_LISTTINGS_ANALYZE`
- **Primary code:** `app\routers\events.py`, `app\services\msai_asx_listings.py`,
  `app\services\crawler.py`
- **Summary of process flow:** Fetch and parse the ASX upcoming-listings page; send selected page text to an extraction
  task and parse its JSON array into listing models; build a second prompt containing the extracted companies; pass
  that model-generated prompt to a research-enabled listings-analysis task; parse the returned JSON and attach each
  analysis to its listing; cache the final event list for 72 hours. The async API runs the same flow as a background
  task and exposes start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 11. Shared asynchronous AI task start and polling

- **API or flow name:** All AI-backed `*_async` endpoints
- **AI tasks involved:** All tasks used by dividend analysis, ticker analysis, portfolio construction, portfolio
  spotlight, portfolio review/rebalance, and ASX new listings
- **Primary code:** `app\routers\ai.py`, `app\routers\events.py`, `app\schemas\async_task.py`,
  `app\utils\cache.py`
- **Summary of process flow:** Create a UUID task ID, store a `RUNNING` record with a one-hour TTL, execute the selected
  flow with FastAPI `BackgroundTasks`, and replace the cache record with `COMPLETED` plus the serialized response or
  `FAILED` plus a generic error. Clients poll the same endpoint using the task ID. There are no current streaming
  endpoints; all long-running APIs use start/poll behavior.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

## Inventory exclusions

- `/events/upcoming_dividends*` performs deterministic dividend-event analysis but does not invoke an AI task.
- `/events/upcoming_earnings*` does not invoke an AI task.
- Stock, market-index, and precious-metal APIs do not invoke AI tasks.
