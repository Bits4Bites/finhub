# Copilot Instructions for FinHub

## Build, Test, and Lint

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dev server (defaults to port 8000)
python server.py
# Or with reload: RELOAD=true python server.py

# Lint
flake8 ./app
black --check --diff ./app

# Format
black ./app

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
├── config.py       # Settings via pydantic-settings (env files: ai_clients_config.env, finhub_proxy_config.env)
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
- Configuration is nested env-based via `pydantic-settings` with `ai_clients_config.env`
- Task-to-model mapping is configured via `FINHUB_LLM_TASK` settings
- Prompt templates live in `resources/prompts/`

### Data flow pattern

Routers parse/validate input → call service functions → services fetch data (yfinance, web crawling, LLM calls) → construct model objects → routers wrap in response schemas.

## Conventions

- **Symbol format**: The API accepts stock symbols in Yahoo Finance format (`CBA.AX`) or `EXCHANGE:CODE` format (`NASDAQ:AAPL`). Symbols are uppercased at the router level.
- **Response envelope**: All API responses use `BaseResponse` schema with `status`, `message`, and optional `data`/`extra` fields.
- **Models from Tickers**: Domain models in `app/models/finhub.py` accept a `yf.Ticker` as the first positional argument in `__init__` and extract fields from `ticker.info`.
- **Async for AI, sync for data**: AI/LLM service functions are `async`. Stock data fetching functions are synchronous.
- **Config via env files**: Use `pydantic-settings` with `.env` files rather than raw `os.environ`. Proxy config is in `finhub_proxy_config.env`.
- **Linting rules**: Flake8 ignores E501 (line length), E203, W503, W504. Black uses 120 char line length (configured in `pyproject.toml`).
- **Semantic release**: The project uses `action-semrelease` for versioning. Commit messages should follow conventional commits format (e.g., `Add:`, `Fix:`).
