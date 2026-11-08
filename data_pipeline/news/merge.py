"""Merge every news source into the text-branch files (docs/03 §2).

1. Convert each source to the headlines schema and save data/text/headlines.parquet (everything collected).
2. Clean: assign each item to its news window W_t with capesize.calendar (12:00 UTC cutoff, date-only
   items at 23:59:59 UTC), keep relevant items, drop duplicates (same URL; Reuters "UPDATE" versions;
   near-identical titles on the same day; optionally embedding near-duplicates, cosine > 0.92).
3. Volume check: headlines per trading day, flag days with fewer than 5 items.
4. Save data/text/headlines_clean.parquet.

Usage (from the repository root), every input optional:
    python -m data_pipeline.news.merge --factiva path/to/factiva_articles_clean.csv \
        --gdelt path/to/gdelt.csv --scraped hellenic gcaptain [--trading-days 5tc_dates.csv] [--embed-dedup]
"""
import argparse
import json
import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from capesize.calendar import assign_news_day, to_utc

from . import config
from .filters import is_relevant
from .schema import HEADLINE_COLUMNS, canonical_url, make_id
from .trading_days import load_trading_days

TOPICS = {
    "topic_freight": r"capesize|dry bulk|drybulk|bulk carrier|bulker|baltic|freight|charter|tonnage|bdi|bci|5tc",
    "topic_hormuz": r"hormuz|iran|persian gulf|red sea|suez|rerout|tanker|war risk",
    "topic_ironcoal": r"iron ore|coal|steel|vale|bhp|rio tinto|fortescue|simandou|bauxite",
}
_TOPIC_RE = {k: re.compile(rf"(?<!\w)(?:{v})", re.IGNORECASE) for k, v in TOPICS.items()}

_PREFIX_RE = re.compile(r"^(?:(?:UPDATE \d+|REFILE|RPT|CORRECTED|CORRECTION|BUZZ|WRAPUP \d*|FOCUS|ANALYSIS|"
                        r"EXCLUSIVE|INSIGHT|EXPLAINER|FACTBOX|GRAPHIC|BREAKINGVIEWS)\s*-\s*)+", re.I)
_DATELINE_RE = re.compile(r"^.{0,60}?\(Reuters\)\s*-\s*")


def clean_reuters_lead(lead) -> str | None:
    """Drop the dateline; None when the lead is only an editorial note or too short to be useful."""
    if not isinstance(lead, str):
        return None
    lead = lead.strip()
    if lead.startswith("("):  # e.g. "(Updates prices on market close)"
        return None
    lead = _DATELINE_RE.sub("", lead).strip()
    return lead if len(lead) >= 40 else None


# --- Loaders: each returns the headlines schema ------------------------------------------------------
def load_factiva(path: Path) -> pd.DataFrame:
    """Reuters via Factiva (headline + first paragraph, exact timestamps, no public URL)."""
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["published_utc"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return pd.DataFrame({
        "id": df["id"].astype(str).map(lambda i: make_id("reuters_factiva", i)),
        "published_utc": ts,
        "first_seen_utc": ts,
        "source": "reuters_factiva",
        "outlet": df["source"],
        "url": None,
        "title": df["title"].astype(str).str.strip(),
        "lead": df["lead"].map(clean_reuters_lead),
        "lang": "en",
        "query": "factiva",
        "retrieved_utc": None,
        "date_only": df["time_missing"].astype(bool),
    })


def load_scraped(source: str) -> pd.DataFrame:
    """Rows written by scrape_wordpress (already in the headlines schema)."""
    files = sorted((config.RAW_DIR / source).glob("*.jsonl"))
    rows = [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise FileNotFoundError(f"No scraped files in {config.RAW_DIR / source}")
    return pd.DataFrame(rows)[HEADLINE_COLUMNS]


# Change these to the column names of the GDELT export if they differ
GDELT_COLUMNS = {"url": "url", "title": "title", "seendate": "seendate", "domain": "domain",
                 "language": "language", "query": "query"}


def load_gdelt(path: Path) -> pd.DataFrame:
    """GDELT DOC API export: titles and URLs, no lead. Its time is when GDELT first saw the article
    (first_seen_utc, the time decisions.md C4 asks for)."""
    df = pd.read_csv(path)
    c = GDELT_COLUMNS
    ts = pd.to_datetime(df[c["seendate"]], utc=True, format="mixed").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    urls = df[c["url"]].astype(str).map(canonical_url)
    lang = df[c["language"]].astype(str).str.lower().replace({"english": "en"}) if c["language"] in df else "en"
    return pd.DataFrame({
        "id": urls.map(lambda u: make_id("gdelt", u)),
        "published_utc": ts,
        "first_seen_utc": ts,
        "source": "gdelt",
        "outlet": df[c["domain"]] if c["domain"] in df else None,
        "url": urls,
        "title": df[c["title"]].astype(str).str.strip(),
        "lead": None,
        "lang": lang,
        "query": df[c["query"]] if c["query"] in df else "gdelt",
        "retrieved_utc": None,
        "date_only": False,
    })


# --- Deduplication -------------------------------------------------------------------------------------
def normalize_title(title: str) -> str:
    title = _PREFIX_RE.sub("", title or "")
    return " ".join(re.sub(r"[^\w\s]", " ", title.lower()).split())


def dedupe(df: pd.DataFrame, window_days: int = 3, fuzzy_threshold: float = 0.95) -> tuple[pd.DataFrame, dict]:
    """Keep the earliest copy of each story. Identical normalized titles are the same story only within
    `window_days` (recurring daily titles months apart are kept); near-identical titles on the same
    news day are merged. Expects columns first_seen_ts, title, url, news_day."""
    report = {"start": len(df)}
    df = df.sort_values("first_seen_ts")
    has_url = df["url"].notna()
    df = pd.concat([df[has_url].drop_duplicates("url"), df[~has_url]]).sort_values("first_seen_ts")
    report["after_same_url"] = len(df)

    df = df.assign(norm=df["title"].map(normalize_title))
    keep, last_seen = [], {}
    for idx, norm, ts in zip(df.index, df["norm"], df["first_seen_ts"]):
        prev = last_seen.get(norm)
        if prev is not None and (ts - prev) < timedelta(days=window_days):
            continue
        last_seen[norm] = ts
        keep.append(idx)
    df = df.loc[keep]
    report["after_same_title"] = len(df)

    drop = set()
    for _, day in df.groupby("news_day"):
        idxs, norms = list(day.index), list(day["norm"])
        for i in range(len(idxs)):
            if idxs[i] in drop:
                continue
            for j in range(i + 1, len(idxs)):
                if idxs[j] not in drop and SequenceMatcher(None, norms[i], norms[j]).ratio() >= fuzzy_threshold:
                    drop.add(idxs[j])
    df = df.drop(index=list(drop)).drop(columns="norm")
    report["after_near_identical"] = len(df)
    return df, report


def embedding_dedupe(df: pd.DataFrame, threshold: float = 0.92,
                     model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> pd.DataFrame:
    """Optional (needs requirements-dl.txt): drop later items whose title embedding has cosine > threshold
    with an earlier item of the same news day (docs/03 §2)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    df = df.sort_values("first_seen_ts")
    emb = model.encode(df["title"].tolist(), normalize_embeddings=True, show_progress_bar=False)
    pos = {idx: k for k, idx in enumerate(df.index)}
    drop = set()
    for _, day in df.groupby("news_day"):
        idxs = list(day.index)
        for i, a in enumerate(idxs):
            if a in drop:
                continue
            for b in idxs[i + 1:]:
                if b not in drop and float(emb[pos[a]] @ emb[pos[b]]) > threshold:
                    drop.add(b)
    return df.drop(index=list(drop))


# --- Pipeline ------------------------------------------------------------------------------------------
def build(frames: list[pd.DataFrame], trading_days: pd.DatetimeIndex, embed: bool = False):
    raw = pd.concat(frames, ignore_index=True)[HEADLINE_COLUMNS]
    report = {"collected": raw.groupby("source").size().to_dict()}

    df = raw.copy()
    df["first_seen_ts"] = to_utc(df["first_seen_utc"], df["date_only"])
    df["news_day"] = assign_news_day(df["first_seen_ts"], trading_days)
    # items before the first window (previous business day, 12:00 UTC) would pile up on the first day
    first_window_open = (pd.Timestamp(trading_days[0]) - pd.offsets.BDay(1)).tz_localize("UTC") + pd.Timedelta(
        hours=config.NEWS_CUTOFF_UTC.hour)
    df = df[df["news_day"].notna() & (df["first_seen_ts"] > first_window_open)]
    df = df[df["lang"].fillna("en").eq("en")]
    report["in_grid_english"] = df.groupby("source").size().to_dict()

    rel = [is_relevant(t, l) for t, l in zip(df["title"], df["lead"])]
    df = df.assign(matched_terms=[", ".join(m) for _, m in rel])[[k for k, _ in rel]]
    report["relevant"] = df.groupby("source").size().to_dict()

    df, report["dedupe"] = dedupe(df)
    if embed:
        df = embedding_dedupe(df)
        report["dedupe"]["after_embedding"] = len(df)

    text = df["title"] + " " + df["lead"].fillna("")
    for col, pattern in _TOPIC_RE.items():
        df[col] = text.map(lambda t, p=pattern: int(bool(p.search(t))))
    df["is_brief"] = df["title"].str.startswith("BRIEF-").astype(int)
    report["final"] = df.groupby("source").size().to_dict()
    report["lead_missing_share"] = df.groupby("source")["lead"].apply(lambda s: round(s.isna().mean(), 2)).to_dict()

    per_day = df.groupby("news_day").size().reindex(trading_days, fill_value=0)
    per_day = per_day[(per_day.index >= df["news_day"].min()) & (per_day.index <= df["news_day"].max())]
    report["volume"] = {
        "trading_days": len(per_day),
        "mean_per_day": round(float(per_day.mean()), 1),
        f"days_below_{config.MIN_HEADLINES_PER_DAY}": int((per_day < config.MIN_HEADLINES_PER_DAY).sum()),
        "days_with_zero": int((per_day == 0).sum()),
    }
    clean = df.drop(columns="first_seen_ts").sort_values(["news_day", "first_seen_utc"]).reset_index(drop=True)
    return raw, clean, per_day.rename("n_headlines"), report


def _save(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
    except ImportError:  # pyarrow missing
        path = path.with_suffix(".csv")
        df.to_csv(path, index=False)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--factiva", type=Path)
    parser.add_argument("--gdelt", type=Path)
    parser.add_argument("--scraped", nargs="*", default=[], help="scraped sources, e.g. hellenic gcaptain")
    parser.add_argument("--trading-days", type=Path, help="CSV whose first column holds the 5TC dates")
    parser.add_argument("--start", type=date.fromisoformat, default=config.COLLECTION_START)
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--embed-dedup", action="store_true", help="also drop embedding near-duplicates")
    args = parser.parse_args()

    frames = []
    if args.factiva:
        frames.append(load_factiva(args.factiva))
    if args.gdelt:
        frames.append(load_gdelt(args.gdelt))
    frames += [load_scraped(s) for s in args.scraped]
    if not frames:
        parser.error("give at least one source")

    grid = load_trading_days(args.start, args.end + timedelta(days=10), args.trading_days)
    raw, clean, per_day, report = build(frames, grid, embed=args.embed_dedup)
    paths = [_save(raw, config.TEXT_DIR / "headlines.parquet"),
             _save(clean, config.TEXT_DIR / "headlines_clean.parquet"),
             _save(per_day.rename_axis("date").reset_index(), config.TEXT_DIR / "headlines_per_day.parquet")]
    print(json.dumps(report, indent=2, default=str))
    print("\nSaved:", *paths, sep="\n  ")


if __name__ == "__main__":
    main()
