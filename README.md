[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Actions Status](https://github.com/Bits4Bites/finhub/workflows/ci/badge.svg)](https://github.com/Bits4Bites/finhub/actions)
[![Release](https://img.shields.io/github/release/Bits4Bites/finhub.svg?style=flat-square)](RELEASE-NOTES.md)

A developer-first financial API hub for stock market data, built for frontend apps and future AI features.

## ✨ Features

- 📈 Get stock quotes and other information (from Yahoo Finance).
- 🤖 (AI Assistant) Check incoming earnings/dividend/distribution events.

## 📚 API

View [OpenAPI spec](openapi.json).

### `/stocks/quotes`

Get stock quotes for a list of ticker symbols.

Query parameters:
- `symbols` (required): A comma-separated list of ticker symbols to fetch quotes for. Each ticker symbol must follow Yahoo Finance's format (e.g., `AAPL` for Apple Inc., `CBA.AX` for Commonwealth Bank of Australia).

Examples:

```
GET /stocks/quotes?symbols=AAPL,CBA.AX
```

### `/<symbol>/info`

Get detailed information about a specific ticker symbol.

Path parameters:
- `symbol` (required): The ticker symbol to fetch information for. Must follow Yahoo Finance's format (e.g., `AAPL` for Apple Inc., `CBA.AX` for Commonwealth Bank of Australia).

Examples:

```
GET /stocks/AAPL/info
```

### `/<symbol>/overview`

Get overview information about a specific ticker symbol.

Path parameters:
- `symbol` (required): The ticker symbol to fetch information for. Must follow Yahoo Finance's format (e.g., `AAPL` for Apple Inc., `CBA.AX` for Commonwealth Bank of Australia).

Examples:

```
GET /stocks/AAPL/overview
```

### `/ai/event/earnings`

Check for incoming earnings events for a market, using AI assistance.

Query parameters:
- `country` (required): Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.).
- `index` (optional): Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.).

Examples:

```
GET /ai/event/earnings?country=AU'
```

### `/ai/event/dividends`

Check for incoming dividend/distribution events for a market, using AI assistance.

Query parameters:
- `country` (required): Country code to filter events by (e.g., 'AU', 'US', 'VN', etc.).
- `index` (optional): Optional stock index to filter events by (e.g., 'NASDAQ 100', 'S&P/ASX 200', etc.).

Examples:

```
GET /ai/event/dividends?country=AU'
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
