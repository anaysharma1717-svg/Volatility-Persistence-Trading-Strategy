import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# sharpe.py components
# ---------------------------------------------------------------------------
def compute_sharpe_daily(trade_pnls, trade_dates, initial_capital, risk_free_rate=0.0):
    """
    Compute annualized Sharpe from daily time-series returns.
    trade_pnls: array of PnL per trade
    trade_dates: array of exit dates (datetime) per trade
    initial_capital: starting capital
    """
    if len(trade_pnls) < 2 or trade_dates is None or len(trade_dates) < 2:
        return 0.0

    # Build daily PnL series by summing trade PnLs per calendar date
    pnl_series = pd.Series(np.asarray(trade_pnls, dtype=float), index=pd.to_datetime(trade_dates))
    daily_pnl = pnl_series.groupby(pnl_series.index.date).sum()

    # Fill missing calendar days with zero PnL
    if len(daily_pnl) < 2:
        return 0.0
    full_range = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq='D')
    daily_pnl = daily_pnl.reindex(full_range, fill_value=0.0)

    # Convert daily PnL to daily returns (based on running capital)
    equity = initial_capital + daily_pnl.cumsum()
    equity_prev = equity.shift(1).fillna(initial_capital)
    daily_returns = (daily_pnl / equity_prev).values

    if len(daily_returns) < 2:
        return 0.0

    # Crypto trades 365 days/year
    periods_per_year = 365
    excess = daily_returns - (risk_free_rate / periods_per_year)
    std = np.std(excess, ddof=1)
    if std == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * np.mean(excess) / std)

# ---------------------------------------------------------------------------
# drawdown.py components
# ---------------------------------------------------------------------------
def add_drawdown_columns(df_res, initial_capital):
    if df_res.empty:
        return df_res

    df_res = df_res.copy()
    df_res['capital_after_trade'] = float(initial_capital) + df_res['pnl'].cumsum()
    df_res['peak_capital'] = df_res['capital_after_trade'].cummax()
    df_res['drawdown'] = df_res['peak_capital'] - df_res['capital_after_trade']
    df_res['drawdown_pct'] = np.where(
        df_res['peak_capital'] != 0,
        (df_res['drawdown'] / df_res['peak_capital']) * 100.0,
        0.0,
    )
    return df_res

def compute_equity_curve(details_df, initial_capital):
    if details_df is None or details_df.empty:
        return pd.Series([float(initial_capital)], name='equity_curve')

    curve = float(initial_capital) + details_df['pnl'].fillna(0.0).cumsum()
    return curve.reset_index(drop=True)

def compute_drawdown_curve(equity_curve):
    if equity_curve is None or len(equity_curve) == 0:
        return pd.DataFrame({'equity': [], 'drawdown': [], 'drawdown_pct': []})

    series = pd.Series(equity_curve, dtype=float).reset_index(drop=True)
    peak = series.cummax()
    drawdown = peak - series
    drawdown_pct = np.where(peak != 0, (drawdown / peak) * 100.0, 0.0)
    return pd.DataFrame({
        'equity': series,
        'drawdown': drawdown,
        'drawdown_pct': drawdown_pct,
    })

# ---------------------------------------------------------------------------
# metrics.py components
# ---------------------------------------------------------------------------
def compute_backtest_stats(details_df, initial_capital, final_capital, exit_dates=None):
    if details_df is None or details_df.empty:
        return {
            'trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'expectancy_pnl': 0.0, 'expectancy_ret_pct': 0.0, 'avg_trade_return': 0.0,
            'sharpe_ratio': 0.0, 'total_pnl': 0.0, 'total_cost': 0.0,
            'avg_cost_per_trade': 0.0, 'initial_capital': float(initial_capital),
            'final_capital': float(final_capital), 'roi_pct': 0.0,
            'avg_position_size': 0.0, 'max_position_size': 0.0,
            'avg_notional_exposure': 0.0, 'max_notional_exposure': 0.0,
            'max_drawdown': 0.0, 'max_drawdown_pct': 0.0,
            'exit_reason_counts': {}, 'details': pd.DataFrame(),
            'ambiguous_sl_tp_count': 0,
            'profit_factor': 0.0, 'avg_winner': 0.0, 'avg_loser': 0.0,
            'return_drawdown_ratio': 0.0,
        }

    df_res = details_df
    trades = len(df_res)
    wins = int((df_res['pnl'] > 0).sum())
    losses = int((df_res['pnl'] < 0).sum())
    win_rate = (wins / trades) if trades else 0.0
    total_pnl = float(df_res['pnl'].sum())
    roi_pct = ((float(final_capital) / float(initial_capital)) - 1.0) * 100.0 if initial_capital else 0.0
    max_drawdown = float(df_res['drawdown'].max()) if not df_res.empty and 'drawdown' in df_res.columns else 0.0
    max_drawdown_pct = float(df_res['drawdown_pct'].max()) if not df_res.empty and 'drawdown_pct' in df_res.columns else 0.0

    avg_trade_return = float(df_res['ret_pct'].mean()) if 'ret_pct' in df_res.columns else 0.0

    # Compute Sharpe from daily time-series returns (correct method)
    trade_pnls = df_res['pnl'].values
    sharpe_ratio = compute_sharpe_daily(trade_pnls, exit_dates, initial_capital)

    ambiguous_sl_tp_count = int(df_res['is_ambiguous'].sum()) if 'is_ambiguous' in df_res.columns else 0

    # --- Robustness metrics ---
    winning_pnls = df_res.loc[df_res['pnl'] > 0, 'pnl']
    losing_pnls  = df_res.loc[df_res['pnl'] < 0, 'pnl']
    gross_profit = float(winning_pnls.sum()) if not winning_pnls.empty else 0.0
    gross_loss   = float(losing_pnls.abs().sum()) if not losing_pnls.empty else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
    avg_winner = float(winning_pnls.mean()) if not winning_pnls.empty else 0.0
    avg_loser  = float(losing_pnls.mean())  if not losing_pnls.empty else 0.0   # negative value
    return_drawdown_ratio = (roi_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0

    avg_mfe_atr = float(df_res['mfe_atr'].mean()) if 'mfe_atr' in df_res.columns else 0.0
    avg_mae_atr = float(df_res['mae_atr'].mean()) if 'mae_atr' in df_res.columns else 0.0

    return {
        'trades': int(trades), 'wins': wins, 'losses': losses, 'win_rate': float(win_rate),
        'expectancy_pnl': float(df_res['pnl'].mean()), 'expectancy_ret_pct': float(df_res['ret_pct'].mean()),
        'avg_trade_return': avg_trade_return, 'sharpe_ratio': float(sharpe_ratio),
        'total_pnl': total_pnl, 'total_cost': float(df_res['cost'].sum()),
        'avg_cost_per_trade': float(df_res['cost'].mean()), 'initial_capital': float(initial_capital),
        'final_capital': float(final_capital), 'roi_pct': float(roi_pct),
        'avg_position_size': float(df_res['position_size'].mean()) if 'position_size' in df_res.columns else 0.0,
        'max_position_size': float(df_res['position_size'].max()) if 'position_size' in df_res.columns else 0.0,
        'avg_notional_exposure': float(df_res['entry_notional'].mean()) if 'entry_notional' in df_res.columns else 0.0,
        'max_notional_exposure': float(df_res['entry_notional'].max()) if 'entry_notional' in df_res.columns else 0.0,
        'max_drawdown': max_drawdown, 'max_drawdown_pct': max_drawdown_pct,
        'exit_reason_counts': df_res['exit_reason'].value_counts().to_dict(), 'details': df_res,
        'ambiguous_sl_tp_count': ambiguous_sl_tp_count,
        'profit_factor': float(profit_factor),
        'avg_winner': float(avg_winner),
        'avg_loser': float(avg_loser),
        'return_drawdown_ratio': float(return_drawdown_ratio),
        'avg_mfe_atr': avg_mfe_atr,
        'avg_mae_atr': avg_mae_atr,
    }

def compute_segment_stats(details_df, initial_capital, exit_dates=None):
    if details_df is None or details_df.empty:
        return compute_backtest_stats(pd.DataFrame(), initial_capital, initial_capital)

    segment = add_drawdown_columns(details_df.copy(), initial_capital)
    final_capital = float(initial_capital) + float(segment['pnl'].sum())
    return compute_backtest_stats(segment, initial_capital, final_capital, exit_dates=exit_dates)

# ---------------------------------------------------------------------------
# stress_tests.py components
# Note: since this references engine.run_multi_candle_backtest, we will use local imports or it's separated at usage level.
# To avoid circular imports, run_multi_candle_backtest is imported locally in compute_stress_summary if used.
# ---------------------------------------------------------------------------
def compute_stress_summary(df_fixed, signal_col, multipliers=(1.0, 2.0, 3.0)):
    import config
    from backtest import run_multi_candle_backtest  # using the new consolidated module

    rows = []
    for mult in multipliers:
        stats = run_multi_candle_backtest(
            df_fixed,
            signal_col,
            realistic_exit_timing=True,
            trailing_intrabar_trigger=True,
            use_compounding=config.USE_COMPOUNDING,
            cost_multiplier=mult,
            entry_delay=False,
            max_duration_candles=config.MAX_DURATION_CANDLES,
        )
        details = stats.get('details', pd.DataFrame())

        rows.append({
            'multiplier': float(mult), 'regime': 'overall', 'trades': int(stats.get('trades', 0)),
            'total_pnl': float(stats.get('total_pnl', 0.0)),
            'final_capital': float(stats.get('final_capital', config.INITIAL_CAPITAL)),
            'capital_change': float(stats.get('final_capital', config.INITIAL_CAPITAL)) - float(config.INITIAL_CAPITAL),
        })

        for regime in ('low', 'medium', 'high'):
            sub = details[details['exit_regime'] == regime] if not details.empty else pd.DataFrame()
            regime_pnl = float(sub['pnl'].sum()) if not sub.empty else 0.0
            regime_trades = int(len(sub)) if not sub.empty else 0
            regime_final_cap = float(config.INITIAL_CAPITAL) + regime_pnl
            rows.append({
                'multiplier': float(mult), 'regime': regime, 'trades': regime_trades,
                'total_pnl': regime_pnl, 'final_capital': regime_final_cap,
                'capital_change': regime_final_cap - float(config.INITIAL_CAPITAL),
            })

    return pd.DataFrame(rows)
