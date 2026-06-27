# Volatility Persistence Trading Framework

This repository contains a quantitative breakout-momentum trading strategy designed to exploit trend persistence in cryptocurrency markets (Bitcoin and Ethereum). The strategy enters positions based on candle color transitions (using either raw single-candle momentum or state-based trend tracking that requires two consecutive opposite candles to trigger a directional switch). Entries are restricted to New York session hours (09:00 to 17:00 ET), aligned with the broader 4-hour 200-period Exponential Moving Average trend, and executed only during high-volatility regimes where trend persistence is statistically stronger.

These strategies are evaluated using a modular backtesting framework that simulates realistic execution conditions, including a dynamic slippage model linked to volatility, trading fees, concurrent position limits, and a partial take-profit system. The codebase includes components to run a combinatorial backtest across 48 parameter configurations and evaluate performance stability across consecutive 4-month segments.

For the complete backtest performance breakdown, historical charts, monthly return heatmap, cost sensitivity stress tests, and market regime diagnostics, view the [Backtest Results Report](backtest_report.md).

---

### Framework Components

Execution Engine
The simulator supports concurrent position tracking across multiple assets, entry execution delay modeling, and intra-bar trigger checking for stops and take-profits.

Exit Modeling
Trades utilize a split take-profit structure where 50% of the position closes at the first target (TP1) and the remaining position runs to the second target (TP2), with the stop loss adjusted to breakeven upon hitting TP1.

Slippage and Costs
Slippage is modeled dynamically, scaling based on the prevailing volatility regime (low, medium, high, and extreme). Standard transaction fees are applied to both entry and exit execution.

Trend and Filters
Signals are filtered through a higher-timeframe trend direction filter (4-hour EMA) and New York session execution windows (09:00 to 17:00 ET) to minimize execution during low-liquidity periods.

Rolling Window Analysis
Performance is evaluated across consecutive 4-month windows to verify strategy consistency over time.

---

### Setup and Execution

To set up the environment and install dependencies:

```bash
git clone https://github.com/anaysharma1717-svg/Volatility-Persistence-Trading-Framework.git
cd Volatility-Persistence-Trading-Framework
pip install -r requirements.txt
```

Set the path to your historical candle data directory:

```bash
# Linux/macOS
export DATA_BASE_DIR="/path/to/data"

# Windows PowerShell
$env:DATA_BASE_DIR = "C:\path\to\data"
```

To run the full backtest suite across all 48 parameter configurations:

```bash
python scripts/run_full_backtest.py
```

To run the rolling window backtest analysis:

```bash
python scripts/run_walk_forward_v2.py
```

To generate the comprehensive report containing execution charts:

```bash
python scripts/generate_backtest_report.py
```

---

### System Architecture

The core framework is split into decoupled Python modules:

- config.py: Holds operational parameters, position limits, slippage models, and target rules.
- data.py: Manages data ingestion, New York session filtering, and trend filter calculations.
- indicators.py: Computes indicators such as Average True Range (ATR) and Parkinson volatility.
- signals.py: Produces raw directional triggers and state transition signals.
- backtest.py: Executes the multi-candle simulation loop, managing position slots and exits.
- analytics.py: Computes performance metrics including Sharpe ratio, drawdown, and expectancy.

---

### Historical Results

The top-performing strategy configuration was identified as the raw breakout signal on Ethereum (ETHUSDT) with a 5-period ATR trailing exit, New York session filter active, and compounding position sizing.

Performance Summary
- Return on Investment: +383.5%
- Sharpe Ratio: 1.79
- Profit Factor: 1.63
- Maximum Drawdown: 26.4%
- Return to Drawdown Ratio: 14.52
- Total Trades: 849
- Win Rate: 43.9%
- Average Winner: $26,475
- Average Loser: -$12,690

Performance Across 4-Month Windows

Performance breakdown across consecutive 4-month historical segments:

| Window | Period | ROI | Sharpe | Status |
|---|---|---|---|---|
| W1 | Nov 2023 - Mar 2024 | +64.2% | 3.90 | Profitable |
| W2 | Mar 2024 - Jul 2024 | -14.2% | -1.92 | Unprofitable |
| W3 | Jul 2024 - Nov 2024 | +11.0% | 1.06 | Profitable |
| W4 | Nov 2024 - Mar 2025 | +18.2% | 1.65 | Profitable |
| W5 | Mar 2025 - Jul 2025 | +3.7% | 0.65 | Profitable |
| W6 | Jul 2025 - Nov 2025 | +49.5% | 3.30 | Profitable |
| W7 | Nov 2025 - Mar 2026 | +66.2% | 4.44 | Profitable |

The average return across all windows was +28.4% with an average Sharpe ratio of 2.15. The single unprofitable window (W2) occurred during a multi-month range-bound consolidation phase.

---

### Regime Diagnostics

The table below contrasts trade metrics during winning windows against those during losing windows:

| Metric | Winning Windows | Losing Windows | Difference |
|---|---|---|---|
| Average ADX | 27.82 | 28.13 | -0.31 |
| Average ATR | 37.21 | 38.32 | -1.11 |
| Average EMA 50 Slope | +0.16 | -0.32 | +0.48 |
| Trade Win Rate | 47.79% | 36.03% | +11.76% |
| Profit Factor | 1.43 | 0.74 | +0.69 |
| Maximum Consecutive Losses | 9.3 | 14.0 | -4.7 |
| TP1 Hit Rate | 47.79% | 36.03% | +11.76% |
| Stop Loss Hit Rate | 77.12% | 87.36% | -10.24% |
| Median MFE | 1.48 ATR | 0.91 ATR | +0.57 ATR |
| Median MAE | 1.02 ATR | 1.11 ATR | -0.09 ATR |

Winning and losing periods exhibit similar trend strength (ADX) and volatility (ATR). Performance degradation is primary driven by trend directionality (reflected in the negative slope of the 50-period EMA) and a reduction in post-breakout continuation, which drops the TP1 hit rate below the threshold required to trigger the breakeven stop-loss adjustment.

---

### License

This project is released under the MIT License. See the LICENSE file for details.
