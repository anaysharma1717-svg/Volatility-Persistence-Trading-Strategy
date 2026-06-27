import pandas as pd
import numpy as np
import config

# ---------------------------------------------------------------------------
# atr.py components
# ---------------------------------------------------------------------------
def add_atr(df, window=14, output_col='ATR'):
    # ATR uses only current/previous candle values and no future data.
    df = df.copy()
    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        (df['High'] - df['Low']).abs(),
        (df['High'] - prev_close).abs(),
        (df['Low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df[output_col] = tr.rolling(window, min_periods=window).mean()
    return df

# ---------------------------------------------------------------------------
# ema.py components
# ---------------------------------------------------------------------------
def add_ema(df, column='Close', span=20, output_col=None):
    """Add EMA for a given column. Simple helper for future expansion."""
    if output_col is None:
        output_col = f"EMA_{span}"
    series = df[column].ewm(span=span, adjust=False).mean()
    df = df.copy()
    df[output_col] = series
    return df

# ---------------------------------------------------------------------------
# parkinson.py components
# ---------------------------------------------------------------------------
def add_parkinson_volatility(df, window=20):
    # Parkinson volatility: sqrt( mean( ln(H/L)^2 ) / (4 ln(2)) )
    df = df.copy()
    hl_log_sq = np.log(df['High'] / df['Low']) ** 2
    df['park_vol'] = np.sqrt(hl_log_sq.rolling(window).mean() / (4.0 * np.log(2.0)))
    return df

# ---------------------------------------------------------------------------
# volatility.py components
# ---------------------------------------------------------------------------
def add_volatility_thresholds(
    df,
    low_q=0.33,
    high_q=0.66,
    extreme_q=0.95,
    mode='rolling',
    window=None,
    min_history=100,
    past_only=True,
):
    if window is None:
        window = config.ROLLING_VOL_WINDOW

    df = df.copy()
    valid = df['park_vol'].dropna()
    if valid.empty:
        raise ValueError('Parkinson volatility could not be computed. Check High/Low data.')

    if mode == 'rolling':
        low_thr_series     = df['park_vol'].rolling(window=window, min_periods=window).quantile(low_q)
        high_thr_series    = df['park_vol'].rolling(window=window, min_periods=window).quantile(high_q)
        extreme_thr_series = df['park_vol'].rolling(window=window, min_periods=window).quantile(extreme_q)
    elif mode == 'expanding':
        low_thr_series     = df['park_vol'].expanding(min_periods=min_history).quantile(low_q)
        high_thr_series    = df['park_vol'].expanding(min_periods=min_history).quantile(high_q)
        extreme_thr_series = df['park_vol'].expanding(min_periods=min_history).quantile(extreme_q)
    else:
        raise ValueError("mode must be 'rolling' or 'expanding'")

    if past_only:
        low_thr_series     = low_thr_series.shift(1)
        high_thr_series    = high_thr_series.shift(1)
        extreme_thr_series = extreme_thr_series.shift(1)

    df['vol_low_thr']     = low_thr_series
    df['vol_high_thr']    = high_thr_series
    df['vol_extreme_thr'] = extreme_thr_series

    # Before enough history is available, keep regime neutral as 'medium'.
    df['vol_regime'] = 'medium'
    ready = df['vol_low_thr'].notna() & df['vol_high_thr'].notna()
    df.loc[ready & (df['park_vol'] <= df['vol_low_thr']),                                             'vol_regime'] = 'low'
    df.loc[ready & (df['park_vol'] >= df['vol_high_thr']),                                            'vol_regime'] = 'high'
    df.loc[ready & df['vol_extreme_thr'].notna() & (df['park_vol'] >= df['vol_extreme_thr']),         'vol_regime'] = 'extreme'

    low_thr     = float(df['vol_low_thr'].dropna().iloc[-1])     if df['vol_low_thr'].notna().any()     else float('nan')
    high_thr    = float(df['vol_high_thr'].dropna().iloc[-1])    if df['vol_high_thr'].notna().any()    else float('nan')
    extreme_thr = float(df['vol_extreme_thr'].dropna().iloc[-1]) if df['vol_extreme_thr'].notna().any() else float('nan')
    return df, low_thr, high_thr
