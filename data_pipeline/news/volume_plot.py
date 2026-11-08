"""Volume plot for the text branch (docs/03 §6, week 1-2): relevant headlines per trading day by source,
with the Hormuz closure marked. Uses only counts, never article text, so the figure is safe to share.

Usage (from the repository root, after the merge):
    python -m data_pipeline.news.volume_plot
"""
import matplotlib

matplotlib.use("Agg")  # write the file without opening a window
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

HORMUZ_CLOSURE = pd.Timestamp("2026-02-28")


def main():
    df = pd.read_parquet(config.TEXT_DIR / "headlines_clean.parquet")
    daily = df.groupby(["news_day", "source"]).size().unstack(fill_value=0).sort_index()
    smooth = daily.rolling(5, min_periods=1).mean()  # 5-day average: one trading week

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.stackplot(smooth.index, smooth.T.values, labels=smooth.columns, alpha=0.85)
    ax.axvline(HORMUZ_CLOSURE, color="black", linestyle="--", linewidth=1)
    ax.text(HORMUZ_CLOSURE, ax.get_ylim()[1] * 0.95, "  Hormuz closure (28 Feb 2026)", va="top", fontsize=9)
    ax.set_title("Relevant headlines per trading day (5-day average), by source")
    ax.set_ylabel("Headlines per day")
    ax.legend(loc="upper left", frameon=False)
    ax.margins(x=0)
    fig.tight_layout()

    out = config.LOCAL_DIR / "figures" / "news_volume.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)

    monthly = daily.groupby(daily.index.to_period("M")).sum()
    monthly["total"] = monthly.sum(axis=1)
    print(monthly.to_string())
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
