[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Actions Status](https://github.com/Bits4Bites/finhub/workflows/ci/badge.svg)](https://github.com/Bits4Bites/finhub/actions)
[![Release](https://img.shields.io/github/release/Bits4Bites/finhub.svg?style=flat-square)](RELEASE-NOTES.md)

A developer-first financial API hub for stock market data, built for frontend apps and future AI features.

## ✨ Features

- 📈 Get stock quotes and other information (from Yahoo Finance).
- 🤖 (AI Assistant) Check incoming earnings/dividend/distribution events.

## 📚 API

View [OpenAPI spec](openapi.json).

### `GET /ai/analyze_dividend_event`

Analyzes a dividend event.

Query parameters:
- `symbol` (required): The stock symbol. Accept Yahoo Finance format (`CBA.AX` for Commonwealth Bank of Australia) or EXCHANGE:CODE format (`NASDAQ:AAPL` for Apple Inc.).
- `ex_date` (required): The ex-dividend date in `YYYY-MM-DD` format (e.g., `2026-04-01`).
- `div_amount` (required): The dividend amount as float number, without currency symbol (e.g., `0.50`).

Examples:

```shell
curl -X 'GET' \
  'http://localhost:8000/ai/analyze_dividend_event?symbol=AAPL&ex_date=2026-02-09&div_amount=0.26' \
  -H 'accept: application/json'
```

### `GET /events/upcoming_dividends`

Check for incoming dividend/distribution events for a market.

Query parameters:
- `country` (required): Country code to filter events by (only `AU`, `US` and `VN` are supported).
- `index` (optional): Optional stock index to filter events by (support `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `VN30` and `VN100`).

Examples:

```shell
curl -X 'GET' \
  'http://localhost:8000/events/upcoming_dividends?country=AU&index=ASX200' \
  -H 'accept: application/json'
```

### `get /events/upcoming_earnings`

Check for incoming earnings events for a market.

Query parameters:
- `country` (required): Country code to filter events by (only `AU`, `US` and `VN` are supported).
- `index` (optional): Optional stock index to filter events by (support `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `VN30` and `VN100`).

Examples:

```shell
curl -X 'GET' \
  'http://localhost:8000/events/upcoming_earnings?country=AU&index=ASX200' \
  -H 'accept: application/json'
```

### `GET /events/new_listings`

Check for new listing events for a market.

Query parameters:
- `country` (required): Country code to filter events by (only `AU` is supported).

Examples:

```shell
curl -X 'GET' \
  'http://localhost:8000/events/new_listings?country=AU' \
  -H 'accept: application/json'
```

### `GET /stocks/quotes`

Get stock quotes for a list of ticker symbols.

Query parameters:
- `symbols` (required): A comma-separated list of stock symbols to fetch quotes for, accepting Yahoo Finance format (`CBA.AX` for Commonwealth Bank of Australia) or EXCHANGE:CODE (`NASDAQ:AAPL` for Apple Inc.)

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/stocks/quotes?symbols=AAPL%2CASX%3ACBA' \
  -H 'accept: application/json'
```

### `GET /stocks/<symbol>/overview`

Get overview information about a specific ticker symbol.

Path parameters:
- `symbol` (required): The ticker symbol to fetch information for, accepting Yahoo Finance format (`CBA.AX` for Commonwealth Bank of Australia) or EXCHANGE:CODE (`NASDAQ:AAPL` for Apple Inc.)

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/stocks/AAPL/overview' \
  -H 'accept: application/json'
```

### `GET /stocks/<symbol>/info`

Get detailed information about a specific ticker symbol.

Path parameters:
- `symbol` (required): The ticker symbol to fetch information for, accepting Yahoo Finance format (`CBA.AX` for Commonwealth Bank of Australia) or EXCHANGE:CODE (`NASDAQ:AAPL` for Apple Inc.)

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/stocks/AAPL/info' \
  -H 'accept: application/json'
```

### `GET /stocks/<symbol>/quote_at/<date>`

Get stock quote information for a given ticker symbol at a specific date.

Path parameters:
- `symbol` (required): The ticker symbol to fetch information for, accepting Yahoo Finance format (`CBA.AX` for Commonwealth Bank of Australia) or EXCHANGE:CODE (`NASDAQ:AAPL` for Apple Inc.)
- `date` (required): The date to fetch the stock quote for, in format `YYYY-MM-DD` (e.g. `2026-04-01`).

Examples:

```shell
curl -X 'GET' \
  'http://localhost:8000/stocks/AAPL/quote_at/2026-04-01' \
  -H 'accept: application/json'
```

> If the date falls on a non-trading day, the API may return quote for the most recent trading day before the given date.

### `GET /stocks/index/<index>/companies`

Gets list of companies for a given index. Note: current supported indices are `ASX20`, `ASX50`, `ASX100`, `ASX200`, `ASX300`, `NASDAQ100`, `SP500`, `SP400`, `SP600`, `VN30`, `VN100` and `HNX30`.

Path parameters:
- `index` (required): The index to fetch companies for.

Examples:

```shell
curl -X 'GET' \
  'http://localhost:8000/stocks/index/NASDAQ100/companies' \
  -H 'accept: application/json'
```

> Warning: the data may not be up-to-date as the API currently relies on static data files for index constituents, which are updated periodically.

### `GET /toz/gold/quote`

Check the current price of gold.

Query parameters:
- `currency` (optional): The currency to return the gold price in. Defaults to `USD`. For example, `AUD`, `USD`, `EUR`, etc.

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/toz/gold/quote?currency=AUD' \
  -H 'accept: application/json'
```

### `GET /toz/gold/history`

Get historical gold price data.

Query parameters:
- `currency` (optional): The currency to return the gold price in. Defaults to `USD`. For example, `AUD`, `USD`, `EUR`, etc.
- `days` (optional): The number of past days to return historical data for. Defaults to `30`. For example, `7`, `30`, `90`, etc.

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/toz/gold/history?currency=AUD&days=30' \
  -H 'accept: application/json'
```

### `GET /toz/silver/quote`

Check the current price of silver.

Query parameters:
- `currency` (optional): The currency to return the silver price in. Defaults to `USD`. For example, `AUD`, `USD`, `EUR`, etc.

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/toz/silver/quote?currency=AUD' \
  -H 'accept: application/json'
```

### `GET /toz/silver/history`

Get historical silver price data.

Query parameters:
- `currency` (optional): The currency to return the silver price in. Defaults to `USD`. For example, `AUD`, `USD`, `EUR`, etc.
- `days` (optional): The number of past days to return historical data for. Defaults to `30`. For example, `7`, `30`, `90`, etc.

Example:

```shell
curl -X 'GET' \
  'http://localhost:8000/toz/silver/history?currency=AUD&days=30' \
  -H 'accept: application/json'
```

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
