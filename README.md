# qnd-papi-template

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Actions Status](https://github.com/Bits4Bites/finhub/workflows/ci/badge.svg)](https://github.com/Bits4Bites/finhub/actions)
[![Release](https://img.shields.io/github/release/Bits4Bites/finhub.svg?style=flat-square)](RELEASE-NOTES.md)

A developer-first financial API hub for stock market data, built for frontend apps and future AI features.

## ✨ Features

- 📈 Get stock quotes and other information (from Yahoo Finance).

## 📚 API

### `/stocks/quotes`

Get stock quotes for a list of ticker symbols.

Query parameters:
- `symbols` (required): A comma-separated list of ticker symbols to fetch quotes for. Each ticker symbol must follow Yahoo Finance's format (e.g., `AAPL` for Apple Inc., `CBA.AX` for Commonwealth Bank of Australia).

Examples:

Request
```
GET /stocks/quotes?symbols=AAPL,CBA.AX
```

Response:
```json
{
  "status": 200,
  "message": "ok",
  "data": {
    "AAPL": {
      "market_price": 273.68,
      "market_price_change": -0.940002,
      "market_price_change_percent": -0.342292,
      "market_open": 274.885,
      "market_day_high": 275.36,
      "market_day_low": 272.94,
      "fifty_two_week_high": 288.62,
      "fifty_two_week_low": 169.21,
      "market_volume": 34343365,
      "bid": 273.06,
      "bid_size": 2,
      "ask": 274.03,
      "ask_size": 3,
      "market_cap": 4022528114688,
      "trailing_eps": 7.88,
      "forward_eps": 9.29181,
      "trailing_p_e": 34.730965,
      "forward_p_e": 29.453894,
      "beta": 1.107,
      "recommendation_key": "buy",
      "target_high_price": 350,
      "target_low_price": 205,
      "target_mean_price": 293.06952,
      "target_median_price": 300
    },
    "CBA.AX": {
      "market_price": 170.88,
      "market_price_change": 12.139999,
      "market_price_change_percent": 7.6477256,
      "market_open": 165,
      "market_day_high": 172.08,
      "market_day_low": 164.27,
      "fifty_two_week_high": 192,
      "fifty_two_week_low": 140.21,
      "market_volume": 2356644,
      "bid": 170.88,
      "bid_size": 0,
      "ask": 170.88,
      "ask_size": 0,
      "market_cap": 285711138816,
      "trailing_eps": 6.05,
      "forward_eps": 6.52965,
      "trailing_p_e": 28.244629,
      "forward_p_e": 26.169855,
      "beta": 0.855,
      "recommendation_key": "sell",
      "target_high_price": 139.6,
      "target_low_price": 99.81328,
      "target_mean_price": 120.74381,
      "target_median_price": 123.5
    }
  }
}
```

### `/<symbol>/info`

Get detailed information about a specific ticker symbol.

Path parameters:
- `symbol` (required): The ticker symbol to fetch information for. Must follow Yahoo Finance's format (e.g., `AAPL` for Apple Inc., `CBA.AX` for Commonwealth Bank of Australia).

Examples:

Request
```
GET /stocks/AAPL/info
```

Response:
```json
{
  "status": 200,
  "message": "ok",
  "data": {
    "symbol": "AAPL",
    "currency": "USD",
    "exchange": "NasdaqGS",
    "overview": {
      "country": "United States",
      "short_name": "Apple Inc.",
      "long_name": "Apple Inc.",
      "sector": "Technology",
      "industry": "Consumer Electronics",
      "website": "https://www.apple.com",
      "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide. The company offers iPhone, a line of smartphones; Mac, a line of personal computers; iPad, a line of multi-purpose tablets; and wearables, home, and accessories comprising AirPods, Apple Vision Pro, Apple TV, Apple Watch, Beats products, and HomePod, as well as Apple branded and third-party accessories. It also provides AppleCare support and cloud services; and operates various platforms, including the App Store that allow customers to discover and download applications and digital content, such as books, music, video, games, and podcasts, as well as advertising services include third-party licensing arrangements and its own advertising platforms. In addition, the company offers various subscription-based services, such as Apple Arcade, a game subscription service; Apple Fitness+, a personalized fitness service; Apple Music, which offers users a curated listening experience with on-demand radio stations; Apple News+, a subscription news and magazine service; Apple TV, which offers exclusive original content and live sports; Apple Card, a co-branded credit card; and Apple Pay, a cashless payment service, as well as licenses its intellectual property. The company serves consumers, and small and mid-sized businesses; and the education, enterprise, and government markets. It distributes third-party applications for its products through the App Store. The company also sells its products through its retail and online stores, and direct sales force; and third-party cellular network carriers and resellers. The company was formerly known as Apple Computer, Inc. and changed its name to Apple Inc. in January 2007. Apple Inc. was founded in 1976 and is headquartered in Cupertino, California.",
      "quote_type": "EQUITY"
    },
    "stock_quote": {
      "market_price": 273.68,
      "market_price_change": -0.940002,
      "market_price_change_percent": -0.342292,
      "market_open": 274.885,
      "market_day_high": 275.36,
      "market_day_low": 272.94,
      "fifty_two_week_high": 288.62,
      "fifty_two_week_low": 169.21,
      "market_volume": 34343365,
      "bid": 273.06,
      "bid_size": 2,
      "ask": 274.03,
      "ask_size": 3,
      "market_cap": 4022528114688,
      "trailing_eps": 7.88,
      "forward_eps": 9.29181,
      "trailing_p_e": 34.730965,
      "forward_p_e": 29.453894,
      "beta": 1.107,
      "recommendation_key": "buy",
      "target_high_price": 350,
      "target_low_price": 205,
      "target_mean_price": 293.06952,
      "target_median_price": 300
    },
    "dividend": {
      "dividend_rate": 1.04,
      "dividend_yield": 0.38,
      "ex_dividend_date": 1770595200,
      "five_year_avg_dividend_yield": 0.52,
      "trailing_annual_dividend_rate": 1.03,
      "trailing_annual_dividend_yield": 0.0037506372,
      "last_dividend_value": 0.26,
      "last_dividend_date": 1770595200
    },
    "stock_history": {
      "recent_high_price": 277.8599853515625,
      "pull_pack_percent": 1.5043521543746257,
      "current_volume": 34341400,
      "average_volume_30d": 51623225,
      "ma10": 269.05054931640626,
      "ma20": 261.3650863647461,
      "ma50": 268.3369714355469,
      "ma100": 264.86364669799804,
      "ma200": 238.7767985534668,
      "rsi14": 81.93639419654752,
      "rsi14_history_daily": [
        {
          "timestamp": 1770699600,
          "value": 81.93639419654752
        },
        {
          "timestamp": 1770613200,
          "value": 84.22614707782293
        },
        {
          "timestamp": 1770354000,
          "value": 74.16046132279104
        }
      ]
    }
  }
}
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
   git clone https://github.com/YOUR_USERNAME/qnd-papi-template.git
   cd qnd-papi-template
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
