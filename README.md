# Volatility Persistence Trading Framework

This repository contains a quantitative breakout-momentum trading strategy designed to exploit trend persistence in cryptocurrency markets (Bitcoin and Ethereum). The strategy enters positions based on candle color transitions (using either raw single-candle momentum or state-based trend tracking that requires two consecutive opposite candles to trigger a directional switch). Entries are restricted to New York session hours (09:00 to 17:00 ET), aligned with the broader 4-hour 200-period Exponential Moving Average trend, and executed only during high-volatility regimes where trend persistence is statistically stronger.

These strategies are evaluated using a modular backtesting framework that simulates realistic execution conditions, including a dynamic slippage model linked to volatility, trading fees, concurrent position limits, and a partial take-profit system. The codebase includes components to run a combinatorial backtest across 48 parameter configurations and evaluate performance stability across consecutive 4-month segments.

For the complete backtest performance breakdown, historical charts, monthly return heatmap, cost sensitivity stress tests, and market regime diagnostics, view the [Backtest Results Report](backtest_report.md).

---

### Framework Components

#### 1. Execution Engine
The simulator supports concurrent position tracking across multiple assets, entry execution delay modeling, and intra-bar trigger checking for stops and take-profits via the [run_multi_candle_backtest](file:///c:/Users/anays/OneDrive/Desktop/trading-system/backtest.py#L415) engine.

#### 2. Capital and Position Sizing
* **Initial Capital**: Default backtests are initialized with **\$1,000,000** as defined by `INITIAL_CAPITAL` in [config.py](file:///c:/Users/anays/OneDrive/Desktop/trading-system/config.py).
* **Sizing Modes**:
  * **Percentage Risk Sizing (`pct_risk`)**: Risks a specified fraction of capital per trade (default `RISK_PCT_PER_TRADE = 0.01` or 1%). The position size is calculated dynamically:
    $$\text{Position Size} = \frac{\text{Capital} \times \text{Risk Percent}}{\text{Entry Price} - \text{Stop Loss Price}}$$
  * **Fixed Notional Sizing (`fixed_notional`)**: Allocates a static dollar amount to each trade (default `FIXED_NOTIONAL = $500,000`).
* **Compounding Sizing**: Configured via `USE_COMPOUNDING = True` in [config.py](file:///c:/Users/anays/OneDrive/Desktop/trading-system/config.py). When enabled, position sizing scales dynamically with the current accumulated capital. Otherwise, it scales based on the static `INITIAL_CAPITAL`.
* **Leverage Constraints**: Position sizes are capped by a maximum leverage limit (`MAX_LEVERAGE = 2.0` times current capital) to mitigate catastrophic risk.

#### 3. Volatility Model & Mathematics
The framework uses **Parkinson Volatility** (implemented in [add_parkinson_volatility](file:///c:/Users/anays/OneDrive/Desktop/trading-system/indicators.py#L35)), which is an extreme-value volatility estimator that utilizes the High and Low prices of each period rather than just the Close. This makes it more sensitive to intra-bar price action.

**Mathematical Formula:**
$$\sigma_P = \sqrt{\frac{1}{4 \ln(2) \cdot N} \sum_{i=1}^{N} \left(\ln\left(\frac{H_i}{L_i}\right)\right)^2}$$

Where:
* $\sigma_P$ is the Parkinson Volatility over a window $N$.
* $H_i$ is the High price of period $i$.
* $L_i$ is the Low price of period $i$.
* $N$ is the rolling window size (default `window=20` in [indicators.py](file:///c:/Users/anays/OneDrive/Desktop/trading-system/indicators.py)).
* $4 \ln(2)$ is the normalization constant derived from the range of continuous-time Brownian motion.

**Volatility Regimes & Slippage Scaling:**
The Parkinson Volatility is compared against historical quantiles over a rolling window (default `ROLLING_VOL_WINDOW = 500` in [config.py](file:///c:/Users/anays/OneDrive/Desktop/trading-system/config.py)):
* **Low Volatility**: $\leq 33\text{rd}$ percentile (calm markets; dynamic slippage is scaled to 0.5 bps per side).
* **Medium Volatility**: Between $33\text{rd}$ and $66\text{th}$ percentiles (normal conditions; dynamic slippage is scaled to 1.0 bps per side).
* **High Volatility**: Between $66\text{th}$ and $95\text{th}$ percentiles (active trend conditions; dynamic slippage is scaled to 2.0 bps per side).
* **Extreme Volatility**: $\geq 95\text{th}$ percentile (market stress / spikes; dynamic slippage is scaled to 5.0 bps per side).

By default, trade entries are restricted to the High and Extreme regimes (`ONLY_HIGH_VOL_TRADES = True`) to focus execution on high-momentum periods.

#### 4. Exit Strategies
The framework implements three configurable exit strategies inside [evaluate_open_trade_exit](file:///c:/Users/anays/OneDrive/Desktop/trading-system/backtest.py#L175):

* **Simple Risk/Reward Exit (`simple_rr`)**:
  * **Initial Stop Loss (SL)**: Placed at $1.5 \times \text{ATR}_5$ from the entry price.
  * **Take Profit (TP)**:
    * **Partial TP (TP1)**: Placed at $2.0 \times \text{Risk Distance}$ (where risk distance is $| \text{Entry} - \text{SL} |$). If hit, closes 50% of the position and adjusts the Stop Loss of the remaining position to the entry price (breakeven).
    * **Final TP (TP2)**: Placed at $3.0 \times \text{Risk Distance}$ (closes the remaining 50% of the position).
* **ATR-Based Risk/Reward Exit (`atr5_rr`)**:
  * **Initial SL**: Placed at $1.5 \times \text{ATR}_5$ from the entry price.
  * **Take Profit (TP)**: Placed at $2.8 \times \text{Risk Distance}$ to close the entire position.
  * **Dynamic Breakout Trail**: If a single candle's range ($\text{High} - \text{Low}$) exceeds $1.5 \times \text{ATR}_5$, the Stop Loss trails dynamically by moving to the current candle's Low (for LONG trades) or High (for SHORT trades), provided it is more favorable than the current stop.
* **Legacy Exit Strategy (`legacy`)**:
  * **Initial SL**: Placed at $1.5 \times \text{ATR}_{14}$ from the entry price.
  * **Trailing Stop**: Trails behind the previous candle's Open price with a buffer of $0.2 \times \text{ATR}_{14}$ if the trade moves in favor of the position.
  * **State-Based Exit**: Closes the trade at the next candle's Open if the candle color is opposite to the position direction for two consecutive periods (e.g. 2 bearish candles for a LONG position, or 2 bullish candles for a SHORT position).
  * **Time-Based Exit**: Closes the trade after a maximum number of candles has elapsed, if configured.

#### 5. Trend and Session Filters
* **Trend Filter**: Signals are filtered through a higher-timeframe trend direction filter (4-hour 200-period EMA) to restrict entries to the primary trend direction.
* **Session Filter**: Entries are restricted to New York session hours (09:00 to 17:00 ET) to minimize execution during low-liquidity periods.

#### 6. Walk-Forward and Backtest Reports
* **Reports Location**: Running `python scripts/generate_backtest_report.py` generates a comprehensive performance report at [backtest_report.md](file:///c:/Users/anays/OneDrive/Desktop/trading-system/backtest_report.md).
* **Generated Assets**: The report includes 9 diagnostic charts saved under [reports/backtest_report/](file:///c:/Users/anays/OneDrive/Desktop/trading-system/reports/backtest_report):
  1. `01_equity_curves_*.png`: Comparative equity growth curves for the top 6 strategy configurations.
  2. `02_drawdown_curves_*.png`: Peak-to-trough equity drawdowns.
  3. `03_monthly_heatmap_*.png`: Monthly return distribution heatmap for the top-performing strategy.
  4. `04_pnl_distribution_*.png`: Win/loss trade PnL distribution histogram.
  5. `05_wf_roi_bars_*.png`: Walk-forward out-of-sample ROI per 4-month window.
  6. `06_wf_sharpe_*.png`: Walk-forward out-of-sample Sharpe ratio per window.
  7. `07_strategy_comparison_*.png`: Comparison bar chart of ROI, Sharpe, and Maximum Drawdown across strategies.
  8. `08_exit_breakdown_*.png`: Pie chart breakdown of trade exit reasons (e.g., SL, TP, State, Trail, Time).
  9. `3min_cost_analysis.png`: Stress tests evaluating strategy sensitivity to transaction costs and slippage.

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
