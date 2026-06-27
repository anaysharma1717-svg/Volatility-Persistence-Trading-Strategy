"""
generate_backtest_report.py
============================
Generates a comprehensive backtest results report with 8 charts:
  1. Equity curves  (top 6 strategies)
  2. Drawdown curves
  3. Monthly returns heatmap (best strategy)
  4. Trade PnL distribution (best strategy)
  5. Walk-forward OOS ROI bars
  6. Walk-forward Sharpe per window
  7. Strategy comparison bars (ROI / Sharpe / MaxDD)
  8. Exit reason pie charts

Run from project root:
    python scripts/generate_backtest_report.py
"""

import os, sys, datetime, warnings
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

# ── output ─────────────────────────────────────────────────────────────────
OUT_DIR = os.path.join(PROJECT_ROOT, "reports", "backtest_report")
os.makedirs(OUT_DIR, exist_ok=True)
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# ── colour theme ───────────────────────────────────────────────────────────
BG    = "#0f1117"
PANEL = "#161b22"
TEXT  = "#e0e0e0"
MUTED = "#888888"
GRID  = "#1e2435"
PAL   = ["#00d4aa", "#4da6ff", "#ff9f43", "#ee5a24", "#a55eea", "#e056b0"]

# ── strategy registry ──────────────────────────────────────────────────────
STRATEGIES = [
    # (id,                label,                              symbol,    signal,          exit_mode,   ny,    comp)
    ("eth_raw_atr5_comp",   "ETH | Raw | ATR5 RR | NY (Comp)",   "ETHUSDT", "raw_signal",   "atr5_rr",  True,  True),
    ("eth_raw_atr5_fix",    "ETH | Raw | ATR5 RR | NY (Fixed)",  "ETHUSDT", "raw_signal",   "atr5_rr",  True,  False),
    ("eth_state_atr5_comp", "ETH | State | ATR5 RR | NY (Comp)", "ETHUSDT", "state_signal", "atr5_rr",  True,  True),
    ("eth_raw_rr_comp",     "ETH | Raw | Simple RR | NY (Comp)", "ETHUSDT", "raw_signal",   "simple_rr",True,  True),
    ("btc_raw_atr5_comp",   "BTC | Raw | ATR5 RR | NY (Comp)",   "BTCUSDT", "raw_signal",   "atr5_rr",  True,  True),
    ("btc_raw_atr5_fix",    "BTC | Raw | ATR5 RR | NY (Fixed)",  "BTCUSDT", "raw_signal",   "atr5_rr",  True,  False),
]

# ── walk-forward windows (ETH – 4-month OOS) ───────────────────────────────
WF_WINDOWS = [
    ("2023-03-01", "2023-11-01", "2023-11-01", "2024-03-01"),
    ("2023-07-01", "2024-03-01", "2024-03-01", "2024-07-01"),
    ("2023-11-01", "2024-07-01", "2024-07-01", "2024-11-01"),
    ("2024-03-01", "2024-11-01", "2024-11-01", "2025-03-01"),
    ("2024-07-01", "2025-03-01", "2025-03-01", "2025-07-01"),
    ("2024-11-01", "2025-07-01", "2025-07-01", "2025-11-01"),
    ("2025-03-01", "2025-11-01", "2025-11-01", "2026-03-01"),
]

def _set_exit_mode(exit_mode: str):
    config.ENABLE_EXIT_SIMPLE_RR = (exit_mode == "simple_rr")
    config.ENABLE_EXIT_ATR5_RR   = (exit_mode == "atr5_rr")
    config.ENABLE_EXIT_LEGACY    = (exit_mode == "legacy")

def _reset_config():
    """Apply the standard config shared by all strategies."""
    config.SIZING_MODE           = "pct_risk"
    config.RISK_PCT_PER_TRADE    = 0.01
    config.SL_ATR_MULT           = 1.5
    config.SIMPLE_RR             = 3.0
    config.PARTIAL_TP1_RR        = 2.0
    config.MAX_CONCURRENT_TRADES = 3
    config.ENABLE_PARTIAL_TP     = True
    config.PARTIAL_TP_CLOSE_PCT  = 0.50
    config.PARTIAL_MOVE_SL_TO_BE = True
    config.ONLY_HIGH_VOL_TRADES  = True
    config.ENABLE_4H_EMA_TREND_FILTER = True

def _run(df, signal, comp):
    return run_multi_candle_backtest(
        df, signal,
        realistic_exit_timing=True,
        trailing_intrabar_trigger=True,
        use_compounding=comp,
        cost_multiplier=1.0,
        entry_delay=False,
        max_duration_candles=config.MAX_DURATION_CANDLES,
    )

def _ax(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=MUTED, labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    ax.grid(color=GRID, linewidth=0.5, alpha=0.6)
    if title:  ax.set_title(title,  color=TEXT,  fontsize=10, pad=8, fontweight="bold")
    if xlabel: ax.set_xlabel(xlabel, color=MUTED, fontsize=8)
    if ylabel: ax.set_ylabel(ylabel, color=MUTED, fontsize=9)

def _save(fig, name):
    path = os.path.join(OUT_DIR, f"{name}_{TS}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return path

# ── main ────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "=" * 65)
    print("  COMPREHENSIVE BACKTEST REPORT GENERATOR")
    print(f"  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 65)

    # ── load OHLCV data ────────────────────────────────────────────────────
    print("\n  Loading data...")
    df_eth_raw = load_symbol("ETHUSDT")
    df_btc_raw = load_symbol("BTCUSDT")
    # prepare both NY-on variants (all top strategies use NY filter ON)
    df_eth = prepare(df_eth_raw, use_ny=True)
    df_btc = prepare(df_btc_raw, use_ny=True)
    symbol_data = {"ETHUSDT": df_eth, "BTCUSDT": df_btc}
    print(f"  ETH: {len(df_eth):,} candles | BTC: {len(df_btc):,} candles")

    # ── run all 6 strategies ────────────────────────────────────────────────
    results = {}
    for sid, label, sym, signal, exit_mode, ny, comp in STRATEGIES:
        _reset_config()
        _set_exit_mode(exit_mode)
        st = _run(symbol_data[sym], signal, comp)
        results[sid] = st
        print(f"  {label:45}  ROI={st['roi_pct']:+7.1f}%  Sharpe={st['sharpe_ratio']:5.2f}  DD={st['max_drawdown_pct']:5.1f}%")

    # ── walk-forward OOS (top strategy: ETH raw ATR5 NY Comp) ──────────────
    top_id, top_label, top_sym, top_sig, top_exit, _, top_comp = STRATEGIES[0]
    print("\n  Running walk-forward OOS windows...")
    _reset_config()
    _set_exit_mode(top_exit)
    wf_rois, wf_sharpes, wf_labels = [], [], []
    for i, (_, _, oos_s, oos_e) in enumerate(WF_WINDOWS, 1):
        df_oos = symbol_data[top_sym]
        df_oos = df_oos[(df_oos["DateTime"] >= oos_s) & (df_oos["DateTime"] < oos_e)].reset_index(drop=True)
        if len(df_oos) < 20:
            continue
        st = _run(df_oos, top_sig, top_comp)
        wf_rois.append(st["roi_pct"])
        wf_sharpes.append(st["sharpe_ratio"])
        wf_labels.append(f"W{i}")
        print(f"  W{i}: OOS={oos_s}->{oos_e}  ROI={st['roi_pct']:+7.1f}%  Sharpe={st['sharpe_ratio']:5.2f}")

    cap = config.INITIAL_CAPITAL

    # ────────────────────────────────────────────────────────────────────────
    # Fig 1 – Equity curves (2×3 grid)
    # ────────────────────────────────────────────────────────────────────────
    fig1, axes1 = plt.subplots(2, 3, figsize=(20, 11), facecolor=BG)
    fig1.suptitle("Equity Curves — All Strategy Variants", color=TEXT, fontsize=14, fontweight="bold", y=0.98)
    for ax, (sid, label, *_), col in zip(axes1.flat, STRATEGIES, PAL):
        det = results[sid].get("details", pd.DataFrame())
        if det.empty:
            ax.set_visible(False)
            continue
        equity = cap + det["pnl"].cumsum()
        x = range(len(equity))
        ax.plot(x, equity / 1e6, color=col, linewidth=1.4)
        ax.fill_between(x, cap / 1e6, equity / 1e6, where=(equity >= cap), alpha=0.12, color=col)
        ax.fill_between(x, cap / 1e6, equity / 1e6, where=(equity < cap),  alpha=0.20, color="#ff4d6d")
        ax.axhline(cap / 1e6, color="#555", linewidth=0.7, linestyle="--")
        roi = results[sid]["roi_pct"]
        sharpe = results[sid]["sharpe_ratio"]
        _ax(ax, title=label, ylabel="Capital ($M)")
        ax.text(0.98, 0.04,
                f"ROI {roi:+.1f}%\nSharpe {sharpe:.2f}",
                transform=ax.transAxes, ha="right", va="bottom",
                color=col, fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=BG, alpha=0.85, edgecolor=col))
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    p1 = _save(fig1, "01_equity_curves")
    print("\n  [OK] Equity curves saved")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 2 – Drawdown curves (overlay)
    # ────────────────────────────────────────────────────────────────────────
    fig2, ax2 = plt.subplots(figsize=(18, 7), facecolor=BG)
    for (sid, label, *_), col in zip(STRATEGIES, PAL):
        det = results[sid].get("details", pd.DataFrame())
        if det.empty or "drawdown_pct" not in det.columns:
            continue
        ax2.fill_between(range(len(det)), 0, -det["drawdown_pct"], alpha=0.15, color=col)
        ax2.plot(range(len(det)), -det["drawdown_pct"], color=col, linewidth=1.0, label=label)
    ax2.axhline(0, color="#555", linewidth=0.5, linestyle="--")
    ax2.legend(fontsize=8, facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, ncol=2,
               loc="lower left", framealpha=0.9)
    _ax(ax2, title="Drawdown Curves — All Strategies", ylabel="Drawdown (%)")
    plt.tight_layout()
    p2 = _save(fig2, "02_drawdown_curves")
    print("  [OK] Drawdown curves saved")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 3 – Monthly returns heatmap (best strategy)
    # ────────────────────────────────────────────────────────────────────────
    p3 = None
    det_top = results[top_id].get("details", pd.DataFrame())
    if not det_top.empty and "exit_dt" in det_top.columns:
        try:
            det2 = det_top.copy()
            det2["exit_dt"] = pd.to_datetime(det2["exit_dt"], utc=True, errors="coerce")
            det2 = det2.dropna(subset=["exit_dt"])
            det2["month"] = det2["exit_dt"].dt.to_period("M")
            monthly_pnl  = det2.groupby("month")["pnl"].sum()
            monthly_pct  = (monthly_pnl / cap * 100).round(2)

            all_months = pd.period_range(monthly_pct.index.min(), monthly_pct.index.max(), freq="M")
            monthly_pct = monthly_pct.reindex(all_months, fill_value=0.0)

            years  = sorted(set(p.year for p in monthly_pct.index))
            hm = np.full((len(years), 12), np.nan)
            for period, val in monthly_pct.items():
                yi = years.index(period.year)
                hm[yi, period.month - 1] = val

            vmax = max(abs(np.nanmax(hm)), abs(np.nanmin(hm)), 0.1)
            fig3, ax3 = plt.subplots(figsize=(16, max(4, len(years) * 0.75 + 2)), facecolor=BG)
            im = ax3.imshow(hm, aspect="auto", cmap="RdYlGn", vmin=-vmax, vmax=vmax)
            MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            ax3.set_xticks(range(12)); ax3.set_xticklabels(MN, color=MUTED, fontsize=9)
            ax3.set_yticks(range(len(years))); ax3.set_yticklabels([str(y) for y in years], color=MUTED, fontsize=9)
            for yi in range(len(years)):
                for mi in range(12):
                    v = hm[yi, mi]
                    if not np.isnan(v):
                        fc = "white" if abs(v) > vmax * 0.5 else "black"
                        ax3.text(mi, yi, f"{v:+.1f}%", ha="center", va="center", fontsize=7, color=fc)
            cbar = fig3.colorbar(im, ax=ax3, shrink=0.8, pad=0.02)
            cbar.ax.tick_params(colors=MUTED)
            cbar.set_label("Monthly Return %", color=MUTED, fontsize=9)
            ax3.tick_params(colors=MUTED)
            for sp in ax3.spines.values(): sp.set_edgecolor(GRID)
            ax3.set_title(f"Monthly Returns Heatmap — {top_label}", color=TEXT, fontsize=10, pad=8, fontweight="bold")
            ax3.set_facecolor(PANEL)
            plt.tight_layout()
            p3 = _save(fig3, "03_monthly_heatmap")
            print("  [OK] Monthly heatmap saved")
        except Exception as e:
            print(f"  [SKIP] Monthly heatmap skipped: {e}")
    else:
        print("  [SKIP] Monthly heatmap skipped (no exit_dt column)")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 4 – Win / Loss PnL distribution
    # ────────────────────────────────────────────────────────────────────────
    fig4, axes4 = plt.subplots(1, 2, figsize=(16, 6), facecolor=BG)
    if not det_top.empty:
        wins_s  = det_top.loc[det_top["pnl"] > 0, "pnl"] / 1e3
        loses_s = det_top.loc[det_top["pnl"] < 0, "pnl"] / 1e3

        ax4a = axes4[0]
        bins_w = np.linspace(wins_s.min(), wins_s.max(), 35) if len(wins_s) > 1 else 20
        ax4a.hist(wins_s, bins=bins_w, color="#00d4aa", alpha=0.85, edgecolor=BG, linewidth=0.4)
        ax4a.axvline(wins_s.mean(), color="#ffd700", linewidth=1.8, linestyle="--",
                     label=f"Mean = ${wins_s.mean():.0f}K")
        ax4a.legend(fontsize=9, facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
        _ax(ax4a, title=f"Winning Trade PnL Distribution  (n={len(wins_s)})", xlabel="PnL ($K)", ylabel="Frequency")

        ax4b = axes4[1]
        bins_l = np.linspace(loses_s.min(), loses_s.max(), 25) if len(loses_s) > 1 else 20
        ax4b.hist(loses_s, bins=bins_l, color="#ff4d6d", alpha=0.85, edgecolor=BG, linewidth=0.4)
        ax4b.axvline(loses_s.mean(), color="#ffd700", linewidth=1.8, linestyle="--",
                     label=f"Mean = ${loses_s.mean():.0f}K")
        ax4b.legend(fontsize=9, facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
        _ax(ax4b, title=f"Losing Trade PnL Distribution  (n={len(loses_s)})", xlabel="PnL ($K)", ylabel="Frequency")

    fig4.suptitle(f"Trade PnL Distribution — {top_label}", color=TEXT, fontsize=12, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    p4 = _save(fig4, "04_pnl_distribution")
    print("  [OK] PnL distribution saved")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 5 – Walk-Forward OOS ROI bars
    # ────────────────────────────────────────────────────────────────────────
    fig5, ax5 = plt.subplots(figsize=(14, 6), facecolor=BG)
    c5 = ["#00d4aa" if r > 0 else "#ff4d6d" for r in wf_rois]
    bars5 = ax5.bar(wf_labels, wf_rois, color=c5, edgecolor=BG, linewidth=0.5, width=0.6)
    for bar, roi in zip(bars5, wf_rois):
        sign = 1 if roi >= 0 else -1
        ax5.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + sign * max(abs(r) for r in wf_rois) * 0.02,
                 f"{roi:+.1f}%", ha="center",
                 va="bottom" if roi >= 0 else "top",
                 fontsize=10, color=TEXT, fontweight="bold")
    ax5.axhline(0, color="#555", linewidth=0.8, linestyle="--")
    prof = sum(1 for r in wf_rois if r > 0)
    avg  = np.mean(wf_rois)
    ax5.text(0.98, 0.97,
             f"Profitable windows: {prof}/{len(wf_rois)}\nAvg OOS ROI: {avg:+.1f}%",
             transform=ax5.transAxes, ha="right", va="top", color=TEXT, fontsize=10,
             bbox=dict(boxstyle="round,pad=0.4", facecolor=PANEL, edgecolor="#00d4aa", alpha=0.9))
    _ax(ax5, title=f"Walk-Forward Out-of-Sample ROI — {top_label}", ylabel="OOS ROI %")
    plt.tight_layout()
    p5 = _save(fig5, "05_wf_roi_bars")
    print("  [OK] Walk-forward ROI bars saved")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 6 – Walk-Forward Sharpe per window
    # ────────────────────────────────────────────────────────────────────────
    fig6, ax6 = plt.subplots(figsize=(14, 5), facecolor=BG)
    c6 = ["#00d4aa" if s >= 0 else "#ff4d6d" for s in wf_sharpes]
    ax6.bar(wf_labels, wf_sharpes, color=c6, edgecolor=BG, linewidth=0.5, width=0.6)
    ax6.axhline(0,   color="#555",    linewidth=0.8, linestyle="--")
    ax6.axhline(1.0, color="#ffd700", linewidth=1.0, linestyle=":", label="Sharpe = 1.0 target")
    for i, (lbl, sh) in enumerate(zip(wf_labels, wf_sharpes)):
        ax6.text(i, sh + (0.04 if sh >= 0 else -0.06),
                 f"{sh:.2f}", ha="center", va="bottom" if sh >= 0 else "top",
                 fontsize=9, color=TEXT)
    ax6.legend(fontsize=9, facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    _ax(ax6, title="Walk-Forward Out-of-Sample Sharpe Ratio per Window", ylabel="Sharpe Ratio")
    plt.tight_layout()
    p6 = _save(fig6, "06_wf_sharpe")
    print("  [OK] Walk-forward Sharpe saved")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 7 – Strategy comparison bars (ROI / Sharpe / MaxDD)
    # ────────────────────────────────────────────────────────────────────────
    labels7 = [label for _, label, *_ in STRATEGIES]
    rois7    = [results[sid]["roi_pct"]          for sid, *_ in STRATEGIES]
    sharpes7 = [results[sid]["sharpe_ratio"]      for sid, *_ in STRATEGIES]
    dds7     = [results[sid]["max_drawdown_pct"]  for sid, *_ in STRATEGIES]

    fig7, axes7 = plt.subplots(1, 3, figsize=(22, 7), facecolor=BG)

    def _bar_panel(ax, vals, title, ylabel):
        ax.bar(range(len(vals)), vals, color=PAL, edgecolor=BG, linewidth=0.5)
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(
            [l.replace(" | ", "\n") for l in labels7],
            rotation=0, ha="center", color=MUTED, fontsize=7,
        )
        _ax(ax, title=title, ylabel=ylabel)
        for j, v in enumerate(vals):
            ax.text(j, v + max(vals) * 0.01, f"{v:.1f}", ha="center", va="bottom",
                    fontsize=8.5, color=TEXT)

    _bar_panel(axes7[0], rois7,    "ROI % by Strategy",          "ROI %")
    _bar_panel(axes7[1], sharpes7, "Sharpe Ratio by Strategy",   "Sharpe")
    _bar_panel(axes7[2], dds7,     "Max Drawdown % by Strategy", "Max DD %")

    fig7.suptitle("Strategy Comparison", color=TEXT, fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    p7 = _save(fig7, "07_strategy_comparison")
    print("  [OK] Strategy comparison saved")

    # ────────────────────────────────────────────────────────────────────────
    # Fig 8 – Exit reason breakdown (pie charts)
    # ────────────────────────────────────────────────────────────────────────
    fig8, axes8 = plt.subplots(2, 3, figsize=(20, 11), facecolor=BG)
    fig8.suptitle("Exit Reason Breakdown", color=TEXT, fontsize=13, fontweight="bold", y=0.98)
    pie_cols = ["#00d4aa", "#ff4d6d", "#ffd700", "#4da6ff", "#a55eea", "#e056b0"]
    for ax8, (sid, label, *_) in zip(axes8.flat, STRATEGIES):
        er = results[sid].get("exit_reason_counts", {})
        ax8.set_facecolor(PANEL)
        if not er:
            ax8.text(0.5, 0.5, "No data", color=MUTED, ha="center", va="center", transform=ax8.transAxes)
            ax8.set_title(label, color=TEXT, fontsize=8, pad=6, fontweight="bold")
            continue
        lbls  = list(er.keys())
        sizes = list(er.values())
        colors_pie = pie_cols[:len(lbls)]
        wedges, texts, autotexts = ax8.pie(
            sizes, labels=lbls, colors=colors_pie,
            autopct="%1.1f%%", startangle=90,
            wedgeprops=dict(edgecolor=BG, linewidth=1.5),
        )
        for t in texts:     t.set_color(MUTED); t.set_fontsize(8)
        for at in autotexts: at.set_color(TEXT);  at.set_fontsize(8)
        ax8.set_title(label, color=TEXT, fontsize=9, pad=6, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    p8 = _save(fig8, "08_exit_breakdown")
    print("  [OK] Exit breakdown saved")

    # ────────────────────────────────────────────────────────────────────────
    # Markdown report
    # ────────────────────────────────────────────────────────────────────────
    def _md_table(headers, rows_data):
        head = "| " + " | ".join(headers) + " |"
        sep  = "| " + " | ".join(["---"] * len(headers)) + " |"
        body = ["| " + " | ".join(str(c) for c in row) + " |" for row in rows_data]
        return "\n".join([head, sep] + body)

    summary_rows = []
    for sid, label, *_ in STRATEGIES:
        r = results[sid]
        summary_rows.append([
            label,
            r["trades"],
            f"{r['win_rate']*100:.1f}%",
            f"{r['roi_pct']:+.1f}%",
            f"{r['sharpe_ratio']:.2f}",
            f"{r['max_drawdown_pct']:.1f}%",
            f"{r['profit_factor']:.2f}",
            f"${r['expectancy_pnl']/1e3:,.1f}K",
            f"${r['avg_winner']/1e3:,.1f}K",
            f"${r['avg_loser']/1e3:,.1f}K",
            f"{r['return_drawdown_ratio']:.2f}",
        ])

    wf_rows = []
    for i, (lbl, roi, sh) in enumerate(zip(wf_labels, wf_rois, wf_sharpes), 1):
        _, _, oos_s, oos_e = WF_WINDOWS[i - 1]
        result_str = "✅ Profitable" if roi > 0 else "❌ Loss"
        wf_rows.append([lbl, oos_s, oos_e, f"{roi:+.1f}%", f"{sh:.2f}", result_str])

    charts = [
        ("Equity Curves", p1),
        ("Drawdown Curves", p2),
        ("Monthly Returns Heatmap", p3),
        ("Trade PnL Distribution", p4),
        ("Walk-Forward OOS ROI", p5),
        ("Walk-Forward Sharpe", p6),
        ("Strategy Comparison", p7),
        ("Exit Reason Breakdown", p8),
    ]

    top_r = results[top_id]
    md_lines = [
        "# Backtest Results Report\n\n",
        f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n",
        "**Universe:** BTCUSDT, ETHUSDT — 1-hour candles  \n",
        "**Period:** Full available history  \n",
        "**Starting Capital:** $1,000,000  \n\n",
        "---\n\n",
        "## Configuration\n\n",
        "| Parameter | Value |\n|---|---|\n",
        "| Risk per Trade | 1% of equity |\n",
        "| SL Distance | 1.5× ATR(14) |\n",
        "| Partial TP1 | 2.0× risk → close 50%, move SL to breakeven |\n",
        "| Full TP2 | 3.0× risk |\n",
        "| Session Filter | New York (09:00–17:00 ET) |\n",
        "| Volatility Filter | High-vol regime only |\n",
        "| Trend Filter | 4H EMA-200 direction |\n",
        "| Max Concurrent | 3 open positions |\n",
        "| Fees | 0.02% per side |\n",
        "| Slippage | 0.5–5.0 bps (regime-dependent) |\n\n",
        "---\n\n",
        "## Strategy Performance Summary\n\n",
        _md_table(
            ["Strategy", "Trades", "Win%", "ROI%", "Sharpe", "Max DD%", "PF",
             "Expectancy", "Avg Win", "Avg Loss", "R/DD"],
            summary_rows,
        ),
        "\n\n---\n\n",
        "## Top Strategy Highlight\n\n",
        f"> **{top_label}** — Composite Score: #1 out of 48 variants\n\n",
        "| Metric | Value |\n|---|---|\n",
        f"| ROI | {top_r['roi_pct']:+.1f}% |\n",
        f"| Sharpe Ratio | {top_r['sharpe_ratio']:.3f} |\n",
        f"| Profit Factor | {top_r['profit_factor']:.2f} |\n",
        f"| Max Drawdown | {top_r['max_drawdown_pct']:.1f}% |\n",
        f"| Return/DD Ratio | {top_r['return_drawdown_ratio']:.2f} |\n",
        f"| Expectancy per Trade | ${top_r['expectancy_pnl']:,.0f} |\n",
        f"| Total Trades | {top_r['trades']} |\n",
        f"| Win Rate | {top_r['win_rate']*100:.1f}% |\n",
        f"| Avg Winner | ${top_r['avg_winner']:,.0f} |\n",
        f"| Avg Loser | ${top_r['avg_loser']:,.0f} |\n\n",
        "---\n\n",
        "## Walk-Forward Out-of-Sample Results\n\n",
        f"> Strategy: **{top_label}** | 4-month OOS windows\n\n",
        _md_table(
            ["Window", "OOS Start", "OOS End", "OOS ROI%", "OOS Sharpe", "Result"],
            wf_rows,
        ),
        f"\n\n**Profitable windows:** {sum(1 for r in wf_rois if r>0)} / {len(wf_rois)}  \n",
        f"**Average OOS ROI:** {np.mean(wf_rois):+.1f}%  \n",
        f"**Average OOS Sharpe:** {np.mean(wf_sharpes):.2f}  \n\n",
        "---\n\n",
        "## Charts\n\n",
    ]
    for title, path in charts:
        if path:
            md_lines.append(f"### {title}\n\n")
            md_lines.append(f"![{title}]({os.path.basename(path)})\n\n")

    rpt_path = os.path.join(OUT_DIR, f"backtest_report_{TS}.md")
    with open(rpt_path, "w", encoding="utf-8") as f:
        f.writelines(md_lines)

    print(f"\n{'='*65}")
    print(f"  Report : {rpt_path}")
    print(f"  Charts : {OUT_DIR}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
