import numpy as np

# ---------------------------------------------------------------------------
# filters.py components
# ---------------------------------------------------------------------------
def is_high_vol_regime(df, idx):
    if 'vol_regime' not in df.columns:
        return False
    return str(df['vol_regime'].iat[idx]) == 'high'

# ---------------------------------------------------------------------------
# raw_signal.py components
# ---------------------------------------------------------------------------
def add_raw_signal(df):
    df = df.copy()
    if 'bull' not in df.columns:
        df['bull'] = df['Close'] > df['Open']
    if 'bear' not in df.columns:
        df['bear'] = df['Close'] < df['Open']

    prev_bull_signal = df['bull'].shift(1).fillna(False)
    prev_bear_signal = df['bear'].shift(1).fillna(False)
    df['raw_signal'] = np.where(prev_bull_signal, 1, np.where(prev_bear_signal, -1, 0))
    return df

# ---------------------------------------------------------------------------
# state_signal.py components
# ---------------------------------------------------------------------------
def add_state_with_two_opposites(df):
    # Switch trend state only after 2 consecutive opposite candles.
    df = df.copy()
    if 'bull' not in df.columns:
        df['bull'] = df['Close'] > df['Open']
    if 'bear' not in df.columns:
        df['bear'] = df['Close'] < df['Open']

    state = None
    states = []
    opposite_count = 0

    for i in range(len(df)):
        if i == 0:
            states.append(None)
            continue

        if state is None:
            if bool(df['bull'].iat[i]):
                state = 'GREEN'
            elif bool(df['bear'].iat[i]):
                state = 'RED'
            states.append(state)
            continue

        # Keep prior state on doji candles (Open == Close).
        if bool(df['bull'].iat[i]):
            current = 'GREEN'
        elif bool(df['bear'].iat[i]):
            current = 'RED'
        else:
            states.append(state)
            continue

        if current == state:
            opposite_count = 0
        else:
            opposite_count += 1
            if opposite_count >= 2:
                state = current
                opposite_count = 0

        states.append(state)

    df['state'] = states
    return df

def add_state_signal(df):
    df = add_state_with_two_opposites(df)
    df['state_signal'] = np.where(df['state'].shift(1) == 'GREEN', 1, np.where(df['state'].shift(1) == 'RED', -1, 0))
    return df
