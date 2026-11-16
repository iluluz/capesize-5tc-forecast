"""Hormuz case-study chart: Capesize news sentiment around the Strait of Hormuz closure (28 Feb 2026).

Run from the text_signal folder (conda env 'aiedge'):
    python plot_hormuz.py                          # news panels only
    python plot_hormuz.py --tc data/raw/<5TC workbook>.xlsx   # adds a 5TC panel (column auto-detected)
Options: --tc-sheet NAME  --tc-col NAME  (if auto-detection picks the wrong sheet/column)

Input : data/processed/text_daily_features.parquet (from Ninon: date, sent_*_ewm20, sent_ft/llm/fb, n_headlines)
Output: figures/hormuz_case_study.png (main, 20-day averages; with --tc: *_5tc_PRIVATE.png, licensed), figures/hormuz_closeup.png (Jan–Apr 2026, 5-day averages),
        figures/hormuz_before_after.csv (numbers for the slide). All 300 dpi, slide-ready.
Separate panels share the date axis (no dual y-axis). The 5TC panel is an internal chart: licensed data, keep it out of GitHub.
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
FEATURES = HERE / "data" / "processed" / "text_daily_features.parquet"
FIG = HERE / "figures"
T0 = pd.Timestamp("2026-02-28")          # Hormuz closure
TRAIN_END = pd.Timestamp("2026-03-28")   # fine-tuned FinBERT trained only on headlines before this day

# Reference palette, categorical slots 1-3 (validated all-pairs), light surface
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
SERIES = [  # (column stem, label, colour, line style)
    ("sent_ft", "Fine-tuned FinBERT (Capesize labels)", "#2a78d6", "-"),
    ("sent_llm", "LLM labels (Qwen2.5-7B)", "#eb6834", "-"),
    ("sent_fb", "Plain FinBERT (general tone)", "#1baf7a", "--"),
]


def load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def load_5tc(path: Path, sheet=None, col=None) -> pd.Series:
    """Find a date column and a 5TC column in the workbook (first match), unless given explicitly."""
    sheets = pd.read_excel(path, sheet_name=sheet if sheet else None)
    sheets = {sheet: sheets} if sheet else sheets
    for name, s in sheets.items():
        cols = [c for c in s.columns if (col and str(c) == col) or (not col and "5tc" in str(c).lower())]
        dcol = next((c for c in s.columns if pd.api.types.is_datetime64_any_dtype(s[c]) or "date" in str(c).lower()), None)
        if cols and dcol is not None:
            out = pd.Series(pd.to_numeric(s[cols[0]], errors="coerce").to_numpy(),
                            index=pd.to_datetime(s[dcol], errors="coerce")).dropna()
            print(f"5TC: sheet '{name}', date column '{dcol}', value column '{cols[0]}' ({len(out)} rows)")
            return out.sort_index()
    raise SystemExit("No 5TC column found: pass --tc-sheet and --tc-col (print the sheet names/columns first).")


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.axvline(T0, color=INK2, linewidth=1, linestyle=":")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--features", type=Path, default=FEATURES)
    p.add_argument("--tc", type=Path, help="5TC workbook (optional)")
    p.add_argument("--tc-sheet"); p.add_argument("--tc-col")
    p.add_argument("--start", default="2025-09-01")
    p.add_argument("--zoom-start", default="2026-01-05")
    p.add_argument("--zoom-end", default="2026-04-30")
    a = p.parse_args()

    full = load(a.features)
    vol_full = full.set_index("date")["n_headlines"].rolling(20, min_periods=1).mean()   # before cutting the window: no start-up spike
    df = full[full["date"] >= a.start]
    tc = load_5tc(a.tc, a.tc_sheet, a.tc_col) if a.tc else None

    # before/after numbers for the slide (daily means, not smoothed)
    after = df["date"] >= T0
    oos = df["date"] >= TRAIN_END   # after the fine-tuned model's training cut-off: fully out-of-sample
    rows = [{"model": lab, "before closure": df.loc[~after, s].mean(), "after closure": df.loc[after, s].mean(),
             "after 28 Mar (out-of-sample)": df.loc[oos, s].mean()} for s, lab, _, _ in SERIES]
    rows.append({"model": "Headlines per day", "before closure": df.loc[~after, "n_headlines"].mean(),
                 "after closure": df.loc[after, "n_headlines"].mean(),
                 "after 28 Mar (out-of-sample)": df.loc[oos, "n_headlines"].mean()})
    table = pd.DataFrame(rows).round(3)
    FIG.mkdir(exist_ok=True)
    table.to_csv(FIG / "hormuz_before_after.csv", index=False)
    print(table.to_string(index=False))

    # main chart: whole window, 20-day averages
    tag = "_5tc_PRIVATE" if tc is not None else ""   # licensed 5TC data -> separate file name, never to GitHub
    draw(df, vol_full, tc, smooth="20", out=FIG / f"hormuz_case_study{tag}.png",
         title="After the Hormuz closure, Capesize-specific news turns bullish while general tone turns negative",
         subtitle="Daily news sentiment from 9,512 shipping and commodity headlines, Sep 2025 – Oct 2026",
         locator=mdates.MonthLocator(interval=2), fmt="%b %Y")
    # close-up: weeks around the closure, 5-day averages (reacts faster, noisier)
    vol5_full = full.set_index("date")["n_headlines"].rolling(5, min_periods=1).mean()
    near = full[(full["date"] >= a.zoom_start) & (full["date"] <= a.zoom_end)]
    draw(near, vol5_full, tc, smooth="5", out=FIG / f"hormuz_closeup{tag}.png",
         title="Close-up: news sentiment in the weeks around the Hormuz closure",
         subtitle=f"5-day averages, {pd.Timestamp(a.zoom_start):%d %b} – {pd.Timestamp(a.zoom_end):%d %b %Y}",
         locator=mdates.WeekdayLocator(byweekday=mdates.MO, interval=2), fmt="%d %b")


def draw(df, vol_full, tc, smooth, out, title, subtitle, locator, fmt):
    n = 3 if tc is not None else 2
    ratios = [3, 2, 1.2] if tc is not None else [3, 1.2]
    plt.rcParams["font.family"] = ["Inter", "DejaVu Sans"]
    fig, axes = plt.subplots(n, 1, figsize=(11, 7.5 if tc is not None else 6), sharex=True,
                             gridspec_kw={"height_ratios": ratios, "hspace": 0.18}, facecolor=SURFACE)

    # 1. sentiment, smoothed (backward-looking averages from Ninon's file)
    ax = axes[0]; style(ax)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ends = []
    for s, lab, colour, ls in SERIES:
        y = df[f"{s}_ewm{smooth}"]
        ax.plot(df["date"], y, color=colour, linewidth=2, linestyle=ls, label=lab)
        ends.append([y.iloc[-1], lab.split(" (")[0]])
    # direct labels at the line ends, nudged apart so they never overlap
    span = ax.get_ylim()[1] - ax.get_ylim()[0]; gap = 0.07 * span
    ends.sort(key=lambda e: e[0])
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + gap)
    for y_end, text in ends:
        ax.annotate(text, (df["date"].iloc[-1], y_end), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=INK, annotation_clip=False)
    ax.set_ylabel(f"Sentiment for Capesize rates\n(−1 bearish … +1 bullish, {smooth}-day avg)", color=INK2, fontsize=9)
    ax.text(T0, 1.0, "  Hormuz closure 28 Feb", transform=ax.get_xaxis_transform(), color=INK2, fontsize=9, va="top")
    shade_end = min(TRAIN_END, df["date"].max())
    if df["date"].min() < shade_end:
        ax.axvspan(df["date"].min(), shade_end, color=GRID, alpha=0.25, linewidth=0)
        ax.text(df["date"].min(), 0.02, "  fine-tuned model's training period", transform=ax.get_xaxis_transform(),
                color=INK2, fontsize=8)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK)

    # 2. 5TC (optional, own panel: no dual axis)
    k = 1
    if tc is not None:
        ax = axes[k]; style(ax); k += 1
        t = tc[(tc.index >= df["date"].min()) & (tc.index <= df["date"].max())]
        ax.plot(t.index, t.values / 1000, color=INK, linewidth=2)
        ax.set_ylabel("Capesize 5TC\n($ thousand/day)", color=INK2, fontsize=9)

    # 3. news volume (average computed on the full data before cutting: no start-up spike)
    ax = axes[k]; style(ax)
    vol = vol_full[(vol_full.index >= df["date"].min()) & (vol_full.index <= df["date"].max())]
    ax.fill_between(vol.index, vol.values, color="#2a78d6", alpha=0.25, linewidth=0)
    ax.plot(vol.index, vol.values, color="#2a78d6", linewidth=1.5)
    ax.set_ylabel(f"Headlines/day\n({smooth}-day avg)", color=INK2, fontsize=9)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))

    fig.suptitle(title, x=0.06, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.06, 0.915, subtitle, fontsize=10, color=INK2)
    fig.subplots_adjust(left=0.1, right=0.86, top=0.87, bottom=0.07)
    fig.savefig(out, dpi=300, facecolor=SURFACE)
    plt.close(fig)
    print("saved", out)


if __name__ == "__main__":
    main()
