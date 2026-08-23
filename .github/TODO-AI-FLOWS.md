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
- Cache identity and freshness, including whether TTL should vary by event phase, data volatility, or workflow state;
  retries, timeouts, cancellation, idempotency, and cleanup
- Test coverage and observability across stage boundaries

### AI task configuration scoring

Score each candidate model and reasoning configuration from 0 through 100 in every category:

| Category                      | Weight | Meaning                                                                                            |
|-------------------------------|-------:|----------------------------------------------------------------------------------------------------|
| Expected output quality       |    50% | Correctness, relevance, completeness, factual accuracy, and fitness for the API's intended use     |
| Structured-output reliability |    20% | Schema adherence, consistency, completeness of required fields, and resistance to malformed output |
| Task depth                    |    15% | Research/source coverage for web-enabled tasks, or analytical/reasoning depth for non-web tasks    |
| Cost efficiency               |    15% | Relative expected token, reasoning, and tool-use cost for materially equivalent work               |
| Latency efficiency            |     0% | Record for operational context when useful, but do not include it in the weighted score            |

Use this formula:

`weighted score = quality * 0.50 + structure * 0.20 + task depth * 0.15 + cost efficiency * 0.15`

The score is a decision aid, not a substitute for quality gates:

1. Exclude any option expected to miss required output quality, safety, source-verification, or reliability thresholds.
2. Score the remaining viable options using evidence from representative fixtures where available.
3. Treat unbenchmarked scores as provisional engineering estimates.
4. For web-enabled tasks, include search-context size, tool-call allowance, evidence breadth, and citation quality in
   task depth.
5. For non-web tasks, include reasoning complexity, synthesis quality, and difficult-case performance in task depth.
6. Break close scores by expected output quality first, then structured-output reliability.

## Agreed cross-cutting requirements

- Treat all user inputs and all AI-model outputs as untrusted data.
- Validate AI outputs before using them as input to another model or application stage.
- Apply the shared 50/20/15/15/0 AI scoring and its quality gates to every AI-related review and future AI feature.
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
- Use `app\utils\ai_reference.py` for source URL normalization, canonical IDs, citation verification, recursive ID
  remapping, and registry validation in every sourced AI flow.
- Treat model-authored source IDs as temporary. Final IDs and `is_verified` are application-owned; empty or unmatched
  provider citations produce `is_verified=False`, not whole-flow failure.
- Never pass orphan or unused source IDs downstream. Bounded repair may remove orphan links and unsupported claims,
  add explicit data gaps, prune unused sources, and then rerun strict registry validation; it must never guess a
  replacement source.
- Keep temporary provider-output models private to their flow and keep final caller-facing validated models in
  `app\models`. Put provider, market, and country constraints in the owning service rather than generic models.
- Load source-controlled AI prompt templates through `app\utils\ai_prompt.py` so services share path validation,
  non-empty content checks, and cached file content instead of implementing file I/O independently.
- Prefer phase-aware caching over a fixed TTL when evidence freshness changes across an event lifecycle. Use shorter
  TTLs near or during events and for active or failed work, and longer TTLs only for stable historical results. Cache
  identity should include normalized inputs, the relevant exchange-local or evidence date, contract/prompt revision,
  and AI task configuration so stale results cannot survive meaningful flow changes. Every review should identify and
  fixture-test its freshness boundaries.

## Current AI task inventory

Task IDs below use their current code spelling, including `ASX_LISTTINGS`.

| AI task                                   | Current model   | Reasoning | Web search   | Current objective                                                                 |
|-------------------------------------------|-----------------|-----------|--------------|-----------------------------------------------------------------------------------|
| `ANALYZE_TICKER_BUILD_PROMPT`             | `gpt-5.6-luna`  | Medium    | No (default) | Build a ticker-specific analysis prompt                                           |
| `ANALYZE_TICKER_EXEC`                     | `gpt-5.6-terra` | High      | Yes          | Research and analyze a ticker                                                     |
| `BUILD_PORTFOLIO_PLAN`                    | `gpt-5.6-terra` | Medium    | No (default) | Build a validated, theme-aware portfolio-construction plan                        |
| `BUILD_PORTFOLIO_RESEARCH`                | `gpt-5.6-terra` | High      | Yes          | Research a bounded, sourced candidate universe                                    |
| `BUILD_PORTFOLIO_CONSTRUCT`               | `gpt-5.6-terra` | High      | No (default) | Select and allocate one evidence-backed target portfolio                          |
| `BUILD_PORTFOLIO_ACTION_PLAN`             | `gpt-5.6-terra` | High      | No (default) | Explain fixed, budget-aware whole-share actions in priority order                 |
| `REVIEW_PORTFOLIO_PLAN`                   | `gpt-5.6-terra` | Medium    | No (default) | Build a structured, portfolio-specific review plan                               |
| `REVIEW_PORTFOLIO_RESEARCH`               | `gpt-5.6-terra` | High      | Yes          | Research current holdings and bounded addition candidates                         |
| `REVIEW_PORTFOLIO_ASSESS`                 | `gpt-5.6-terra` | High      | No (default) | Assess strengths, risks, roles, and holding disposition intent                    |
| `REVIEW_PORTFOLIO_TARGET`                 | `gpt-5.6-terra` | High      | No (default) | Design one validated aspirational target portfolio                               |
| `REVIEW_PORTFOLIO_ACTION_PLAN`            | `gpt-5.6-terra` | High      | No (default) | Rank and explain application-calculated portfolio actions                         |
| `SPOTLIGHT_PORTFOLIO_PLAN`                | `gpt-5.6-terra` | Medium    | No (default) | Build a validated, theme-aware analysis plan for a verified portfolio             |
| `SPOTLIGHT_PORTFOLIO_RESEARCH`            | `gpt-5.6-terra` | High      | Yes          | Research sourced risks for a verified portfolio                                   |
| `SPOTLIGHT_PORTFOLIO_ASSESS`              | `gpt-5.6-terra` | High      | No           | Rank structured risks and actions from validated research                         |
| `ANALYZE_DIV_EVENT_RESEARCH`              | `gpt-5.6-terra` | High      | Yes          | Research sourced dividend-event evidence                                          |
| `ANALYZE_DIV_EVENT_ASSESS`                | `gpt-5.6-terra` | High      | No           | Compare dividend strategies from validated evidence                               |
| `ASX_LISTTINGS_EXTRACT`                   | `gpt-5.6-luna`  | Low       | No (default) | Extract structured listings from scraped ASX text                                 |
| `ASX_LISTTINGS_RESEARCH`                  | `gpt-5.6-terra` | Medium    | Yes          | Run bounded first-pass research for one ASX listing                               |
| `ASX_LISTTINGS_ANALYZE`                   | `gpt-5.6-terra` | Medium    | No (default) | Produce a quick screening assessment from validated research                      |
| `ASX_LISTTINGS_UNDERWRITTEN_RESEARCH`     | `gpt-5.6-terra` | High      | Yes          | Research an explicitly underwritten listing with additional underwriting scrutiny |
| `ASX_LISTTINGS_UNDERWRITTEN_ANALYZE`      | `gpt-5.6-terra` | High      | No (default) | Assess an explicitly underwritten listing and residual execution risk             |

## Flow review backlog

### 1. Ticker analysis

- **API or flow name:** `POST /ai/analyze_ticker` and `POST /ai/analyze_ticker_async`
- **AI tasks involved:** `ANALYZE_TICKER_BUILD_PROMPT`, `ANALYZE_TICKER_EXEC`
- **Primary code:** `app\routers\ai.py`, `app\services\msai_analyze_ticker.py`
- **Summary of process flow:** Normalize and validate the symbol through Yahoo Finance; derive asset type, exchange,
  sector, and market-cap context; ask one model to build an intent-specific prompt; pass that model output to a
  research-enabled analysis task; return the Markdown analysis and cache it for 72 hours. The async API runs the same
  flow as a background task and exposes start/poll states.
- **Status:** Reviewed: **No** | Implemented: **No** | Done: **No**

### 2. Portfolio construction

- **API or flow name:** `POST /ai/build_portfolio`, `POST /ai/build_portfolio_async`, and the no-holdings branch of
  `POST /ai/analyze_portfolio`
- **AI tasks involved:** `BUILD_PORTFOLIO_PLAN`, `BUILD_PORTFOLIO_RESEARCH`, `BUILD_PORTFOLIO_CONSTRUCT`,
  `BUILD_PORTFOLIO_ACTION_PLAN`
- **Primary code:** `app\routers\ai_portfolio_construction.py`, `app\schemas\ai_portfolio_construction.py`,
  `app\models\ai_portfolio_construction.py`, `app\services\portfolio_verification.py`,
  `app\services\msai_build_portfolio.py`
- **Summary of process flow:** Require a non-blank investor theme; ignore zero-share positions; verify positive seed
  holdings; extract a total or recurring budget from the theme; build a structured theme-aware plan; research a
  bounded candidate set with canonical sources; construct one allocation target; verify target prices; size
  whole-share actions deterministically; and explain the fixed actions in priority order. Total budgets may produce
  seeded TRIM actions, recurring budgets preserve aligned holdings with HOLD, and non-target seeds use EXIT/SELL ALL.
  Verification is cached for five minutes and each AI stage plus the final result for one hour. Async start and
  query-poll calls expose the same structured result and preserve `422`/`502` failures.
- **Status:** Reviewed: **Yes** | Implemented: **Yes** | Done: **Yes**

### 3. Portfolio analysis dispatcher

- **API or flow name:** `POST /ai/analyze_portfolio` and `POST /ai/analyze_portfolio_async`
- **AI tasks involved:** Conditionally uses the four `BUILD_PORTFOLIO_*` tasks or the five structured
  `REVIEW_PORTFOLIO_*` tasks listed in entries 4 and 5.
- **Primary code:** `app\routers\ai_portfolio_review.py`, `app\schemas\ai_portfolio_review.py`
- **Summary of process flow:** Require a non-blank investor theme and inspect all submitted positions. Dispatch to
  structured construction when no positions are submitted, no position is positive, or positive positions make up
  35% or less of submissions; pass sparse positive positions through as construction seeds. Otherwise dispatch to
  structured existing-portfolio review. Return a `result_type`-discriminated union of `PortfolioConstruction` and
  `PortfolioReview`; async start/poll preserves the same typed result and failure status.
- **Detailed review:** [Review portfolio redesign](detailed_review_plan/04-review-portfolio.md)
- **Status:** Reviewed: **Yes** | Implemented: **Yes** | Done: **Yes**

### 4. Existing-portfolio review

- **API or flow name:** Existing-holdings branch of `POST /ai/analyze_portfolio` and
  `POST /ai/analyze_portfolio_async`
- **AI tasks involved:** `REVIEW_PORTFOLIO_PLAN`, `REVIEW_PORTFOLIO_RESEARCH`, `REVIEW_PORTFOLIO_ASSESS`,
  `REVIEW_PORTFOLIO_TARGET`, and conditionally `REVIEW_PORTFOLIO_ACTION_PLAN`
- **Primary code:** `app\routers\ai_portfolio_review.py`, `app\schemas\ai_portfolio_review.py`,
  `app\models\ai_portfolio_review.py`, `app\services\msai_review_portfolio.py`
- **Summary of process flow:** Verify and value every positive holding; extract LongTerm or Swing strategy and a
  supplied or inferred budget deterministically; plan, research, assess, and design a sourced target through focused
  structured stages; render emoji roles; derive turnover and the `YES`/`NO` rebalance recommendation in the
  application; and return structured strengths, risks, holding reviews, target allocations, data gaps, and canonical
  references. Verification and AI stages use freshness-specific caches.
- **Detailed review:** [Review portfolio redesign](detailed_review_plan/04-review-portfolio.md)
- **Status:** Reviewed: **Yes** | Implemented: **Yes** | Done: **Yes**

### 5. Portfolio rebalance extension

- **API or flow name:** Rebalance branch of `POST /ai/analyze_portfolio` and `POST /ai/analyze_portfolio_async`
- **AI tasks involved:** `REVIEW_PORTFOLIO_TARGET` and conditionally `REVIEW_PORTFOLIO_ACTION_PLAN`, using the
  validated plan, research, and assessment from entry 4
- **Primary code:** `app\models\ai_portfolio_review.py`, `app\services\msai_review_portfolio.py`
- **Summary of process flow:** Derive major rebalancing from validated EXIT intent, introduced holdings, or at least
  20% one-way turnover. When a recommended rebalance was not requested, return an explicit null action plan. Otherwise
  calculate whole-share EXIT/TRIM/BUY_MORE/INTRODUCE/ACCUMULATE/HOLD actions, balance new money and sale proceeds,
  enforce LongTerm and Swing policy, and ask the final model only to rank within fixed groups and explain every
  immutable action. No-rebalance reviews always return a funded Growth plan.
- **Detailed review:** [Review portfolio redesign](detailed_review_plan/04-review-portfolio.md)
- **Status:** Reviewed: **Yes** | Implemented: **Yes** | Done: **Yes**

### 6. Shared asynchronous AI task start and polling

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
