# BTC Raw ATR5 RR NY ON — Compounding vs Fixed

**Generated:** 2026-06-26 22:56:02  
**Purpose:** Test whether compounding adds value or just increases volatility  
**Exit Mode:** ATR5 RR | **Risk:** 1% | **SL:** 1.5x ATR | **RR:** 3.0 | **Max Slots:** 3  

---

## Walk-Forward Results

### Compounding

| W# | Test Period | Trades | ROI | Sharpe | PF | Max DD | WR | Expectancy |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 2024-04 to 2024-07 | 81 | -4.3% | -0.37 | 0.89 | 20.8% | 33% | $-535 |
| 2 | 2024-08 to 2024-11 | 117 | 3.6% | 0.46 | 1.06 | 19.3% | 36% | $309 |
| 3 | 2024-12 to 2025-03 | 85 | 8.5% | 1.01 | 1.20 | 13.0% | 40% | $998 |
| 4 | 2025-04 to 2025-07 | 55 | 1.9% | 0.38 | 1.08 | 14.4% | 38% | $348 |
| 5 | 2025-08 to 2025-11 | 114 | 2.1% | 0.36 | 1.04 | 16.8% | 39% | $189 |
| 6 | 2025-12 to 2026-03 | 98 | 54.4% | 4.14 | 2.31 | 7.2% | 54% | $5,553 |

### Fixed Capital

| W# | Test Period | Trades | ROI | Sharpe | PF | Max DD | WR | Expectancy |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 2024-04 to 2024-07 | 81 | -3.1% | -0.18 | 0.93 | 22.0% | 33% | $-382 |
| 2 | 2024-08 to 2024-11 | 117 | 6.1% | 0.63 | 1.10 | 20.2% | 36% | $520 |
| 3 | 2024-12 to 2025-03 | 85 | 9.9% | 1.17 | 1.25 | 11.9% | 40% | $1,159 |
| 4 | 2025-04 to 2025-07 | 55 | 2.8% | 0.48 | 1.12 | 14.7% | 38% | $503 |
| 5 | 2025-08 to 2025-11 | 114 | 4.7% | 0.55 | 1.09 | 17.8% | 39% | $413 |
| 6 | 2025-12 to 2026-03 | 98 | 45.9% | 4.08 | 2.40 | 7.1% | 54% | $4,683 |

---

## Aggregate Comparison

| Metric | Compounding | Fixed | Winner |
|--------|:---:|:---:|:---:|
| Profitable Windows | 5/6 | 5/6 | Tie |
| Avg OOS ROI | 11.0% | 11.0% | Comp |
| Avg OOS Sharpe | 0.99 | 1.12 | Fixed |
| Avg Max DD | 15.2% | 15.6% | Comp |
| Cumulative OOS | 72.9% | 77.3% | Fixed |
| Total OOS Trades | 550 | 550 | — |
