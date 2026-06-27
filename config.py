import os

# Clean switch: use '1 hour' or '1 day'.
# You can also override via terminal env var TIMEFRAME.
TIMEFRAME = os.getenv('TIMEFRAME', '1 hour')

# Use the legacy strategies data location only, with a portable local fallback.
_default_data_dir = r'c:\Users\anays\OneDrive\Desktop\strategies'
if not os.path.exists(_default_data_dir):
    _default_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
DATA_BASE_DIR = os.getenv('DATA_BASE_DIR', _default_data_dir)


def _env_flag(name, default=False):
    val = os.getenv(name)
    if val is None:
        return bool(default)
    return str(val).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def _env_int(name, default):
    val = os.getenv(name)
    if val is None:
        return int(default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return int(default)


# New York session filter (applies only to 1-hour candles)
USE_NY_SESSION_FILTER_1H = _env_flag('USE_NY_SESSION_FILTER_1H', False)
NY_TIMEZONE = 'America/New_York'
NY_SESSION_START_HOUR = 9
NY_SESSION_END_HOUR = 17

# Paper-trade costs
FEE_RATE_PER_SIDE = 0.0002     # 0.02% each side
SLIPPAGE_BPS_PER_SIDE = 1.0    # fallback slippage (bps per side) when regime is unknown

# Variable slippage by volatility regime (bps per side)
SLIPPAGE_BPS_BY_REGIME = {
    'low':     0.5,    # calm market — tight spreads
    'medium':  1.0,    # normal conditions
    'high':    2.0,    # elevated volatility — wider spreads
    'extreme': 5.0,    # spike / flash-crash conditions
    'unknown': 1.0,    # default when regime not available
}

# Capital and sizing for backtests
INITIAL_CAPITAL = 1_000_000.0
SL_ATR_MULT = 1.5              # Stop distance in ATR units
USE_COMPOUNDING = True         # If False, sizing uses INITIAL_CAPITAL

# Sizing mode: 'pct_risk' (recommended) or 'fixed_notional' (legacy)
SIZING_MODE = 'pct_risk'

# Percent-risk sizing: risk this fraction of capital per trade (e.g. 0.01 = 1%)
RISK_PCT_PER_TRADE = 0.01

# Fixed-notional sizing (only used when SIZING_MODE='fixed_notional')
FIXED_NOTIONAL = 500_000.0     # The dollar value of every trade
MAX_LEVERAGE = 2.0             # Max allowed leverage vs current capital

# Multi-candle backtest settings (uses evaluate_open_trade_exit)
INITIAL_SL_FALLBACK_PCT = 0.005    # If ATR unavailable: 0.5%
TRAIL_BUFFER_ATR_MULT = 0.2
ONLY_HIGH_VOL_TRADES = _env_flag('ONLY_HIGH_VOL_TRADES', True)       # Set via env var to allow entries only in high volatility regime (default: True)
MAX_DURATION_CANDLES = None        # Optional time exit
ENTRY_DELAY_TEST = False           # Optional: enter at Open[i+1]
ROLLING_VOL_WINDOW = 500           # Fixed-mode volatility quantile window

# ATR setting (used by initial SL and trailing buffer)
ATR_WINDOW = 14

# Higher-timeframe directional filter
ENABLE_4H_EMA_TREND_FILTER = _env_flag('ENABLE_4H_EMA_TREND_FILTER', True)
EMA_4H_PERIOD = _env_int('EMA_4H_PERIOD', 200)

# Exit-specific ATR and risk/reward settings
EXIT_ATR_WINDOW = 5
EXIT_ATR_COL = 'ATR_5'
EXIT_REWARD_RISK = 2.8
EXIT_BREAKOUT_ATR_MULT = 1.5

# Exit mode toggles (priority: simple_rr -> atr5_rr -> legacy)
ENABLE_EXIT_LEGACY = False
ENABLE_EXIT_ATR5_RR = False
ENABLE_EXIT_SIMPLE_RR = True

# Simple RR parameters
SIMPLE_RR = 3.0

# Concurrent trades (allow multiple open positions)
MAX_CONCURRENT_TRADES = 3

# Partial take profit: close PARTIAL_TP_CLOSE_PCT at TP1, let rest run to TP2
ENABLE_PARTIAL_TP = True
PARTIAL_TP1_RR = 2.0              # First TP at 2× risk
PARTIAL_TP_CLOSE_PCT = 0.50       # Close 50% at TP1
PARTIAL_MOVE_SL_TO_BE = True      # Move SL to breakeven after TP1
