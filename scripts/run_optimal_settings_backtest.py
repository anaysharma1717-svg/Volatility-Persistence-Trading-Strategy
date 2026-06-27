"""
run_optimal_settings_backtest.py
================================
Run the optimal settings backtest for BTC and ETH on the full consolidated 3-year dataset.

Optimal settings:
- ETHUSDT: State signal, 2% risk, SL = 1.0x ATR, TP1 = 1.5x, RR Target = 4.0, Max Concurrent = 5, NY ON.
- BTCUSDT: Raw signal, 2% risk, SL = 1.5x ATR, TP1 = 1.5x, RR Target = 2.5, Max Concurrent = 5, NY ON.
"""

import os
import sys
import warnings
import datetime
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import config
from backtest import run_multi_candle_backtest
from scripts.run_full_backtest import load_symbol, prepare

def run_optimal_btc():
    print("\n" + "=" * 50)
    print("  BTCUSDT OPTIMAL BACKTEST (Full 3-Year)")
    print("=" * 50)
    
    # 1. Load data
    df_raw = load_symbol("BTCUSDT")
    print(f"Loaded {len(df_raw)} raw candles.")
    
    # 2. Configure BTC optimal settings
    config.USE_NY_SESSION_FILTER_1H = True
    config.SIZING_MODE = 'pct_risk'
    config.RISK_PCT_PER_TRADE = 0.02
    config.USE_COMPOUNDING = True
    config.MAX_CONCURRENT_TRADES = 5
    config.SL_ATR_MULT = 1.5
    config.ENABLE_EXIT_SIMPLE_RR = True
    config.ENABLE_EXIT_ATR5_RR = False
    config.ENABLE_EXIT_LEGACY = False
    config.SIMPLE_RR = 2.5
    config.ENABLE_PARTIAL_TP = True
    config.PARTIAL_TP1_RR = 1.5
    config.PARTIAL_TP_CLOSE_PCT = 0.50
    config.PARTIAL_MOVE_SL_TO_BE = True
    config.ONLY_HIGH_VOL_TRADES = True
    config.ENABLE_4H_EMA_TREND_FILTER = True
    
    # 3. Prepare data (with NY ON)
    df = prepare(df_raw, use_ny=True)
    print(f"Prepared data: {len(df)} candles.")
    
    # 4. Run backtest
    stats = run_multi_candle_backtest(
        df, "raw_signal",
        realistic_exit_timing=True,
        trailing_intrabar_trigger=True,
        use_compounding=True,
        cost_multiplier=1.0,
    )
    
    print_results("BTCUSDT", stats)
    return stats

def run_optimal_eth():
    print("\n" + "=" * 50)
    print("  ETHUSDT OPTIMAL BACKTEST (Full 3-Year)")
    print("=" * 50)
    
    # 1. Load data
    df_raw = load_symbol("ETHUSDT")
    print(f"Loaded {len(df_raw)} raw candles.")
    
    # 2. Configure ETH optimal settings
    config.USE_NY_SESSION_FILTER_1H = True
    config.SIZING_MODE = 'pct_risk'
    config.RISK_PCT_PER_TRADE = 0.02
    config.USE_COMPOUNDING = True
    config.MAX_CONCURRENT_TRADES = 5
    config.SL_ATR_MULT = 1.0
    config.ENABLE_EXIT_SIMPLE_RR = True
    config.ENABLE_EXIT_ATR5_RR = False
    config.ENABLE_EXIT_LEGACY = False
    config.SIMPLE_RR = 4.0
    config.ENABLE_PARTIAL_TP = True
    config.PARTIAL_TP1_RR = 1.5
    config.PARTIAL_TP_CLOSE_PCT = 0.50
    config.PARTIAL_MOVE_SL_TO_BE = True
    config.ONLY_HIGH_VOL_TRADES = True
    config.ENABLE_4H_EMA_TREND_FILTER = True
    
    # 3. Prepare data (with NY ON)
    df = prepare(df_raw, use_ny=True)
    print(f"Prepared data: {len(df)} candles.")
    
    # 4. Run backtest
    stats = run_multi_candle_backtest(
        df, "state_signal",
        realistic_exit_timing=True,
        trailing_intrabar_trigger=True,
        use_compounding=True,
        cost_multiplier=1.0,
    )
    
    print_results("ETHUSDT", stats)
    return stats

def print_results(symbol: str, stats: dict):
    print(f"\n--- Results for {symbol} ---")
    print(f"Total Trades       : {stats['trades']}")
    print(f"Win Rate           : {stats['win_rate'] * 100:.1f}%")
    print(f"ROI (%)            : {stats['roi_pct']:.2f}%")
    print(f"Sharpe Ratio       : {stats['sharpe_ratio']:.3f}")
    print(f"Max Drawdown (%)   : {stats['max_drawdown_pct']:.2f}%")
    print(f"Profit Factor      : {stats['profit_factor']:.3f}")
    print(f"Expectancy ($)     : ${stats['expectancy_pnl']:,.2f}")
    print(f"Avg Winner ($)     : ${stats['avg_winner']:,.2f}")
    print(f"Avg Loser ($)      : ${stats['avg_loser']:,.2f}")
    print(f"Return/DD Ratio    : {stats['return_drawdown_ratio']:.2f}")
    print(f"Ambiguous Trades   : {stats['ambiguous_sl_tp_count']}")
    print(f"Exit Reasons       : {stats['exit_reason_counts']}")

def main():
    run_optimal_btc()
    run_optimal_eth()

if __name__ == "__main__":
    main()
