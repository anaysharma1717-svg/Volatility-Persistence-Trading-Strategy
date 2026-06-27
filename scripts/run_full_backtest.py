"""
run_full_backtest.py
====================
Exhaustive combinatorial backtest across all strategy variants.

Combinations:
  Symbols   : BTCUSDT, ETHUSDT
  Signals   : raw_signal, state_signal
  NY filter : OFF (all hours), ON (9–17 ET)
  Sizing    : Compounding, Fixed capital
  Exit mode : Simple RR, ATR5 RR, Legacy trailing

Metrics collected per variant:
  ROI, Sharpe, Max DD%, Profit Factor, Expectancy, Trade Count,
  Win Rate, Avg Winner, Avg Loser, Return/DD Ratio, Cost Sensitivity

Ranking: Composite robustness score (Sharpe + PF + DD + Expectancy + Trades)
Output  : Markdown report + equity-curve chart for top-ranked strategy
"""

import os
import sys
import math
import copy
import datetime
import warnings

warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import FuncFormatter

import config
from backtest import run_multi_candle_backtest
from data import filter_new_york_session_1h, add_signals, add_datetime_column
from indicators import add_atr, add_parkinson_volatility, add_volatility_thresholds

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_1H_DIR = os.path.join(config.DATA_BASE_DIR, "1 hour")
OUT_DIR     = os.path.join(PROJECT_ROOT, "reports", "full_backtest")
os.makedirs(OUT_DIR, exist_ok=True)

TIMESTAMP   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_PATH = os.path.join(OUT_DIR, f"full_backtest_{TIMESTAMP}.md")
CHART_PATH  = os.path.join(OUT_DIR, f"top_strategy_{TIMESTAMP}.png")

SYMBOLS      = ["BTCUSDT", "ETHUSDT"]
SIGNAL_COLS  = ["raw_signal", "state_signal"]
NY_OPTIONS   = [False, True]
SIZING_OPTIONS = [("Compounding", True), ("Fixed", False)]

EXIT_MODES = [
    {
        "label": "Simple RR",
        "ENABLE_EXIT_SIMPLE_RR": True,
        "ENABLE_EXIT_ATR5_RR":   False,
        "ENABLE_EXIT_LEGACY":    False,
    },
    {
        "label": "ATR5 RR",
        "ENABLE_EXIT_SIMPLE_RR": False,
        "ENABLE_EXIT_ATR5_RR":   True,
        "ENABLE_EXIT_LEGACY":    False,
    },
    {
        "label": "Legacy Trail",
        "ENABLE_EXIT_SIMPLE_RR": False,
        "ENABLE_EXIT_ATR5_RR":   False,
        "ENABLE_EXIT_LEGACY":    True,
    },
]

MIN_TRADES_FOR_RANKING = 20   # skip variants with too few trades

# ---------------------------------------------------------------------------
# Composite scoring weights (all positively oriented after inversion)
# ---------------------------------------------------------------------------
WEIGHTS = {
    "sharpe":      0.25,
    "pf":          0.20,
    "dd":          0.20,   # inverted (lower DD = higher score)
    "expectancy":  0.15,
    "trades":      0.10,   # log-normalized
    "rdd":         0.10,   # return/drawdown ratio
}

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
def load_symbol(symbol: str) -> pd.DataFrame:
    prefix = symbol.upper()
    files = sorted(
        f for f in os.listdir(DATA_1H_DIR)
        if (f.lower().endswith(".csv") or f.lower().endswith(".zip"))
        and os.path.splitext(f)[0].upper().startswith(prefix)
    )
    by_stem = {}
    for f in files:
        stem, ext = os.path.splitext(f)
        cur = by_stem.get(stem)
        if cur is None or (cur.lower().endswith(".zip") and ext.lower() == ".csv"):
            by_stem[stem] = f

    if not by_stem:
        raise FileNotFoundError(f"No 1H files for {symbol} in {DATA_1H_DIR}")

    # Process each file independently — detect header/headerless per file
    frames = []
    for fname in sorted(by_stem.values()):
        path = os.path.join(DATA_1H_DIR, fname)
        compression = "zip" if path.lower().endswith(".zip") else None
        raw = pd.read_csv(path, header=None, compression=compression)

        # Check if first row looks like a header
        first_row = raw.iloc[0].astype(str).str.lower().tolist()
        has_header = any(("open" in x or "close" in x or "high" in x) for x in first_row)

        if has_header:
            df_f = pd.read_csv(path, compression=compression)
            # Map columns to standard names
            col_map = {}
            for c in df_f.columns:
                cl = str(c).strip().lower()
                if ("date" in cl or "time" in cl) and "Date" not in col_map.values():
                    col_map[c] = "Date"
                elif cl.startswith("open") and "Open" not in col_map.values():
                    col_map[c] = "Open"
                elif cl.startswith("high") and "High" not in col_map.values():
                    col_map[c] = "High"
                elif cl.startswith("low") and "Low" not in col_map.values():
                    col_map[c] = "Low"
                elif cl.startswith("close") and "Close" not in col_map.values():
                    col_map[c] = "Close"
            if col_map:
                df_f = df_f.rename(columns=col_map)
        else:
            # Headerless Binance format: col0=timestamp, 1=open, 2=high, 3=low, 4=close
            df_f = raw.rename(columns={
                raw.columns[0]: "Date",
                raw.columns[1]: "Open",
                raw.columns[2]: "High",
                raw.columns[3]: "Low",
                raw.columns[4]: "Close",
            })

        frames.append(df_f)

    df = pd.concat(frames, ignore_index=True)

    for col in ["Open", "High", "Low", "Close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)

    # --- Date parsing ---
    df = add_datetime_column(df)
    return df.sort_values("DateTime").reset_index(drop=True)


def prepare(df_raw: pd.DataFrame, use_ny: bool) -> pd.DataFrame:
    df = filter_new_york_session_1h(df_raw.copy(), "1 hour", use_filter=use_ny)
    df = df.reset_index(drop=True)
    df = add_atr(df, window=config.ATR_WINDOW)
    df = add_atr(df, window=config.EXIT_ATR_WINDOW, output_col=config.EXIT_ATR_COL)
    df = add_parkinson_volatility(df, window=20)
    df, _, _ = add_volatility_thresholds(
        df, low_q=0.33, high_q=0.66, extreme_q=0.95,
        mode="rolling", window=config.ROLLING_VOL_WINDOW, past_only=True,
    )
    df = add_signals(df)
    return df


def set_exit_mode(mode: dict):
    config.ENABLE_EXIT_SIMPLE_RR = mode["ENABLE_EXIT_SIMPLE_RR"]
    config.ENABLE_EXIT_ATR5_RR   = mode["ENABLE_EXIT_ATR5_RR"]
    config.ENABLE_EXIT_LEGACY    = mode["ENABLE_EXIT_LEGACY"]


def run_bt(df, signal_col, use_compounding):
    return run_multi_candle_backtest(
        df, signal_col,
        realistic_exit_timing=True,
        trailing_intrabar_trigger=True,
        use_compounding=use_compounding,
        cost_multiplier=1.0,
        entry_delay=False,
        max_duration_candles=config.MAX_DURATION_CANDLES,
    )


def run_bt_stress(df, signal_col, use_compounding, cost_mult):
    return run_multi_candle_backtest(
        df, signal_col,
        realistic_exit_timing=True,
        trailing_intrabar_trigger=True,
        use_compounding=use_compounding,
        cost_multiplier=cost_mult,
        entry_delay=False,
        max_duration_candles=config.MAX_DURATION_CANDLES,
    )

# ---------------------------------------------------------------------------
# Composite ranking
# ---------------------------------------------------------------------------
def compute_composite_score(rows: list[dict]) -> list[dict]:
    """
    Normalise each metric to [0,1] then apply weights.
    Returns rows with added 'composite_score' and 'rank' columns.
    """
    eligible = [r for r in rows if r["trades"] >= MIN_TRADES_FOR_RANKING]
    if not eligible:
        return rows

    def norm(vals, invert=False):
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return [0.5] * len(vals)
        normed = [(v - mn) / (mx - mn) for v in vals]
        return [1 - v for v in normed] if invert else normed

    sharpe_n  = norm([r["sharpe_ratio"]          for r in eligible])
    pf_vals   = [min(r["profit_factor"], 10.0)   for r in eligible]   # cap at 10
    pf_n      = norm(pf_vals)
    dd_n      = norm([r["max_drawdown_pct"]       for r in eligible], invert=True)
    exp_n     = norm([r["expectancy_pnl"]         for r in eligible])
    trades_n  = norm([math.log1p(r["trades"])     for r in eligible])
    rdd_n     = norm([r["return_drawdown_ratio"]  for r in eligible])

    for i, row in enumerate(eligible):
        row["composite_score"] = (
            WEIGHTS["sharpe"]     * sharpe_n[i] +
            WEIGHTS["pf"]         * pf_n[i]     +
            WEIGHTS["dd"]         * dd_n[i]      +
            WEIGHTS["expectancy"] * exp_n[i]     +
            WEIGHTS["trades"]     * trades_n[i]  +
            WEIGHTS["rdd"]        * rdd_n[i]
        )

    eligible.sort(key=lambda r: r["composite_score"], reverse=True)
    for rank, row in enumerate(eligible, 1):
        row["rank"] = rank

    # mark ineligible rows
    eligible_ids = {id(r) for r in eligible}
    for r in rows:
        if id(r) not in eligible_ids:
            r["composite_score"] = float("nan")
            r["rank"] = None

    return rows


# ---------------------------------------------------------------------------
# Chart: equity curve + drawdown for top strategy
# ---------------------------------------------------------------------------
def plot_top_strategy(top_row: dict, chart_path: str):
    details = top_row.get("details")
    if details is None or details.empty:
        print("  [CHART] No trade details available for top strategy.")
        return

    initial = config.INITIAL_CAPITAL
    equity  = initial + details["pnl"].cumsum().values
    peak    = np.maximum.accumulate(equity)
    dd_pct  = (peak - equity) / peak * 100.0

    # x-axis: trade index
    x = np.arange(len(equity))

    fig = plt.figure(figsize=(14, 8), facecolor="#0f1117")
    gs  = gridspec.GridSpec(2, 1, height_ratios=[3, 1], hspace=0.08)

    # --- Equity panel ---
    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#0f1117")
    ax1.plot(x, equity, color="#00d4aa", linewidth=1.5, zorder=3)
    ax1.fill_between(x, initial, equity,
                     where=(equity >= initial), alpha=0.15, color="#00d4aa", zorder=2)
    ax1.fill_between(x, initial, equity,
                     where=(equity < initial),  alpha=0.20, color="#ff4d6d", zorder=2)
    ax1.axhline(initial, color="#ffffff", linewidth=0.6, linestyle="--", alpha=0.4)

    ax1.set_ylabel("Portfolio Value ($)", color="#cccccc", fontsize=11)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax1.tick_params(colors="#888888", labelbottom=False)
    for spine in ax1.spines.values():
        spine.set_edgecolor("#333333")
    ax1.grid(axis="y", color="#222222", linewidth=0.5)

    # Annotations
    label = (
        f"#{top_row['rank']}  {top_row['symbol']} · {top_row['signal']} · "
        f"{top_row['exit_mode']} · NY {top_row['ny']} · {top_row['sizing']}\n"
        f"ROI: {top_row['roi_pct']:.1f}%   Sharpe: {top_row['sharpe_ratio']:.2f}   "
        f"PF: {top_row['profit_factor']:.2f}   Max DD: {top_row['max_drawdown_pct']:.1f}%   "
        f"Trades: {top_row['trades']}   Win%: {top_row['win_rate']*100:.1f}%"
    )
    ax1.set_title(label, color="#e0e0e0", fontsize=10, pad=10, loc="left")

    # --- Drawdown panel ---
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.set_facecolor("#0f1117")
    ax2.fill_between(x, 0, -dd_pct, color="#ff4d6d", alpha=0.7, zorder=2)
    ax2.plot(x, -dd_pct, color="#ff4d6d", linewidth=0.8, zorder=3)
    ax2.set_ylabel("Drawdown (%)", color="#cccccc", fontsize=10)
    ax2.set_xlabel("Trade #", color="#888888", fontsize=10)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.tick_params(colors="#888888")
    for spine in ax2.spines.values():
        spine.set_edgecolor("#333333")
    ax2.grid(axis="y", color="#222222", linewidth=0.5)

    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Chart saved → {chart_path}")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def fmt_pf(v):
    return "∞" if math.isinf(v) else f"{v:.2f}"


def table_row(r):
    pf_str = fmt_pf(r["profit_factor"])
    al = r["avg_loser"]
    score = r.get("composite_score", float("nan"))
    rank  = r.get("rank", "-")
    return (
        f"| {rank or '-':>4} | {r['symbol']:<8} | {r['signal']:<13} | {r['exit_mode']:<12} | "
        f"{'ON' if r['ny'] else 'OFF':<3} | {r['sizing']:<11} | "
        f"{r['trades']:>6} | {r['win_rate']*100:>5.1f}% | "
        f"{r['roi_pct']:>8.1f}% | {r['sharpe_ratio']:>6.2f} | "
        f"{r['max_drawdown_pct']:>7.1f}% | {pf_str:>7} | "
        f"${r['expectancy_pnl']:>9,.0f} | ${r['avg_winner']:>9,.0f} | "
        f"${al:>9,.0f} | {r['return_drawdown_ratio']:>6.2f} | "
        f"{score:>6.3f} |"
    )


TABLE_HEADER = (
    "| Rank | Symbol   | Signal        | Exit Mode    | NY  | Sizing      | "
    "Trades | Win%  | ROI%      | Sharpe | Max DD%  | PF      | "
    "Expectancy  |  Avg Win   |  Avg Loss  | R/DD   | Score  |\n"
    "|------|----------|---------------|--------------|-----|-------------|"
    "--------|-------|-----------|--------|----------|---------|"
    "------------|------------|------------|--------|--------|"
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("\n" + "="*80)
    print("  FULL COMBINATORIAL BACKTEST")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*80)

    all_results = []

    for sym in SYMBOLS:
        print(f"\n{'─'*60}")
        print(f"  Loading {sym} …")
        df_raw = load_symbol(sym)
        n = len(df_raw)
        dt0 = df_raw["DateTime"].iloc[0].strftime("%Y-%m-%d") if n else "?"
        dt1 = df_raw["DateTime"].iloc[-1].strftime("%Y-%m-%d") if n else "?"
        print(f"  {sym}: {n:,} candles  ({dt0} → {dt1})")

        # Pre-build both NY variants once per symbol
        df_ny_off = prepare(df_raw, use_ny=False)
        df_ny_on  = prepare(df_raw, use_ny=True)
        prepared  = {False: df_ny_off, True: df_ny_on}

        for exit_mode in EXIT_MODES:
            set_exit_mode(exit_mode)
            print(f"\n  Exit: {exit_mode['label']}")

            for use_ny in NY_OPTIONS:
                df_prep = prepared[use_ny]
                ny_label = "ON" if use_ny else "OFF"

                for sig_col in SIGNAL_COLS:
                    for sizing_label, use_comp in SIZING_OPTIONS:
                        stats = run_bt(df_prep, sig_col, use_comp)
                        t = stats["trades"]

                        # Cost sensitivity: ratio of 3× vs 1× cost ROI
                        if t >= MIN_TRADES_FOR_RANKING:
                            stats_3x = run_bt_stress(df_prep, sig_col, use_comp, 3.0)
                            roi_base = stats["roi_pct"]
                            roi_3x   = stats_3x["roi_pct"]
                            cost_sens = (roi_base - roi_3x) / max(abs(roi_base), 1.0)
                        else:
                            cost_sens = float("nan")

                        row = {
                            "symbol":               sym,
                            "signal":               sig_col,
                            "exit_mode":            exit_mode["label"],
                            "ny":                   use_ny,
                            "ny_label":             ny_label,
                            "sizing":               sizing_label,
                            "use_comp":             use_comp,
                            # Core metrics
                            "trades":               stats["trades"],
                            "wins":                 stats["wins"],
                            "losses":               stats["losses"],
                            "win_rate":             stats["win_rate"],
                            "roi_pct":              stats["roi_pct"],
                            "sharpe_ratio":         stats["sharpe_ratio"],
                            "max_drawdown_pct":     stats["max_drawdown_pct"],
                            "profit_factor":        stats["profit_factor"],
                            "expectancy_pnl":       stats["expectancy_pnl"],
                            "avg_winner":           stats["avg_winner"],
                            "avg_loser":            stats["avg_loser"],
                            "return_drawdown_ratio":stats["return_drawdown_ratio"],
                            "total_pnl":            stats["total_pnl"],
                            "final_capital":        stats["final_capital"],
                            "cost_sensitivity":     cost_sens,
                            "ambiguous":            stats["ambiguous_sl_tp_count"],
                            "exit_reason_counts":   stats["exit_reason_counts"],
                            "details":              stats.get("details"),
                        }
                        all_results.append(row)

                        tick = "✓" if t >= MIN_TRADES_FOR_RANKING else "·"
                        print(f"    {tick} NY {ny_label} | {sig_col:<13} | {sizing_label:<11} → "
                              f"trades={t:>4}  ROI={stats['roi_pct']:>7.1f}%  "
                              f"Sharpe={stats['sharpe_ratio']:>5.2f}  "
                              f"PF={fmt_pf(stats['profit_factor']):>5}  "
                              f"DD={stats['max_drawdown_pct']:>5.1f}%")

    # Ranking
    print(f"\n{'─'*60}")
    print("  Computing composite scores …")
    all_results = compute_composite_score(all_results)

    eligible = [r for r in all_results if r.get("rank") is not None]
    eligible.sort(key=lambda r: r["rank"])

    # Top 10 summary
    print(f"\n{'='*80}")
    print("  TOP 10 STRATEGIES BY COMPOSITE ROBUSTNESS SCORE")
    print("="*80)
    for r in eligible[:10]:
        pf = fmt_pf(r["profit_factor"])
        print(f"  #{r['rank']:>2}  {r['symbol']:<8} {r['signal']:<13} {r['exit_mode']:<12} "
              f"NY {r['ny_label']}  {r['sizing']:<11}  "
              f"Score={r['composite_score']:.3f}  ROI={r['roi_pct']:>7.1f}%  "
              f"Sharpe={r['sharpe_ratio']:>5.2f}  PF={pf:>5}  "
              f"DD={r['max_drawdown_pct']:>5.1f}%  T={r['trades']}")

    # Best strategy chart
    top = eligible[0]
    print(f"\n  Generating equity chart for #{top['rank']} …")
    plot_top_strategy(top, CHART_PATH)

    # ---------------------------------------------------------------------------
    # Markdown report
    # ---------------------------------------------------------------------------
    lines = [
        "# Full Combinatorial Backtest Report\n\n",
        f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n",
        f"**Data:** {', '.join(SYMBOLS)}  \n",
        f"**Total variants tested:** {len(all_results)}  \n",
        f"**Eligible for ranking (trades ≥ {MIN_TRADES_FOR_RANKING}):** {len(eligible)}  \n\n",
        "## Ranking Weights\n\n",
        "| Metric | Weight | Direction |\n|--------|--------|-----------|\n",
        f"| Sharpe Ratio       | 25% | Higher → better |\n",
        f"| Profit Factor      | 20% | Higher → better |\n",
        f"| Max Drawdown%      | 20% | Lower → better  |\n",
        f"| Expectancy (PnL)   | 15% | Higher → better |\n",
        f"| Trade Count (log)  | 10% | Higher → better |\n",
        f"| Return/DD Ratio    | 10% | Higher → better |\n\n",
        "---\n\n",
        "## All Ranked Variants\n\n",
        TABLE_HEADER + "\n",
    ]

    for r in eligible:
        lines.append(table_row(r) + "\n")

    if len(all_results) - len(eligible) > 0:
        lines.append(f"\n*{len(all_results) - len(eligible)} variants excluded (< {MIN_TRADES_FOR_RANKING} trades)*\n\n")

    # Top 10 detailed breakdown
    lines.append("\n---\n\n## Top 10 Detailed Breakdown\n\n")
    for r in eligible[:10]:
        pf = fmt_pf(r["profit_factor"])
        lines += [
            f"### #{r['rank']} — {r['symbol']} · {r['signal']} · {r['exit_mode']} · NY {r['ny_label']} · {r['sizing']}\n\n",
            f"| Metric | Value |\n|--------|-------|\n",
            f"| Composite Score | {r['composite_score']:.4f} |\n",
            f"| ROI | {r['roi_pct']:.2f}% |\n",
            f"| Sharpe Ratio | {r['sharpe_ratio']:.3f} |\n",
            f"| Max Drawdown | {r['max_drawdown_pct']:.2f}% |\n",
            f"| Profit Factor | {pf} |\n",
            f"| Expectancy | ${r['expectancy_pnl']:,.0f} |\n",
            f"| Trade Count | {r['trades']} |\n",
            f"| Win Rate | {r['win_rate']*100:.1f}% |\n",
            f"| Avg Winner | ${r['avg_winner']:,.0f} |\n",
            f"| Avg Loser | ${r['avg_loser']:,.0f} |\n",
            f"| Return/DD Ratio | {r['return_drawdown_ratio']:.2f} |\n",
            f"| Cost Sensitivity | {r['cost_sensitivity']:.3f} |\n",
            f"| Ambiguous SL/TP | {r['ambiguous']} |\n",
            f"| Exit Reasons | {r['exit_reason_counts']} |\n\n",
        ]

    # Config snapshot
    lines += [
        "---\n\n## Config Snapshot\n\n",
        "| Parameter | Value |\n|-----------|-------|\n",
        f"| SIZING_MODE | {config.SIZING_MODE} |\n",
        f"| RISK_PCT_PER_TRADE | {config.RISK_PCT_PER_TRADE*100:.1f}% |\n",
        f"| INITIAL_CAPITAL | ${config.INITIAL_CAPITAL:,.0f} |\n",
        f"| MAX_CONCURRENT_TRADES | {config.MAX_CONCURRENT_TRADES} |\n",
        f"| SL_ATR_MULT | {config.SL_ATR_MULT} |\n",
        f"| SIMPLE_RR | {config.SIMPLE_RR} |\n",
        f"| PARTIAL_TP1_RR | {config.PARTIAL_TP1_RR} |\n",
        f"| PARTIAL_TP_CLOSE_PCT | {config.PARTIAL_TP_CLOSE_PCT*100:.0f}% |\n",
        f"| ONLY_HIGH_VOL_TRADES | {config.ONLY_HIGH_VOL_TRADES} |\n",
        f"| ENABLE_4H_EMA_TREND_FILTER | {config.ENABLE_4H_EMA_TREND_FILTER} |\n",
        f"| ROLLING_VOL_WINDOW | {config.ROLLING_VOL_WINDOW} |\n",
        f"| SLIPPAGE_BPS_BY_REGIME | {config.SLIPPAGE_BPS_BY_REGIME} |\n",
        f"| FEE_RATE_PER_SIDE | {config.FEE_RATE_PER_SIDE*100:.3f}% |\n\n",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\n{'='*80}")
    print(f"  Report → {REPORT_PATH}")
    print(f"  Chart  → {CHART_PATH}")
    print("="*80)


if __name__ == "__main__":
    main()
