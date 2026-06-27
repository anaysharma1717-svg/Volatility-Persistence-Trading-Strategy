import os
import pandas as pd

import config
from signals import add_raw_signal, add_state_signal

# ---------------------------------------------------------------------------
# session_filters.py components
# ---------------------------------------------------------------------------
def filter_new_york_session_1h(df, timeframe, use_filter=None):
    tf = str(timeframe).strip().lower()
    if tf not in ['1 hour', '1h', 'hour', 'hourly']:
        return df
    apply_filter = config.USE_NY_SESSION_FILTER_1H if use_filter is None else bool(use_filter)
    if not apply_filter:
        return df
    if 'DateTime' not in df.columns:
        print('NY session filter skipped: DateTime column not found.')
        return df

    tmp = df.copy()
    tmp = tmp[tmp['DateTime'].notna()].copy()
    if tmp.empty:
        print('NY session filter skipped: no valid datetimes.')
        return df

    dt_ny = tmp['DateTime'].dt.tz_convert(config.NY_TIMEZONE)
    in_session = (dt_ny.dt.hour >= config.NY_SESSION_START_HOUR) & (dt_ny.dt.hour < config.NY_SESSION_END_HOUR)

    before = len(tmp)
    tmp = tmp[in_session].copy()
    print(
        f"Applied NY session filter ({config.NY_SESSION_START_HOUR}:00-{config.NY_SESSION_END_HOUR}:00 {config.NY_TIMEZONE}) "
        f"-> {len(tmp)} of {before} candles kept"
    )
    return tmp

# ---------------------------------------------------------------------------
# loader.py components
# ---------------------------------------------------------------------------
def normalize_ohlc(df):
    col_map = {}
    for c in df.columns:
        c_lower = str(c).strip().lower()
        if 'date' in c_lower or 'time' in c_lower or 'timestamp' in c_lower:
            col_map[c] = 'Date'
        if c_lower.startswith('open'):
            col_map[c] = 'Open'
        elif c_lower.startswith('high'):
            col_map[c] = 'High'
        elif c_lower.startswith('low'):
            col_map[c] = 'Low'
        elif c_lower.startswith('close'):
            col_map[c] = 'Close'

    if col_map:
        df = df.rename(columns=col_map)

    # Fallback for no-header Binance-style files
    if 'Open' not in df.columns and df.shape[1] >= 5:
        df = df.copy()
        df.columns = [
            'Date', 'Open', 'High', 'Low', 'Close', *[f'col{i}' for i in range(5, df.shape[1])]
        ]

    if 'Open' not in df.columns or 'Close' not in df.columns:
        raise ValueError('Could not find Open/Close columns in input data.')
    if 'High' not in df.columns or 'Low' not in df.columns:
        raise ValueError('Could not find High/Low columns required for Parkinson volatility.')

    df['Open'] = pd.to_numeric(df['Open'], errors='coerce')
    df['High'] = pd.to_numeric(df['High'], errors='coerce')
    df['Low'] = pd.to_numeric(df['Low'], errors='coerce')
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    return df.dropna(subset=['Open', 'High', 'Low', 'Close'])

def add_datetime_column(df):
    df = df.copy()
    date_series = None

    if 'Date' in df.columns:
        date_series = df['Date']
    else:
        first_col = df.columns[0]
        date_series = df[first_col]

    date_series_str = date_series.astype(str).str.strip()
    parsed = pd.to_datetime(date_series_str, errors='coerce', utc=True)

    needs_reparse = False
    if parsed.notna().sum() < (0.5 * len(df)):
        needs_reparse = True
    elif parsed.notna().sum() > 0:
        median_year = parsed.dt.year.median()
        if median_year < 2015 or median_year > 2035:
            needs_reparse = True

    if needs_reparse:
        s_num = pd.to_numeric(date_series, errors='coerce')
        if s_num.notna().sum() > (0.5 * len(df)):
            s_scaled = s_num.copy()
            # Microseconds (e.g. 1735689600000000)
            is_us = s_scaled > 1e14
            s_scaled.loc[is_us] = s_scaled.loc[is_us] / 1000.0
            
            # Seconds (e.g. 1735689600)
            is_s = s_scaled < 1e11
            s_scaled.loc[is_s] = s_scaled.loc[is_s] * 1000.0
            
            parsed = pd.to_datetime(s_scaled, unit='ms', errors='coerce', utc=True)

    df['DateTime'] = parsed
    return df

def resolve_data_dir(timeframe):
    base_dir = os.path.abspath(config.DATA_BASE_DIR)
    tf = str(timeframe).strip().lower()

    if tf in ['1 hour', '1h', 'hour', 'hourly']:
        candidate_folders = ['1 hour']
    elif tf in ['1 day', '1d', 'day', 'daily']:
        candidate_folders = ['1 day', 'daily']
    else:
        candidate_folders = [timeframe]

    for folder in candidate_folders:
        path_from_base = os.path.join(base_dir, folder)
        if os.path.isdir(path_from_base):
            return path_from_base

    raise FileNotFoundError(
        f"Could not find candles folder for timeframe '{timeframe}'. "
        "Checked names like '1 hour', '1 day', and 'daily'."
    )

def read_ohlc_file(path):
    compression = 'zip' if path.lower().endswith('.zip') else None
    raw = pd.read_csv(path, header=None, compression=compression)

    # If first row looks like header, re-read with header
    first_row = raw.iloc[0].astype(str).str.lower().tolist()
    if any(('open' in x or 'close' in x or 'high' in x or 'low' in x) for x in first_row):
        df_file = pd.read_csv(path, compression=compression)
    else:
        df_file = raw

    norm = normalize_ohlc(df_file)
    return add_datetime_column(norm)

def load_candle_data(timeframe='1 hour'):
    data_dir = resolve_data_dir(timeframe)

    raw_files = sorted([
        f for f in os.listdir(data_dir)
        if f.lower().endswith('.csv') or f.lower().endswith('.zip')
    ])
    if not raw_files:
        raise FileNotFoundError(f'No CSV/ZIP candle files found in: {data_dir}')

    # Avoid double loading if both csv and zip exist for same stem. Prefer csv.
    files_by_stem = {}
    for f in raw_files:
        stem = f.rsplit('.', 1)[0]
        ext = f.rsplit('.', 1)[1].lower()
        current = files_by_stem.get(stem)
        if current is None:
            files_by_stem[stem] = f
        elif current.lower().endswith('.zip') and ext == 'csv':
            files_by_stem[stem] = f

    data_files = sorted(files_by_stem.values())

    frames = []
    for fname in data_files:
        path = os.path.join(data_dir, fname)
        frames.append(read_ohlc_file(path))

    df_all = pd.concat(frames, ignore_index=True)
    print('Timeframe:', timeframe)
    print('Loaded candles from:', data_dir)
    print('Files loaded:', len(data_files), '| Total candles:', len(df_all))
    return df_all

# ---------------------------------------------------------------------------
# preprocessing.py components
# ---------------------------------------------------------------------------
def _add_4h_ema_trend(df):
    if 'DateTime' not in df.columns or 'Close' not in df.columns:
        df = df.copy()
        df['ema_4h_trend'] = 0
        return df

    df_work = df.copy().sort_values('DateTime').reset_index(drop=True)

    close_4h = (
        df_work.set_index('DateTime')['Close']
        .resample('4h')
        .last()
        .dropna()
    )
    if close_4h.empty:
        df_work['ema_4h_trend'] = 0
        return df_work

    ema_4h = close_4h.ewm(span=int(config.EMA_4H_PERIOD), adjust=False).mean()
    trend_4h = pd.Series(0, index=close_4h.index, dtype='int64')
    trend_4h[close_4h > ema_4h] = 1
    trend_4h[close_4h < ema_4h] = -1

    # Shift one completed 4h bar to avoid using unfinished higher-timeframe state.
    trend_4h = trend_4h.shift(1).fillna(0).astype('int64')
    trend_df = trend_4h.rename('ema_4h_trend').reset_index()

    df_work = pd.merge_asof(
        df_work.sort_values('DateTime'),
        trend_df.sort_values('DateTime'),
        on='DateTime',
        direction='backward',
    )
    df_work['ema_4h_trend'] = df_work['ema_4h_trend'].fillna(0).astype('int64')
    return df_work

def _apply_ema_trend_direction_filter(df, signal_cols):
    df_out = df.copy()
    if 'ema_4h_trend' not in df_out.columns:
        return df_out

    trend = df_out['ema_4h_trend'].fillna(0).astype(int)
    for col in signal_cols:
        if col not in df_out.columns:
            continue
        sig = df_out[col].fillna(0).astype(int)
        # Longs only in bullish trend and shorts only in bearish trend.
        sig = sig.where(~((sig > 0) & (trend != 1)), 0)
        sig = sig.where(~((sig < 0) & (trend != -1)), 0)
        df_out[col] = sig
    return df_out

def add_signals(df):
    df = add_raw_signal(df)
    df = add_state_signal(df)
    if getattr(config, 'ENABLE_4H_EMA_TREND_FILTER', False):
        df = _add_4h_ema_trend(df)
        df = _apply_ema_trend_direction_filter(df, ['raw_signal', 'state_signal'])
    return df
