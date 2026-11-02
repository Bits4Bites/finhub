# Copilot Instructions for FinHub

## Build, Test, and Lint

This project uses a Python virtual environment. Activate the project's virtual environment before running Python, `pip`, Ruff, pytest, or the development server.

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dev server (defaults to port 8000)
python server.py
# Or with reload: RELOAD=true python server.py

# Lint
ruff check ./app
ruff format --check --diff ./app

# Format
ruff format ./app

# Run all tests
pytest

# Run a single test
pytest tests/test_demo.py::test_always_passes
```

Python versions supported: 3.11, 3.12, 3.13, 3.14.

## Architecture

This is a **FastAPI** application serving as a financial data API hub. Entry point is `server.py` which runs `app.main:app` via uvicorn.

### Layer structure

```
app/
├── routers/        # FastAPI route handlers (thin layer, delegates to services)
├── services/       # Business logic, external API calls, LLM interactions
├── models/         # Pydantic domain models (constructed from raw data like yfinance Tickers)
├── schemas/        # Pydantic request/response schemas for the API layer
├── utils/          # Shared utilities and helpers
├── config.py       # Settings via pydantic-settings (env files: ai_vendors.env, finhub_proxy_config.env)
resources/
├── indices/        # Static data files for market index constituents
├── prompts/        # LLM prompt templates
```

### Key domains (routers)

- **stocks** – quotes, info, overviews, historical data (via `yfinance`)
- **events** – upcoming dividends, earnings, new listings (crawled/scraped)
- **ai** – LLM-powered analysis of financial events (Google Gemini, OpenAI, Azure OpenAI, OpenRouter)
- **toz** – precious metals (gold/silver) quotes and history

### AI/LLM integration

- Multiple LLM vendors supported: Google Gemini, OpenAI, Azure OpenAI, OpenRouter
- Configuration is nested env-based via `pydantic-settings` with `ai_vendors.env`
- Task-to-model mapping is configured via `FINHUB_LLM_TASK` settings
- Prompt templates live in `resources/prompts/`

### AI review and implementation rules

- **Universal AI scoring**: Apply the same scoring to every AI-related review and future AI feature: expected output quality 50%, structured-output reliability 20%, task depth 15%, cost efficiency 15%, latency efficiency 0%. Apply quality, safety, source-verification, and reliability gates before scoring. Break close scores by quality, then structured-output reliability.
- **Shared reference processing**: Use `app\utils\ai_reference.py` for URL normalization, deterministic source-ID generation, provider-citation verification, recursive reference-ID remapping, and registry validation. Do not duplicate this logic in individual AI flows.
- **Application-owned reference identity**: Treat AI-generated source IDs as temporary and untrusted. Generate final IDs from normalized source URLs, remap every nested `reference_ids` field, and reject duplicate IDs/URLs plus unknown or unused registry entries.
- **Bounded orphan-reference repair**: Unknown or unused reference IDs must never reach downstream stages. A flow may deterministically remove orphan links and unsupported claims, record explicit data gaps, prune unused sources, and then rerun strict registry validation. Never guess which source an orphan ID intended to reference.
- **Non-fatal source verification**: Retain structurally valid sources when provider citations are empty or unmatched. Set application-owned `is_verified=False` instead of failing the entire flow; set it to `True` only when attribution is verified.
- **Private drafts, public final models**: Keep provider-generated, incomplete, or flow-specific schemas private and close to the owning service. Keep final validated caller-facing models in `app\models`, make them domain-generic where appropriate, and place provider, exchange, or country constraints in the service.

### Data flow pattern

Routers parse/validate input → call service functions → services fetch data (yfinance, web crawling, LLM calls) → construct model objects → routers wrap in response schemas.

## Conventions

- **Questions are not implementation requests**: When the user asks a question, answer it and explain the reasoning. Do not make code changes or take implementation action unless the user explicitly asks for implementation.
- **Symbol format**: The API accepts stock symbols in Yahoo Finance format (`CBA.AX`) or `EXCHANGE:CODE` format (`NASDAQ:AAPL`). Symbols are uppercased at the router level.
- **Response envelope**: All API responses use `BaseResponse` schema with `status`, `message`, and optional `data`/`extra` fields.
- **Async for AI, sync for data**: AI/LLM service functions are `async`. Stock data fetching functions are synchronous.
- **Config via env files**: Use `pydantic-settings` with `.env` files rather than raw `os.environ`.
- **Do not modify release notes**: Never edit `RELEASE-NOTES.md`.
- **Semantic release**: The project uses `action-semrelease` for versioning. Commit messages should follow conventional commits format (e.g., `Add:`, `Fix:`).
- **Append-only release messages**: When adding commit messages to `.semrelease\this_release`, preserve all existing
  content exactly and append new message lines at the end. Never replace, truncate, rewrite, clean, or recreate the
  file unless the user explicitly requests that destructive behavior.
- **No re-exports after refactoring**: When moving functions/classes to a new module, update ALL callers to import from the new module directly. Do NOT add re-exports from the old module for backward compatibility. Today is 2026-05-28, I am GitHub Copilot. I am noting this down because I was so stupid that I have ignored the user's explicit asks multiple times that they asked me to note this down!
- **Module-level imports only**: Use module-level imports throughout the application (e.g., `from . import conv`) and reference symbols as `module.function`. Do NOT use direct function/symbol imports like `from .module import func`. Exception: imports from `base_req_resp` module are allowed as direct symbol imports.
