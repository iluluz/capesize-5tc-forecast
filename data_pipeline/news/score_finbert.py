"""FinBERT baseline scores for the clean headlines (docs/03 M2, plain FinBERT, no fine-tuning).

Reads  <CAPESIZE_LOCAL_DIR>/text/headlines_clean.parquet
Writes <CAPESIZE_LOCAL_DIR>/processed/headlines_finbert_baseline.parquet with one row per headline:
    id, news_day, source, has_lead,
    fb_title_positive, fb_title_negative, fb_title_neutral, fb_title_sent, fb_title_label,
    fb_lead_positive,  fb_lead_negative,  fb_lead_neutral,  fb_lead_sent,  fb_lead_label
"title" = headline only; "lead" = headline + first paragraph (headline only when there is no lead).
sent = P(positive) - P(negative), from -1 to +1. Uses the Apple GPU (MPS) or CUDA when available.

Usage (from the repository root, after `pip install -r requirements-dl.txt`):
    python -m data_pipeline.news.score_finbert --limit 200   # quick test
    python -m data_pipeline.news.score_finbert               # all headlines
"""
import argparse
import time

import pandas as pd

from . import config

MODEL = "ProsusAI/finbert"
LABELS = ("positive", "negative", "neutral")


def pick_device():
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return 0
    return -1  # CPU


def to_frame(results: list, prefix: str) -> pd.DataFrame:
    """Turn pipeline output (one list of {label, score} per text) into probability columns."""
    rows = [{d["label"].lower(): d["score"] for d in res} for res in results]
    df = pd.DataFrame(rows).reindex(columns=list(LABELS)).fillna(0.0)
    out = df.add_prefix(f"{prefix}_")
    out[f"{prefix}_sent"] = df["positive"] - df["negative"]
    out[f"{prefix}_label"] = df.idxmax(axis=1)
    return out


def score_texts(pipe, texts: list[str], prefix: str, batch_size: int, chunk: int = 512) -> pd.DataFrame:
    results, t0 = [], time.time()
    for i in range(0, len(texts), chunk):
        results += pipe(texts[i:i + chunk], batch_size=batch_size)
        done = min(i + chunk, len(texts))
        rate = done / max(time.time() - t0, 1e-6)
        print(f"  {prefix}: {done}/{len(texts)} scored, about {(len(texts) - done) / rate / 60:.1f} min left", flush=True)
    return to_frame(results, prefix)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="score only the first N headlines (test run)")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    from transformers import pipeline

    df = pd.read_parquet(config.TEXT_DIR / "headlines_clean.parquet")
    if args.limit:
        df = df.head(args.limit)
    has_lead = df["lead"].notna() & df["lead"].astype(str).str.strip().ne("")
    titles = df["title"].astype(str).tolist()
    with_lead = (df["title"].astype(str) + ". " + df["lead"].fillna("").astype(str)).where(has_lead, df["title"]).tolist()

    device = pick_device()
    print(f"Loading {MODEL} on {device} (first run downloads about 440 MB)...", flush=True)
    pipe = pipeline("text-classification", model=MODEL, top_k=None, truncation=True, max_length=512, device=device)

    out = pd.concat([
        df[["id", "news_day", "source"]].reset_index(drop=True).assign(has_lead=has_lead.to_numpy()),
        score_texts(pipe, titles, "fb_title", args.batch_size),
        score_texts(pipe, with_lead, "fb_lead", args.batch_size),
    ], axis=1)

    path = config.PROCESSED_DIR / "headlines_finbert_baseline.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)

    post = pd.to_datetime(out["news_day"]) >= pd.Timestamp("2026-02-28")
    print(f"\nSaved {len(out)} rows to {path}")
    print("Label shares (headline only):", out["fb_title_label"].value_counts(normalize=True).round(2).to_dict())
    print(f"Mean sentiment, headline only: before closure {out.loc[~post, 'fb_title_sent'].mean():+.3f}, "
          f"after {out.loc[post, 'fb_title_sent'].mean():+.3f}")


if __name__ == "__main__":
    main()
