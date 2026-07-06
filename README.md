[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Actions Status](https://github.com/Bits4Bites/finhub/workflows/ci/badge.svg)](https://github.com/Bits4Bites/finhub/actions)
[![Release](https://img.shields.io/github/release/Bits4Bites/finhub.svg?style=flat-square)](RELEASE-NOTES.md)

A developer-first financial API hub for stock market data, built for frontend apps and future AI features.

## ✨ Features

- 📈 Stock quotes, detailed info, overviews, and historical data (via Yahoo Finance).
- 📅 Upcoming market events: dividends, earnings, and new listings (AU, US, VN markets).
- 🤖 AI-powered analysis: dividend events and portfolio evaluation.
- 🥇 Precious metals: gold/silver prices and historical data in multiple currencies.

## 🚀 Usage

### Requirements

- Python **3.12+** (CI tests against 3.12, 3.13, and 3.14).
- Python dependencies from `requirements.txt`.
- [Playwright](https://playwright.dev/) WebKit browser (used by the event crawlers).

```bash
pip install -r requirements.txt
playwright install webkit
```

### Run from the command line

```bash
python server.py
```

By default, the server listens on port `8000` (configurable via `LISTEN_PORT`). To enable
auto-reload during development, set `RELOAD=true`.

### Run from a pre-built Docker image

A pre-built image is published to Docker Hub as [`btnguyen2k/finhub`](https://hub.docker.com/r/btnguyen2k/finhub):

| Tag          | Description                          |
|--------------|--------------------------------------|
| `:release`   | Latest released (stable) version     |
| `:dev`       | Latest development version           |
| `:x.y.z`     | Released version `x.y.z`             |
| `:x.y.z-dev` | Development build of version `x.y.z` |

```bash
docker run --rm -p 8000:8000 btnguyen2k/finhub:release
```

### Environment variables

Configuration is provided via environment variables, conventionally grouped into `.env` files.

#### Application (`app_config.env`)

| Variable         | Default | Description                                                                |
|------------------|---------|----------------------------------------------------------------------------|
| `LISTEN_PORT`    | `8000`  | Port the server listens on.                                                |
| `NUM_WORKERS`    | `2`     | Number of server worker processes (forced to 1 / disabled on Windows).     |
| `RELOAD`         | `false` | Enable auto-reload on code changes (development only).                     |
| `FINHUB_API_KEY` | _empty_ | API key protecting all endpoints. If empty, no authentication is required. |

#### AI vendors (`ai_vendors.env`)

Configure LLM vendor credentials and available models. Keys follow the pattern
`FINHUB_LLM__<VENDOR>__<TIER>__<SETTING>`, where:

- `<VENDOR>`: `GEMINI`, `AZURE_OPENAI`, or `OPENROUTER`.
- `<TIER>`: `FREE`, `LOWCOST`, or `PREMIUM`.
- `<SETTING>`: `API_KEY`, `ENDPOINT`, or `MODELS` (comma-separated list).

A tier is disabled when its `API_KEY` is empty. Example:

```env
FINHUB_LLM__AZURE_OPENAI__PREMIUM__API_KEY="..."
FINHUB_LLM__AZURE_OPENAI__PREMIUM__ENDPOINT="https://..."
FINHUB_LLM__AZURE_OPENAI__PREMIUM__MODELS="gpt-5.4, gpt-5.5"
```

#### AI task routing (`ai_tasks.env`)

Map each AI task to a vendor/tier/model using the pattern
`FINHUB_LLM_TASK__<TASK>__<SETTING>`, where `<SETTING>` is `VENDOR`, `TIER`, `MODEL`, or `TEMPERATURE`
(`TEMPERATURE` is optional and defaults to `0.2`).
Tasks include `ANALYZE_TICKER_*`, `BUILD_PORTFOLIO_*`, `REVIEW_PORTFOLIO_*`,
`SPOTLIGHT_PORTFOLIO_*`, `ANALYZE_DIV_EVENT_*`, and `ASX_LISTTINGS_*`. Example:

```env
FINHUB_LLM_TASK__ANALYZE_TICKER_EXEC__VENDOR="Azure OpenAI"
FINHUB_LLM_TASK__ANALYZE_TICKER_EXEC__TIER="Premium"
FINHUB_LLM_TASK__ANALYZE_TICKER_EXEC__MODEL="gpt-5.4"
FINHUB_LLM_TASK__ANALYZE_TICKER_EXEC__TEMPERATURE=0.3
```

#### Proxy (`finhub_proxy_config.env`)

FinHub distinguishes between two independent proxying concepts:

- **Node chaining** (`FINHUB_PROXY_MODE` + `FINHUB_URL_WEB_CRAWL_NODE`): when `FINHUB_PROXY_MODE` is set (i.e. not `None`), API calls to this FinHub node are redirected or forwarded to the next FinHub node in the chain, which is pointed to by `FINHUB_URL_WEB_CRAWL_NODE`.
- **External fetching via proxy** (`FINHUB_FETCH_WEBSITE_VIA_PROXY`): when this FinHub node makes requests to external websites, setting `FINHUB_FETCH_WEBSITE_VIA_PROXY` causes those outbound requests to be made through the configured HTTP proxies.

| Variable                         | Default | Description                                                                                                                                                      |
|----------------------------------|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `FINHUB_PROXY_MODE`              | `None`  | Node-chaining mode: `None`, `Redirect`, or `Forward`. If set (not `None`), API calls to this node are redirected/forwarded to the next FinHub node in the chain. |
| `FINHUB_URL_WEB_CRAWL_NODE`      | _empty_ | URL of the next FinHub node in the chain (used when `FINHUB_PROXY_MODE` is set).                                                                                 |
| `FINHUB_FETCH_WEBSITE_VIA_PROXY` | `false` | If `true`, this node's requests to external websites are made through the configured HTTP proxies.                                                               |

## 📚 API

See [API.md](API.md) for full API documentation, or view the [OpenAPI spec](openapi.json).

## 🤝 Contributing

We welcome contributions from the community! Here's how you can help:

### Reporting Issues

If you find a bug or have a suggestion:

1. **Search existing issues** to avoid duplicates
2. **Create a new issue** on GitHub:
   - Go to: https://github.com/Bits4Bytes/finhub/issues/new
   - Provide a clear title and description
   - Include steps to reproduce (for bugs)
   - Add relevant labels (bug, enhancement, question, etc.)

### Submitting Pull Requests

1. **Fork the repository** to your GitHub account

2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/finhub.git
   cd finhub
   ```

3. **Create a new branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

4. **Make your changes** following the project's coding standards

5. **Test your changes** thoroughly:
   ```bash
   # Run tests
   pytest
   
   # Run linters
   flake8 ./app
   black --check ./app
   ```

6. **Commit your changes** with clear, descriptive messages:
   ```bash
   git add .
   git commit -m "Add: brief description of your changes"
   ```

7. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

8. **Create a Pull Request**:
   - Go to the original repository
   - Click "New Pull Request"
   - Select your fork and branch
   - Provide a clear title and description
   - Reference any related issues (e.g., "Fixes #123")

### Code Contribution Guidelines

- Follow [PEP 8](https://peps.python.org/pep-0008/) style guide for Python code
- Write clear, self-documenting code with appropriate comments
- Add unit tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting PR
- Keep pull requests focused on a single feature or fix

## 📄 License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## 🙏 Acknowledgments

- Thanks to all contributors who help improve this project
- Built with ❤️ by the community

## 📞 Contact & Support

- **Issues**: [GitHub Issues](https://github.com/Bits4Bites/finhub/issues)
