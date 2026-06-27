import pandas as pd
import config
import analytics

# ---------------------------------------------------------------------------
# costs.py components
# ---------------------------------------------------------------------------
def compute_trade_pnl(entry_price, exit_price, side, position_size, slip_rate, fee_rate):
    if side == 'LONG':
        entry_exec = entry_price * (1.0 + slip_rate) * position_size
        exit_exec = exit_price * (1.0 - slip_rate) * position_size
        mid_pnl = (exit_price - entry_price) * position_size
        gross_pnl = exit_exec - entry_exec
    else:
        entry_exec = entry_price * (1.0 - slip_rate) * position_size
        exit_exec = exit_price * (1.0 + slip_rate) * position_size
        mid_pnl = (entry_price - exit_price) * position_size
        gross_pnl = entry_exec - exit_exec

    fee_cost = (abs(entry_exec) + abs(exit_exec)) * fee_rate
    slippage_cost = mid_pnl - gross_pnl
    total_cost = fee_cost + slippage_cost
    pnl = gross_pnl - fee_cost
    ret_pct = (pnl / abs(entry_exec) * 100.0) if entry_exec != 0 else 0.0

    return {
        'entry_exec': float(entry_exec),
        'exit_exec': float(exit_exec),
        'pnl': float(pnl),
        'ret_pct': float(ret_pct),
        'total_cost': float(total_cost),
    }

# ---------------------------------------------------------------------------
# portfolio.py components
# ---------------------------------------------------------------------------
def apply_trade_pnl(current_capital, pnl):
    return float(current_capital) + float(pnl)

# ---------------------------------------------------------------------------
# sizing.py components
# ---------------------------------------------------------------------------
def compute_position_size(entry_price, capital_for_sizing, sl_distance=None):
    if entry_price <= 0 or capital_for_sizing <= 0:
        return 0.0

    mode = getattr(config, 'SIZING_MODE', 'fixed_notional')
    max_allowed_notional = float(capital_for_sizing) * float(config.MAX_LEVERAGE)

    if mode == 'pct_risk':
        if sl_distance is None or sl_distance <= 0:
            target_notional = float(config.FIXED_NOTIONAL)
        else:
            risk_dollars = float(capital_for_sizing) * float(config.RISK_PCT_PER_TRADE)
            target_size = risk_dollars / sl_distance
            target_notional = target_size * entry_price

        target_notional = min(target_notional, max_allowed_notional)
        return float(target_notional / entry_price)

    else:
        target_notional = float(config.FIXED_NOTIONAL)
        target_notional = min(target_notional, max_allowed_notional)
        return float(target_notional / entry_price)

def compute_stop_loss(entry_price, side, sl_dist):
    if side == 'LONG':
        return entry_price - sl_dist
    return entry_price + sl_dist

def _regime_slip_rate(regime: str, cost_multiplier: float = 1.0) -> float:
    """Return per-side slip rate for a given vol regime.
    Falls back to SLIPPAGE_BPS_PER_SIDE if regime not in the map.
    """
    bps_map = getattr(config, 'SLIPPAGE_BPS_BY_REGIME', {})
    regime_key = str(regime).strip().lower()
    bps = bps_map.get(regime_key, float(config.SLIPPAGE_BPS_PER_SIDE))
    return float(bps) / 10000.0 * float(cost_multiplier)

# ---------------------------------------------------------------------------
# entries.py components
# ---------------------------------------------------------------------------
def build_entry_trade(df, i, signal, current_capital, use_compounding, entry_delay=False):
    if signal == 0:
        return None

    capital_for_sizing = float(current_capital) if use_compounding else float(config.INITIAL_CAPITAL)
    if capital_for_sizing <= 0:
        return None

    entry_index = i + 1 if entry_delay else i
    if entry_index >= len(df):
        return None

    regime_ref = entry_index - 1
    regime_for_entry = (
        str(df['vol_regime'].iat[regime_ref])
        if ('vol_regime' in df.columns and regime_ref >= 0)
        else 'unknown'
    )
    if config.ONLY_HIGH_VOL_TRADES and 'vol_regime' in df.columns:
        if regime_for_entry not in ('high', 'extreme'):
            return None

    side = 'LONG' if signal == 1 else 'SHORT'
    entry_price = float(df['Open'].iat[entry_index])
    atr_ref = entry_index - 1

    atr14 = (
        float(df['ATR'].iat[atr_ref])
        if ('ATR' in df.columns and atr_ref >= 0 and df['ATR'].notna().iat[atr_ref])
        else None
    )
    atr_col = config.EXIT_ATR_COL if config.EXIT_ATR_COL in df.columns else 'ATR'
    atr5 = (
        float(df[atr_col].iat[atr_ref])
        if (atr_ref >= 0 and df[atr_col].notna().iat[atr_ref])
        else None
    )

    if atr14 is not None and atr14 > 0:
        sl_dist_legacy = float(config.SL_ATR_MULT) * atr14
    else:
        sl_dist_legacy = float(config.INITIAL_SL_FALLBACK_PCT) * entry_price

    if atr5 is not None and atr5 > 0:
        sl_dist_rr = float(config.SL_ATR_MULT) * atr5
    else:
        sl_dist_rr = float(config.INITIAL_SL_FALLBACK_PCT) * entry_price

    position_size = compute_position_size(entry_price, capital_for_sizing, sl_distance=sl_dist_rr)
    if position_size <= 0:
        return None

    legacy_stop = compute_stop_loss(entry_price, side, sl_dist_legacy)
    rr_stop = compute_stop_loss(entry_price, side, sl_dist_rr)
    rr_risk_dist = abs(entry_price - rr_stop)

    if side == 'LONG':
        rr_take_profit = entry_price + (rr_risk_dist * float(config.EXIT_REWARD_RISK))
        simple_take_profit = entry_price + (rr_risk_dist * float(config.SIMPLE_RR))
        simple_tp1 = entry_price + (rr_risk_dist * float(config.PARTIAL_TP1_RR))
    else:
        rr_take_profit = entry_price - (rr_risk_dist * float(config.EXIT_REWARD_RISK))
        simple_take_profit = entry_price - (rr_risk_dist * float(config.SIMPLE_RR))
        simple_tp1 = entry_price - (rr_risk_dist * float(config.PARTIAL_TP1_RR))

    return {
        'side': side,
        'entry_price': entry_price,
        'legacy_stop_loss': float(legacy_stop),
        'atr5_rr_stop_loss': float(rr_stop),
        'atr5_rr_take_profit': float(rr_take_profit),
        'simple_rr_stop_loss': float(rr_stop),
        'simple_rr_take_profit': float(simple_take_profit),
        'simple_rr_tp1': float(simple_tp1),      # partial TP1 level
        'tp1_hit': False,                          # partial TP1 tracking
        'remaining_pct': 1.0,                      # 1.0 = full position
        'atr14_at_entry': float(atr14) if atr14 is not None else None,
        'atr5_at_entry': float(atr5) if atr5 is not None else None,
        'sl_distance': float(sl_dist_rr),
        'entry_index': int(entry_index),
        'entry_regime': regime_for_entry,
        'position_size': float(position_size),
        'entry_notional': float(entry_price * position_size),
        'opposite_count': 0,
        'is_ambiguous': False,
        'highest_price': float(entry_price),
        'lowest_price': float(entry_price),
    }

# ---------------------------------------------------------------------------
# exits.py components
# ---------------------------------------------------------------------------
def evaluate_open_trade_exit(
    df,
    i,
    trade,
    trail_buffer_atr_mult=0.2,
    realistic_exit_timing=True,
    trailing_intrabar_trigger=True,
    max_duration_candles=None,
):
    """
    Returns (exit_price, exit_reason, is_partial)
    is_partial = True means close only a portion (TP1 hit), trade stays open.
    is_partial = False means close entire remaining position.
    """
    side = str(trade.get('side', '')).upper()
    if side not in ('LONG', 'SHORT'):
        raise ValueError("trade['side'] must be 'LONG' or 'SHORT'")

    if 'opposite_count' not in trade:
        trade['opposite_count'] = 0

    high_px = float(df['High'].iat[i])
    low_px = float(df['Low'].iat[i])
    close_px = float(df['Close'].iat[i])
    next_open_px = float(df['Open'].iat[i + 1]) if (i + 1) < len(df) else close_px
    entry_price = float(trade['entry_price'])

    # Reset ambiguity state for this candle evaluation
    trade['is_ambiguous'] = False

    is_ambiguous = False
    if config.ENABLE_EXIT_SIMPLE_RR:
        stop_loss = float(trade.get('simple_rr_stop_loss')) if trade.get('simple_rr_stop_loss') is not None else None
        tp2 = float(trade.get('simple_rr_take_profit')) if trade.get('simple_rr_take_profit') is not None else None
        tp1 = float(trade.get('simple_rr_tp1')) if trade.get('simple_rr_tp1') is not None else None

        hit_sl = False
        if stop_loss is not None:
            if side == 'LONG' and low_px <= stop_loss:
                hit_sl = True
            elif side == 'SHORT' and high_px >= stop_loss:
                hit_sl = True

        hit_tp1 = False
        if config.ENABLE_PARTIAL_TP and not trade.get('tp1_hit', False) and tp1 is not None:
            if side == 'LONG' and high_px >= tp1:
                hit_tp1 = True
            elif side == 'SHORT' and low_px <= tp1:
                hit_tp1 = True

        hit_tp2 = False
        if tp2 is not None:
            if side == 'LONG' and high_px >= tp2:
                hit_tp2 = True
            elif side == 'SHORT' and low_px <= tp2:
                hit_tp2 = True

        if hit_sl and (hit_tp1 or hit_tp2):
            is_ambiguous = True

    if config.ENABLE_EXIT_ATR5_RR:
        stop_loss = float(trade.get('atr5_rr_stop_loss')) if trade.get('atr5_rr_stop_loss') is not None else None
        take_profit = float(trade.get('atr5_rr_take_profit')) if trade.get('atr5_rr_take_profit') is not None else None

        hit_sl = False
        if stop_loss is not None:
            if side == 'LONG' and low_px <= stop_loss:
                hit_sl = True
            elif side == 'SHORT' and high_px >= stop_loss:
                hit_sl = True

        hit_tp = False
        if take_profit is not None:
            if side == 'LONG' and high_px >= take_profit:
                hit_tp = True
            elif side == 'SHORT' and low_px <= take_profit:
                hit_tp = True

        if hit_sl and hit_tp:
            is_ambiguous = True

    trade['is_ambiguous'] = is_ambiguous

    def check_rr_levels(stop_loss, take_profit):
        if stop_loss is None or take_profit is None:
            return None, None
        if side == 'LONG':
            hit_sl = low_px <= stop_loss
            hit_tp = high_px >= take_profit
            if hit_sl and hit_tp:
                return stop_loss, 'SL'
            if hit_sl:
                return stop_loss, 'SL'
            if hit_tp:
                return take_profit, 'TP'
        else:
            hit_sl = high_px >= stop_loss
            hit_tp = low_px <= take_profit
            if hit_sl and hit_tp:
                return stop_loss, 'SL'
            if hit_sl:
                return stop_loss, 'SL'
            if hit_tp:
                return take_profit, 'TP'
        return None, None

    # --- Simple RR with partial TP support ---
    if config.ENABLE_EXIT_SIMPLE_RR:
        stop_loss = float(trade.get('simple_rr_stop_loss')) if trade.get('simple_rr_stop_loss') is not None else None
        tp2 = float(trade.get('simple_rr_take_profit')) if trade.get('simple_rr_take_profit') is not None else None
        tp1 = float(trade.get('simple_rr_tp1')) if trade.get('simple_rr_tp1') is not None else None

        # Check SL first (always priority)
        if stop_loss is not None:
            if side == 'LONG' and low_px <= stop_loss:
                return stop_loss, 'SL', False
            if side == 'SHORT' and high_px >= stop_loss:
                return stop_loss, 'SL', False

        # Partial TP: check TP1 if enabled and not yet hit
        if config.ENABLE_PARTIAL_TP and not trade.get('tp1_hit', False) and tp1 is not None:
            if side == 'LONG' and high_px >= tp1:
                return tp1, 'TP1', True
            if side == 'SHORT' and low_px <= tp1:
                return tp1, 'TP1', True

        # Check TP2 (full exit for remaining position)
        if tp2 is not None:
            if side == 'LONG' and high_px >= tp2:
                return tp2, 'TP', False
            if side == 'SHORT' and low_px <= tp2:
                return tp2, 'TP', False

        # If partial TP is disabled, fall through without returning
        if not config.ENABLE_EXIT_ATR5_RR and not config.ENABLE_EXIT_LEGACY:
            return None, None, False

    # --- ATR5 RR ---
    if config.ENABLE_EXIT_ATR5_RR:
        stop_loss = float(trade.get('atr5_rr_stop_loss')) if trade.get('atr5_rr_stop_loss') is not None else None
        take_profit = float(trade.get('atr5_rr_take_profit')) if trade.get('atr5_rr_take_profit') is not None else None
        exit_px, exit_reason = check_rr_levels(stop_loss, take_profit)
        if exit_reason is not None:
            return exit_px, exit_reason, False

        if i > 0 and stop_loss is not None:
            atr_col = getattr(config, 'EXIT_ATR_COL', 'ATR_5')
            atr_now = float(df[atr_col].iat[i - 1]) if (atr_col in df.columns and pd.notna(df[atr_col].iat[i - 1])) else None
            if atr_now is not None and atr_now > 0:
                range_now = high_px - low_px
                if range_now > (float(config.EXIT_BREAKOUT_ATR_MULT) * atr_now):
                    if side == 'LONG':
                        new_stop = low_px
                        if new_stop > stop_loss:
                            trade['atr5_rr_stop_loss'] = float(new_stop)
                    else:
                        new_stop = high_px
                        if new_stop < stop_loss:
                            trade['atr5_rr_stop_loss'] = float(new_stop)

    # --- Legacy ---
    if not config.ENABLE_EXIT_LEGACY:
        return None, None, False

    stop_loss = float(trade.get('legacy_stop_loss')) if trade.get('legacy_stop_loss') is not None else None
    if stop_loss is None:
        return None, None, False

    if side == 'LONG' and low_px <= stop_loss:
        return stop_loss, 'SL', False
    if side == 'SHORT' and high_px >= stop_loss:
        return stop_loss, 'SL', False

    trail_updated = False
    if i > 0:
        atr_now = None
        if 'ATR' in df.columns:
            atr_now = float(df['ATR'].iat[i - 1]) if pd.notna(df['ATR'].iat[i - 1]) else None
        buffer = (trail_buffer_atr_mult * atr_now) if atr_now is not None else 0.0

        prev_open = float(df['Open'].iat[i - 1])
        prev_close = float(df['Close'].iat[i - 1])
        if side == 'LONG' and prev_close > entry_price:
            new_stop = prev_open - buffer
            new_sl = max(stop_loss, new_stop)
            trail_updated = new_sl > stop_loss
            trade['legacy_stop_loss'] = new_sl
            stop_loss = new_sl
        elif side == 'SHORT' and prev_close < entry_price:
            new_stop = prev_open + buffer
            new_sl = min(stop_loss, new_stop)
            trail_updated = new_sl < stop_loss
            trade['legacy_stop_loss'] = new_sl
            stop_loss = new_sl

    if trail_updated:
        if trailing_intrabar_trigger:
            if side == 'LONG' and low_px <= stop_loss:
                exit_px = next_open_px if realistic_exit_timing else close_px
                return exit_px, 'TRAIL', False
            if side == 'SHORT' and high_px >= stop_loss:
                exit_px = next_open_px if realistic_exit_timing else close_px
                return exit_px, 'TRAIL', False
        else:
            if side == 'LONG' and close_px <= stop_loss:
                exit_px = next_open_px if realistic_exit_timing else close_px
                return exit_px, 'TRAIL', False
            if side == 'SHORT' and close_px >= stop_loss:
                exit_px = next_open_px if realistic_exit_timing else close_px
                return exit_px, 'TRAIL', False

    is_bull = bool(df['Close'].iat[i] > df['Open'].iat[i])
    is_bear = bool(df['Close'].iat[i] < df['Open'].iat[i])

    if side == 'LONG':
        if is_bear:
            trade['opposite_count'] += 1
        elif is_bull:
            trade['opposite_count'] = 0
    else:
        if is_bull:
            trade['opposite_count'] += 1
        elif is_bear:
            trade['opposite_count'] = 0

    if trade['opposite_count'] >= 2:
        exit_px = next_open_px if realistic_exit_timing else close_px
        return exit_px, 'STATE', False

    if max_duration_candles is not None:
        duration = int(i - int(trade['entry_index']))
        if duration >= int(max_duration_candles):
            exit_px = next_open_px if realistic_exit_timing else close_px
            return exit_px, 'TIME', False

    return None, None, False

# ---------------------------------------------------------------------------
# engine.py — supports concurrent trades + partial take profit
# ---------------------------------------------------------------------------
def run_multi_candle_backtest(
    df,
    signal_col,
    realistic_exit_timing=True,
    trailing_intrabar_trigger=True,
    use_compounding=config.USE_COMPOUNDING,
    cost_multiplier=1.0,
    entry_delay=False,
    max_duration_candles=config.MAX_DURATION_CANDLES,
):
    results = []
    open_trades = []  # list of open trades (up to MAX_CONCURRENT_TRADES)
    max_concurrent = getattr(config, 'MAX_CONCURRENT_TRADES', 1)
    slip_rate = float(config.SLIPPAGE_BPS_PER_SIDE) / 10000.0 * float(cost_multiplier)
    fee_rate = float(config.FEE_RATE_PER_SIDE) * float(cost_multiplier)
    current_capital = float(config.INITIAL_CAPITAL)

    def finalize_exit(exit_price, exit_reason, trade, exit_index, partial_size=None):
        """Record a trade exit. partial_size overrides position_size for partial exits."""
        nonlocal current_capital
        entry_mid = float(trade['entry_price'])
        exit_mid = float(exit_price)
        side = trade['side']
        position_size = float(partial_size) if partial_size is not None else float(trade.get('position_size', 0.0))

        # Dynamic slippage: use exit candle's vol regime
        exit_regime = (
            str(df['vol_regime'].iat[exit_index])
            if 'vol_regime' in df.columns
            else 'unknown'
        )
        dynamic_slip = _regime_slip_rate(exit_regime, cost_multiplier)

        pnl_data = compute_trade_pnl(
            entry_mid,
            exit_mid,
            side,
            position_size,
            dynamic_slip,
            fee_rate,
        )

        # Capture exit date for Sharpe calculation
        exit_dt = None
        if 'DateTime' in df.columns and pd.notna(df['DateTime'].iat[exit_index]):
            exit_dt = df['DateTime'].iat[exit_index]

        # Calculate excursion (MFE / MAE)
        atr_ref = trade.get('atr14_at_entry') or trade.get('atr5_at_entry') or (trade.get('sl_distance', 1.0) / float(config.SL_ATR_MULT))
        if atr_ref <= 0:
            atr_ref = 1.0

        highest = float(trade.get('highest_price', entry_mid))
        lowest = float(trade.get('lowest_price', entry_mid))

        if side == 'LONG':
            mfe_price = highest - entry_mid
            mae_price = entry_mid - lowest
        else:
            mfe_price = entry_mid - lowest
            mae_price = highest - entry_mid

        mfe_atr = mfe_price / atr_ref
        mae_atr = mae_price / atr_ref

        results.append({
            'entry_index': int(trade['entry_index']),
            'exit_index': int(exit_index),
            'side': side,
            'entry_price': entry_mid,
            'exit_price': exit_mid,
            'exit_reason': exit_reason,
            'entry_regime': trade.get('entry_regime', 'unknown'),
            'position_size': position_size,
            'entry_notional': float(entry_mid * position_size),
            'exit_regime': str(df['vol_regime'].iat[exit_index]) if 'vol_regime' in df.columns else 'unknown',
            'pnl': pnl_data['pnl'],
            'ret_pct': pnl_data['ret_pct'],
            'cost': pnl_data['total_cost'],
            'exit_dt': exit_dt,
            'is_ambiguous': bool(trade.get('is_ambiguous', False)),
            'mfe_atr': float(mfe_atr),
            'mae_atr': float(mae_atr),
        })
        current_capital = apply_trade_pnl(current_capital, pnl_data['pnl'])

    active_trades_per_candle = []

    for i in range(1, len(df)):
        signal = int(df[signal_col].iat[i]) if pd.notna(df[signal_col].iat[i]) else 0

        # Update running MFE/MAE price extremes for open trades during this candle
        high_px = float(df['High'].iat[i])
        low_px = float(df['Low'].iat[i])
        for trade in open_trades:
            trade['highest_price'] = max(trade.get('highest_price', trade['entry_price']), high_px)
            trade['lowest_price'] = min(trade.get('lowest_price', trade['entry_price']), low_px)

        # --- Check exits for all open trades ---
        trades_to_remove = []
        for idx, trade in enumerate(open_trades):
            exit_price, exit_reason, is_partial = evaluate_open_trade_exit(
                df,
                i,
                trade,
                trail_buffer_atr_mult=config.TRAIL_BUFFER_ATR_MULT,
                realistic_exit_timing=realistic_exit_timing,
                trailing_intrabar_trigger=trailing_intrabar_trigger,
                max_duration_candles=max_duration_candles,
            )

            if exit_reason is None:
                continue

            if is_partial:
                # Partial TP1: close a portion, keep trade open with modified params
                close_pct = float(config.PARTIAL_TP_CLOSE_PCT)
                partial_size = float(trade['position_size']) * close_pct
                finalize_exit(exit_price, exit_reason, trade, i, partial_size=partial_size)

                # Update trade: reduce position, mark TP1 hit, move SL to breakeven
                trade['position_size'] = float(trade['position_size']) * (1.0 - close_pct)
                trade['remaining_pct'] = 1.0 - close_pct
                trade['tp1_hit'] = True
                if config.PARTIAL_MOVE_SL_TO_BE:
                    trade['simple_rr_stop_loss'] = float(trade['entry_price'])  # breakeven
            else:
                # Full exit: close remaining position
                remaining_size = float(trade['position_size'])
                finalize_exit(exit_price, exit_reason, trade, i, partial_size=remaining_size)
                trades_to_remove.append(idx)

        # Remove fully closed trades (in reverse order to preserve indices)
        for idx in sorted(trades_to_remove, reverse=True):
            open_trades.pop(idx)

        # --- Open new trade if we have capacity and signal exists ---
        if len(open_trades) < max_concurrent and signal != 0:
            new_trade = build_entry_trade(
                df,
                i,
                signal,
                current_capital,
                use_compounding,
                entry_delay=entry_delay,
            )
            if new_trade is not None and new_trade['entry_index'] == i:
                # Update price extremes for this new entry bar
                new_trade['highest_price'] = max(new_trade.get('highest_price', new_trade['entry_price']), high_px)
                new_trade['lowest_price'] = min(new_trade.get('lowest_price', new_trade['entry_price']), low_px)

                # Check if this new trade would exit immediately on entry bar
                exit_price, exit_reason, is_partial = evaluate_open_trade_exit(
                    df,
                    i,
                    new_trade,
                    trail_buffer_atr_mult=config.TRAIL_BUFFER_ATR_MULT,
                    realistic_exit_timing=realistic_exit_timing,
                    trailing_intrabar_trigger=trailing_intrabar_trigger,
                    max_duration_candles=max_duration_candles,
                )

                if exit_reason is not None:
                    if is_partial:
                        close_pct = float(config.PARTIAL_TP_CLOSE_PCT)
                        partial_size = float(new_trade['position_size']) * close_pct
                        finalize_exit(exit_price, exit_reason, new_trade, i, partial_size=partial_size)
                        new_trade['position_size'] = float(new_trade['position_size']) * (1.0 - close_pct)
                        new_trade['remaining_pct'] = 1.0 - close_pct
                        new_trade['tp1_hit'] = True
                        if config.PARTIAL_MOVE_SL_TO_BE:
                            new_trade['simple_rr_stop_loss'] = float(new_trade['entry_price'])
                        open_trades.append(new_trade)
                    else:
                        finalize_exit(exit_price, exit_reason, new_trade, i)
                else:
                    open_trades.append(new_trade)

        active_trades_per_candle.append(len(open_trades))

    if active_trades_per_candle:
        max_concurrent_open = int(max(active_trades_per_candle))
        avg_concurrent_open = float(sum(active_trades_per_candle) / len(active_trades_per_candle))
        from collections import Counter
        counts = Counter(active_trades_per_candle)
        concurrency_dist = {int(k): int(v) for k, v in counts.items()}
    else:
        max_concurrent_open = 0
        avg_concurrent_open = 0.0
        concurrency_dist = {}

    if not results:
        stats = analytics.compute_backtest_stats(pd.DataFrame(), config.INITIAL_CAPITAL, current_capital)
        stats['max_concurrent_open_trades'] = max_concurrent_open
        stats['avg_concurrent_open_trades'] = avg_concurrent_open
        stats['concurrency_distribution'] = concurrency_dist
        return stats

    df_res = pd.DataFrame(results)
    exit_dates = df_res['exit_dt'].values if 'exit_dt' in df_res.columns else None
    df_res = analytics.add_drawdown_columns(df_res, config.INITIAL_CAPITAL)
    stats = analytics.compute_backtest_stats(df_res, config.INITIAL_CAPITAL, current_capital, exit_dates=exit_dates)
    stats['max_concurrent_open_trades'] = max_concurrent_open
    stats['avg_concurrent_open_trades'] = avg_concurrent_open
    stats['concurrency_distribution'] = concurrency_dist
    return stats
