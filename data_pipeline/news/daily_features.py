"""Daily text features for the ML team (docs/03 §5: data/processed/text_daily_features.parquet).

One row per Baltic trading day. For each of three scorings of the headlines:
    fb  = plain FinBERT baseline (headline + lead), positive/negative tone
    ft  = fine-tuned FinBERT (headline + lead), Capesize bullish/bearish, "not relevant" dropped
    llm = Qwen2.5-7B labels, Capesize bullish/bearish, "not relevant" dropped
it builds: sent_<s> (mean score, -1 bearish ... +1 bullish), share_bull_<s>, share_bear_<s>, n_rel_<s>,
per-topic means sent_<s>_freight / _hormuz / _ironcoal, smoothed sent_<s>_ewm5 / _ewm20 and the
5-day change sent_<s>_chg5. Volume: n_headlines and n_headlines_rel20 (count / its 20-day average),
because raw counts rise with the crisis. Every smoothing looks backwards only (no future information).
Days without headlines get count 0 and neutral sentiment 0.

Usage (from the repository root):
    python -m data_pipeline.news.daily_features --trading-days data/raw/baltic_5tc_trading_days.csv
The fine-tuned/LLM file is optional: without it, only the fb features are built.
"""
import argparse
from pathlib import Path

import pandas as pd

from . import config
from .trading_days import load_trading_days

TOPICS = ("freight", "hormuz", "ironcoal")
SCORINGS = {  # name: (score column, label column, bullish label, bearish label, label to drop)
    "fb": ("fb_lead_sent", "fb_lead_label", "positive", "negative", None),
    "ft": ("ft_headlead_score", "ft_headlead_label", "bullish", "bearish", "not relevant"),
    "llm": ("llm_score", "llm_label", "bullish", "bearish", "not relevant"),
}


def scoring_features(df: pd.DataFrame, name: str, grid: pd.DatetimeIndex) -> pd.DataFrame:
    score, label, bull, bear, drop = SCORINGS[name]
    d = df if drop is None else df[df[label] != drop]
    g = d.groupby("news_day")
    out = pd.DataFrame(index=grid)
    out[f"sent_{name}"] = g[score].mean()
    out[f"share_bull_{name}"] = g[label].apply(lambda s: (s == bull).mean())
    out[f"share_bear_{name}"] = g[label].apply(lambda s: (s == bear).mean())
    out[f"n_rel_{name}"] = g.size()
    for t in TOPICS:
        out[f"sent_{name}_{t}"] = d[d[f"topic_{t}"] == 1].groupby("news_day")[score].mean()
    out = out.fillna(0.0)  # no headline that day: count 0, neutral sentiment
    out[f"n_rel_{name}"] = out[f"n_rel_{name}"].astype(int)
    s = out[f"sent_{name}"]
    out[f"sent_{name}_ewm5"] = s.ewm(span=5, adjust=False).mean()
    out[f"sent_{name}_ewm20"] = s.ewm(span=20, adjust=False).mean()
    out[f"sent_{name}_chg5"] = out[f"sent_{name}_ewm5"] - out[f"sent_{name}_ewm5"].shift(5)
    return out


def build_features(headlines: pd.DataFrame, scores: list[pd.DataFrame], grid: pd.DatetimeIndex) -> pd.DataFrame:
    df = headlines[["id", "news_day", *[f"topic_{t}" for t in TOPICS]]].copy()
    df["news_day"] = pd.to_datetime(df["news_day"]).dt.normalize()
    for s in scores:
        df = df.merge(s.drop(columns=[c for c in ("news_day", "source", "has_lead") if c in s]), on="id", how="left")
    grid = grid[(grid >= df["news_day"].min()) & (grid <= df["news_day"].max())]

    out = pd.DataFrame(index=grid)
    out["n_headlines"] = df.groupby("news_day").size().reindex(grid, fill_value=0)
    out["n_headlines_rel20"] = out["n_headlines"] / out["n_headlines"].rolling(20, min_periods=5).mean()
    for t in TOPICS:
        out[f"n_{t}"] = df[df[f"topic_{t}"] == 1].groupby("news_day").size().reindex(grid, fill_value=0)
    for name, (score, *_rest) in SCORINGS.items():
        if score in df:
            out = out.join(scoring_features(df, name, grid))
    return out.rename_axis("date").reset_index()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trading-days", type=Path, help="CSV whose first column holds the 5TC dates")
    args = parser.parse_args()

    headlines = pd.read_parquet(config.TEXT_DIR / "headlines_clean.parquet")
    scores = [pd.read_parquet(config.PROCESSED_DIR / "headlines_finbert_baseline.parquet")]
    ft_path = config.PROCESSED_DIR / "headlines_finetuned_scores.parquet"
    if ft_path.exists():
        scores.append(pd.read_parquet(ft_path))
    else:
        print(f"Note: {ft_path.name} not found, building the plain FinBERT (fb) features only.")

    days = pd.to_datetime(headlines["news_day"])
    grid = load_trading_days(days.min().date(), days.max().date(), args.trading_days)
    feats = build_features(headlines, scores, grid)

    path = config.PROCESSED_DIR / "text_daily_features.parquet"
    feats.to_parquet(path, index=False)
    post = feats["date"] >= pd.Timestamp("2026-02-28")
    print(f"Saved {len(feats)} trading days x {feats.shape[1]} columns to {path}")
    print(f"Dates {feats['date'].min().date()} -> {feats['date'].max().date()}, days with no headline: "
          f"{int((feats['n_headlines'] == 0).sum())}")
    main_cols = [c for c in ("sent_fb", "sent_ft", "sent_llm") if c in feats]
    print("Mean sentiment before / after the closure:")
    print(pd.DataFrame({"before": feats.loc[~post, main_cols].mean(), "after": feats.loc[post, main_cols].mean()}).round(3))


if __name__ == "__main__":
    main()
