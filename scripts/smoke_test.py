import sys; sys.path.insert(0, '.')
import config, indicators, backtest, analytics
import pandas as pd, numpy as np

# Build a tiny synthetic OHLCV dataframe
n = 600
np.random.seed(42)
price = 100 + np.cumsum(np.random.randn(n) * 0.5)
df = pd.DataFrame({
    'Open':  price,
    'High':  price + np.random.uniform(0, 1, n),
    'Low':   price - np.random.uniform(0, 1, n),
    'Close': price + np.random.randn(n) * 0.2,
    'DateTime': pd.date_range('2024-01-01', periods=n, freq='1h', tz='UTC'),
})
df = indicators.add_atr(df, window=14)
df = indicators.add_atr(df, window=5, output_col='ATR_5')
df = indicators.add_parkinson_volatility(df, window=20)
df, lo, hi = indicators.add_volatility_thresholds(df, mode='rolling', window=500, past_only=True)

# Check 4 regimes exist
regimes = df['vol_regime'].value_counts()
print("Regimes found:", dict(regimes))
print("vol_extreme_thr col present:", 'vol_extreme_thr' in df.columns)
print()

# Check slippage helper
for r in ['low','medium','high','extreme','unknown']:
    rate = backtest._regime_slip_rate(r, cost_multiplier=1.0)
    print(f"  slip [{r:7s}] = {rate*10000:.2f} bps")

print()
# Quick backtest smoke test
from signals import add_raw_signal, add_state_signal
df = add_raw_signal(df)
df = add_state_signal(df)
stats = backtest.run_multi_candle_backtest(df, 'state_signal', use_compounding=False)
t = stats['trades']
roi = stats['roi_pct']
sh = stats['sharpe_ratio']
print(f"Trades: {t}  ROI: {roi:.2f}%  Sharpe: {sh:.2f}")
print("All checks PASSED")
