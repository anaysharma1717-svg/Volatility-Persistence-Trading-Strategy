"""
run_walk_forward_v2.py
======================
Walk-forward analysis for 6 strategy variants with 4-month test windows.

Strategies:
  1. ETH State NY ON (Fixed, Optimal)       — Most robust candidate
  2. ETH Raw NY ON (Fixed, Optimal)         — Highest fixed-capital ROI
  3. ETH Raw NY ON (Compounding, Optimal)   — Highest overall ROI
  4. BTC Raw NY ON (Fixed, Optimal)         — Best BTC Simple RR strategy
  5. BTC Raw ATR5 RR NY ON (Compounding)    — Top BTC from full backtest
  6. BTC Raw ATR5 RR NY ON (Fixed)          — BTC ATR5 fixed-capital version

Window design:
  - 8-month rolling training window
  - 4-month non-overlapping test window
  - Walk forward until data exhausted

ETH (Mar 2023 → May 2026 ≈ 39 months):
  W1: Train Mar–Oct 2023,  Test Nov 2023–Feb 2024
  W2: Train Jul 2023–Feb 2024,  Test Mar–Jun 2024
  W3: Train Nov 2023–Jun 2024,  Test Jul–Oct 2024
  W4: Train Mar–Oct 2024,  Test Nov 2024–Feb 2025
  W5: Train Jul 2024–Feb 2025,  Test Mar–Jun 2025
  W6: Train Nov 2024–Jun 2025,  Test Jul–Oct 2025
  W7: Train Mar–Oct 2025,  Test Nov 2025–Feb 2026
  W8: Train Jul 2025–Feb 2026,  Test Mar–May 2026

BTC (Aug 2023 → May 2026 ≈ 34 months):
  W1: Train Aug 2023–Mar 2024,  Test Apr–Jul 2024
  W2: Train Dec 2023–Jul 2024,  Test Aug–Nov 2024
  W3: Train Apr–Nov 2024,  Test Dec 2024–Mar 2025
  W4: Train Aug 2024–Mar 2025,  Test Apr–Jul 2025
  W5: Train Dec 2024–Jul 2025,  Test Aug–Nov 2025
  W6: Train Apr–Nov 2025,  Test Dec 2025–Mar 2026
  W7: Train Aug 2025–Mar 2026,  Test Apr–May 2026
"""

import os
import sys
import math
import warnings
import datetime
import json

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
from scripts.run_full_backtest import load_symbol, prepare

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
OUT_DIR = os.path.join(PROJECT_ROOT, "reports", "walk_forward_v2")
os.makedirs(OUT_DIR, exist_ok=True)
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------
STRATEGIES = [
    {
        "id": "eth_state_fixed",
        "label": "ETH State NY ON (Fixed, Optimal)",
        "symbol": "ETHUSDT",
        "signal": "state_signal",
        "compounding": False,
        "risk": 0.02,
        "sl_mult": 1.0,
        "rr": 4.0,
        "tp1_rr": 1.5,
        "max_concurrent": 5,
    },
    {
        "id": "eth_raw_fixed",
        "label": "ETH Raw NY ON (Fixed, Optimal)",
        "symbol": "ETHUSDT",
        "signal": "raw_signal",
        "compounding": False,
        "risk": 0.02,
        "sl_mult": 1.0,
        "rr": 4.0,
        "tp1_rr": 1.5,
        "max_concurrent": 5,
    },
    {
        "id": "eth_raw_comp",
        "label": "ETH Raw NY ON (Compounding, Optimal)",
        "symbol": "ETHUSDT",
        "signal": "raw_signal",
        "compounding": True,
        "risk": 0.02,
        "sl_mult": 1.0,
        "rr": 4.0,
        "tp1_rr": 1.5,
        "max_concurrent": 5,
    },
    {
        "id": "btc_raw_fixed",
        "label": "BTC Raw NY ON (Fixed, Optimal)",
        "symbol": "BTCUSDT",
        "signal": "raw_signal",
        "compounding": False,
        "risk": 0.02,
        "sl_mult": 1.5,
        "rr": 2.5,
        "tp1_rr": 1.5,
        "max_concurrent": 5,
        "exit_mode": "simple_rr",
    },
    {
        "id": "btc_atr5_comp",
        "label": "BTC Raw ATR5 RR NY ON (Compounding)",
        "symbol": "BTCUSDT",
        "signal": "raw_signal",
        "compounding": True,
        "risk": 0.01,
        "sl_mult": 1.5,
        "rr": 3.0,
        "tp1_rr": 2.0,
        "max_concurrent": 3,
        "exit_mode": "atr5_rr",
    },
    {
        "id": "btc_atr5_fixed",
        "label": "BTC Raw ATR5 RR NY ON (Fixed)",
        "symbol": "BTCUSDT",
        "signal": "raw_signal",
        "compounding": False,
        "risk": 0.01,
        "sl_mult": 1.5,
        "rr": 3.0,
        "tp1_rr": 2.0,
        "max_concurrent": 3,
        "exit_mode": "atr5_rr",
    },
]

# ---------------------------------------------------------------------------
# Walk-forward window definitions
# ---------------------------------------------------------------------------
ETH_WINDOWS = [
    ("2023-03-01", "2023-10-31", "2023-11-01", "2024-02-29"),
    ("2023-07-01", "2024-02-29", "2024-03-01", "2024-06-30"),
    ("2023-11-01", "2024-06-30", "2024-07-01", "2024-10-31"),
    ("2024-03-01", "2024-10-31", "2024-11-01", "2025-02-28"),
    ("2024-07-01", "2025-02-28", "2025-03-01", "2025-06-30"),
    ("2024-11-01", "2025-06-30", "2025-07-01", "2025-10-31"),
    ("2025-03-01", "2025-10-31", "2025-11-01", "2026-02-28"),
    ("2025-07-01", "2026-02-28", "2026-03-01", "2026-05-31"),
]

BTC_WINDOWS = [
    ("2023-08-01", "2024-03-31", "2024-04-01", "2024-07-31"),
    ("2023-12-01", "2024-07-31", "2024-08-01", "2024-11-30"),
    ("2024-04-01", "2024-11-30", "2024-12-01", "2025-03-31"),
    ("2024-08-01", "2025-03-31", "2025-04-01", "2025-07-31"),
    ("2024-12-01", "2025-07-31", "2025-08-01", "2025-11-30"),
    ("2025-04-01", "2025-11-30", "2025-12-01", "2026-03-31"),
    ("2025-08-01", "2026-03-31", "2026-04-01", "2026-05-31"),
]


def apply_strategy_config(strat):
    """Set config globals to match strategy parameters."""
    config.USE_NY_SESSION_FILTER_1H = True
    config.SIZING_MODE = "pct_risk"
    config.RISK_PCT_PER_TRADE = strat["risk"]
    config.SL_ATR_MULT = strat["sl_mult"]
    config.SIMPLE_RR = strat["rr"]
    config.PARTIAL_TP1_RR = strat["tp1_rr"]
    config.MAX_CONCURRENT_TRADES = strat["max_concurrent"]
    exit_mode = strat.get("exit_mode", "simple_rr")
    config.ENABLE_EXIT_SIMPLE_RR = (exit_mode == "simple_rr")
    config.ENABLE_EXIT_ATR5_RR = (exit_mode == "atr5_rr")
    config.ENABLE_EXIT_LEGACY = False
    config.ENABLE_PARTIAL_TP = True
    config.PARTIAL_TP_CLOSE_PCT = 0.50
    config.PARTIAL_MOVE_SL_TO_BE = True
    config.ONLY_HIGH_VOL_TRADES = True
    config.ENABLE_4H_EMA_TREND_FILTER = True


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


def fmt_pf(v):
    return "inf" if math.isinf(v) else f"{v:.2f}"


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------
COLORS = {
    "eth_state_fixed": "#00d4aa",
    "eth_raw_fixed": "#4da6ff",
    "eth_raw_comp": "#ff9f43",
    "btc_raw_fixed": "#ee5a24",
    "btc_atr5_comp": "#a55eea",
    "btc_atr5_fixed": "#e056b0",
}


def plot_walk_forward_bars(all_results, chart_path):
    """Bar chart: test-window ROI for each strategy across windows."""
    n = len(STRATEGIES)
    ncols = 3
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(20, 6 * nrows), facecolor="#0f1117")
    fig.suptitle("Walk-Forward Test-Window ROI (%)", color="#e0e0e0",
                 fontsize=16, fontweight="bold", y=0.97)

    flat_axes = axes.flat if hasattr(axes, 'flat') else [axes]
    for i, ax in enumerate(flat_axes):
        if i >= len(STRATEGIES):
            ax.set_visible(False)
            continue
        strat = STRATEGIES[i]
        sid = strat["id"]
        results = all_results[sid]
        ax.set_facecolor("#0f1117")

        test_labels = [r["test_label"] for r in results]
        test_rois = [r["test_roi"] for r in results]
        train_rois = [r["train_roi"] for r in results]

        x = np.arange(len(test_labels))
        width = 0.35
        color = COLORS.get(sid, "#ffffff")

        bars_train = ax.bar(x - width / 2, train_rois, width,
                            label="Train ROI", color=color, alpha=0.35,
                            edgecolor=color, linewidth=0.5)
        bars_test = ax.bar(x + width / 2, test_rois, width,
                           label="Test ROI", color=color, alpha=0.85,
                           edgecolor="white", linewidth=0.5)

        # Colour negative test bars red
        for bar, roi in zip(bars_test, test_rois):
            if roi < 0:
                bar.set_color("#ff4d6d")
                bar.set_edgecolor("#ff4d6d")

        ax.axhline(0, color="#555555", linewidth=0.6, linestyle="--")
        ax.set_xticks(x)
        ax.set_xticklabels(test_labels, rotation=35, ha="right",
                           color="#aaaaaa", fontsize=8)
        ax.set_ylabel("ROI %", color="#cccccc", fontsize=10)
        ax.set_title(strat["label"], color="#e0e0e0", fontsize=11, pad=8)
        ax.legend(fontsize=8, facecolor="#1a1a2e", edgecolor="#333",
                  labelcolor="#cccccc", loc="upper left")
        ax.tick_params(colors="#888888")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")
        ax.grid(axis="y", color="#222222", linewidth=0.5)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Bar chart saved -> {chart_path}")


def plot_cumulative_oos(all_results, chart_path):
    """
    Concatenated out-of-sample equity curve for each strategy.
    Shows what would happen if you traded each test window sequentially.
    """
    fig, ax = plt.subplots(figsize=(16, 8), facecolor="#0f1117")
    ax.set_facecolor("#0f1117")

    for strat in STRATEGIES:
        sid = strat["id"]
        results = all_results[sid]
        color = COLORS.get(sid, "#ffffff")

        # Chain OOS returns multiplicatively
        equity = [1.0]
        labels = ["Start"]
        for r in results:
            roi_frac = r["test_roi"] / 100.0
            equity.append(equity[-1] * (1.0 + roi_frac))
            labels.append(r["test_label"])

        ax.plot(range(len(equity)), equity, marker="o", color=color,
                linewidth=2.0, markersize=5, label=strat["label"], alpha=0.9)

    ax.axhline(1.0, color="#555555", linewidth=0.6, linestyle="--")
    ax.set_ylabel("Cumulative OOS Equity (1.0 = Start)", color="#cccccc", fontsize=12)
    ax.set_xlabel("Walk-Forward Window", color="#888888", fontsize=11)
    ax.set_title("Concatenated Out-of-Sample Equity Curves",
                 color="#e0e0e0", fontsize=14, pad=12)

    # Use the longest strategy's labels for x-axis
    longest = max(all_results.values(), key=len)
    x_labels = ["Start"] + [r["test_label"] for r in longest]
    ax.set_xticks(range(len(x_labels)))
    ax.set_xticklabels(x_labels, rotation=35, ha="right", color="#aaaaaa", fontsize=8)

    ax.legend(fontsize=9, facecolor="#1a1a2e", edgecolor="#333",
              labelcolor="#cccccc", loc="upper left")
    ax.tick_params(colors="#888888")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333333")
    ax.grid(axis="y", color="#222222", linewidth=0.5)

    plt.tight_layout()
    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  OOS equity chart saved -> {chart_path}")


def plot_sharpe_heatmap(all_results, chart_path):
    """Heatmap-style chart of test-window Sharpe ratios."""
    fig, ax = plt.subplots(figsize=(16, 5), facecolor="#0f1117")
    ax.set_facecolor("#0f1117")

    strat_labels = [s["label"] for s in STRATEGIES]
    max_windows = max(len(all_results[s["id"]]) for s in STRATEGIES)

    data = np.full((len(STRATEGIES), max_windows), np.nan)
    window_labels = []
    for si, strat in enumerate(STRATEGIES):
        results = all_results[strat["id"]]
        for wi, r in enumerate(results):
            data[si, wi] = r["test_sharpe"]
            if si == 0:
                window_labels.append(r["test_label"])

    # Pad window labels if needed
    while len(window_labels) < max_windows:
        longest = max(all_results.values(), key=len)
        for r in longest:
            if r["test_label"] not in window_labels:
                window_labels.append(r["test_label"])
        break

    im = ax.imshow(data, aspect="auto", cmap="RdYlGn", vmin=-2, vmax=4)
    ax.set_xticks(range(max_windows))
    ax.set_xticklabels(window_labels[:max_windows], rotation=35, ha="right",
                       color="#aaaaaa", fontsize=9)
    ax.set_yticks(range(len(STRATEGIES)))
    ax.set_yticklabels(strat_labels, color="#cccccc", fontsize=9)

    # Annotate cells
    for si in range(len(STRATEGIES)):
        for wi in range(max_windows):
            val = data[si, wi]
            if not np.isnan(val):
                text_color = "white" if abs(val) > 2 else "black"
                ax.text(wi, si, f"{val:.2f}", ha="center", va="center",
                        color=text_color, fontsize=9, fontweight="bold")

    ax.set_title("Test-Window Sharpe Ratios (Walk-Forward)",
                 color="#e0e0e0", fontsize=14, pad=12)
    cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.ax.tick_params(colors="#aaaaaa")
    cbar.set_label("Sharpe Ratio", color="#cccccc", fontsize=10)

    plt.tight_layout()
    plt.savefig(chart_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Sharpe heatmap saved -> {chart_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("\n" + "=" * 70)
    print("  WALK-FORWARD ANALYSIS v2 — 4-Month Test Windows")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # Pre-load and prepare data once per symbol
    print("\n  Loading ETHUSDT ...")
    df_eth_raw = load_symbol("ETHUSDT")
    df_eth = prepare(df_eth_raw, use_ny=True)
    print(f"  ETH prepared: {len(df_eth)} candles")

    print("  Loading BTCUSDT ...")
    df_btc_raw = load_symbol("BTCUSDT")
    df_btc = prepare(df_btc_raw, use_ny=True)
    print(f"  BTC prepared: {len(df_btc)} candles")

    prepared_data = {"ETHUSDT": df_eth, "BTCUSDT": df_btc}

    all_results = {}  # sid -> list of window results
    report_lines = [
        "# Walk-Forward Analysis v2 — 4-Month Test Windows\n\n",
        f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n",
        "**Training window:** 8 months (rolling)  \n",
        "**Test window:** 4 months (non-overlapping)  \n\n",
        "## Strategy Parameters\n\n",
        "| Strategy | Signal | Sizing | Risk | SL Mult | RR | TP1 | Max Slots |\n",
        "|----------|--------|--------|------|---------|----|----|----------|\n",
    ]
    for s in STRATEGIES:
        sizing = "Compounding" if s["compounding"] else "Fixed"
        report_lines.append(
            f"| {s['label']} | {s['signal']} | {sizing} | "
            f"{s['risk']*100:.0f}% | {s['sl_mult']}x | {s['rr']} | "
            f"{s['tp1_rr']} | {s['max_concurrent']} |\n"
        )
    report_lines.append("\n---\n\n")

    for strat in STRATEGIES:
        sid = strat["id"]
        symbol = strat["symbol"]
        label = strat["label"]
        windows = ETH_WINDOWS if symbol == "ETHUSDT" else BTC_WINDOWS
        df_full = prepared_data[symbol]

        apply_strategy_config(strat)

        print(f"\n{'~' * 60}")
        print(f"  Strategy: {label}")
        print(f"  Symbol: {symbol}  |  Windows: {len(windows)}")
        print(f"{'~' * 60}")

        results = []
        for wi, (train_s, train_e, test_s, test_e) in enumerate(windows, 1):
            df_train = df_full[
                (df_full["DateTime"] >= train_s) & (df_full["DateTime"] <= train_e)
            ].reset_index(drop=True)
            df_test = df_full[
                (df_full["DateTime"] >= test_s) & (df_full["DateTime"] <= test_e)
            ].reset_index(drop=True)

            if len(df_train) < 50 or len(df_test) < 20:
                print(f"    W{wi}: SKIP (train={len(df_train)}, test={len(df_test)} candles)")
                continue

            train_stats = run_bt(df_train, strat["signal"], strat["compounding"])
            test_stats = run_bt(df_test, strat["signal"], strat["compounding"])

            # Short label for test period
            test_label = f"{test_s[:7]} to {test_e[:7]}"

            row = {
                "window": wi,
                "train_period": f"{train_s} to {train_e}",
                "test_period": f"{test_s} to {test_e}",
                "test_label": test_label,
                "train_candles": len(df_train),
                "test_candles": len(df_test),
                "train_roi": train_stats["roi_pct"],
                "train_sharpe": train_stats["sharpe_ratio"],
                "train_trades": train_stats["trades"],
                "train_pf": train_stats["profit_factor"],
                "train_dd": train_stats["max_drawdown_pct"],
                "test_roi": test_stats["roi_pct"],
                "test_sharpe": test_stats["sharpe_ratio"],
                "test_trades": test_stats["trades"],
                "test_pf": test_stats["profit_factor"],
                "test_dd": test_stats["max_drawdown_pct"],
                "test_win_rate": test_stats["win_rate"],
                "test_expectancy": test_stats["expectancy_pnl"],
            }
            results.append(row)

            tick = "+" if test_stats["roi_pct"] > 0 else "-"
            print(
                f"    W{wi}: Train {train_s[:7]}..{train_e[:7]} "
                f"({train_stats['trades']}t, ROI={train_stats['roi_pct']:>7.1f}%)  |  "
                f"Test {test_s[:7]}..{test_e[:7]} "
                f"({test_stats['trades']}t, ROI={test_stats['roi_pct']:>7.1f}%, "
                f"Sharpe={test_stats['sharpe_ratio']:>5.2f}) [{tick}]"
            )

        all_results[sid] = results

        # Aggregate OOS stats
        oos_rois = [r["test_roi"] for r in results]
        oos_sharpes = [r["test_sharpe"] for r in results]
        oos_trades = sum(r["test_trades"] for r in results)
        win_windows = sum(1 for r in oos_rois if r > 0)
        total_windows = len(oos_rois)
        avg_oos_roi = np.mean(oos_rois) if oos_rois else 0
        avg_oos_sharpe = np.mean(oos_sharpes) if oos_sharpes else 0
        cumulative_oos = 1.0
        for r in oos_rois:
            cumulative_oos *= (1.0 + r / 100.0)
        cumulative_oos_pct = (cumulative_oos - 1.0) * 100.0

        print(f"\n  Summary: {win_windows}/{total_windows} profitable windows  "
              f"| Avg OOS ROI: {avg_oos_roi:.1f}%  "
              f"| Avg OOS Sharpe: {avg_oos_sharpe:.2f}  "
              f"| Cumulative OOS: {cumulative_oos_pct:.1f}%  "
              f"| Total OOS Trades: {oos_trades}")

        # Build markdown section
        report_lines += [
            f"## {label}\n\n",
            f"**{symbol}** | **{strat['signal']}** | "
            f"**{'Compounding' if strat['compounding'] else 'Fixed Capital'}**  \n",
            f"Risk: {strat['risk']*100:.0f}% | SL: {strat['sl_mult']}x ATR | "
            f"RR: {strat['rr']} | TP1: {strat['tp1_rr']}x | "
            f"Max Slots: {strat['max_concurrent']}  \n\n",
            "### Window Results\n\n",
            "| W# | Train Period | Test Period | Train Trades | Train ROI | "
            "Test Trades | Test ROI | Test Sharpe | Test PF | Test DD% | Test WR |\n",
            "|:---:|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n",
        ]
        for r in results:
            report_lines.append(
                f"| {r['window']} | {r['train_period']} | {r['test_period']} | "
                f"{r['train_trades']} | {r['train_roi']:.1f}% | "
                f"{r['test_trades']} | {r['test_roi']:.1f}% | "
                f"{r['test_sharpe']:.2f} | {fmt_pf(r['test_pf'])} | "
                f"{r['test_dd']:.1f}% | {r['test_win_rate']*100:.0f}% |\n"
            )

        report_lines += [
            f"\n### Aggregate Out-of-Sample\n\n",
            f"| Metric | Value |\n|--------|-------|\n",
            f"| Profitable Windows | {win_windows} / {total_windows} |\n",
            f"| Average OOS ROI | {avg_oos_roi:.1f}% |\n",
            f"| Average OOS Sharpe | {avg_oos_sharpe:.2f} |\n",
            f"| Cumulative OOS Return | {cumulative_oos_pct:.1f}% |\n",
            f"| Total OOS Trades | {oos_trades} |\n\n",
            "---\n\n",
        ]

    # Generate charts
    print(f"\n{'=' * 60}")
    print("  Generating charts ...")

    bar_path = os.path.join(OUT_DIR, f"wf_roi_bars_{TIMESTAMP}.png")
    plot_walk_forward_bars(all_results, bar_path)

    oos_path = os.path.join(OUT_DIR, f"wf_oos_equity_{TIMESTAMP}.png")
    plot_cumulative_oos(all_results, oos_path)

    sharpe_path = os.path.join(OUT_DIR, f"wf_sharpe_heatmap_{TIMESTAMP}.png")
    plot_sharpe_heatmap(all_results, sharpe_path)

    # Save report
    report_path = os.path.join(OUT_DIR, f"walk_forward_v2_{TIMESTAMP}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(report_lines)

    print(f"\n{'=' * 70}")
    print(f"  Report  -> {report_path}")
    print(f"  Charts  -> {OUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
