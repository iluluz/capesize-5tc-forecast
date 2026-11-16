"""Turn manual Factiva .docx exports into one clean table (one row per unique article).

Usage:  python factiva_clean.py "<folder with .docx exports>" <output.csv>
Keeps only headline + lead paragraph (scope doc: no full text). Output stays PRIVATE (licensed Reuters content).
"""
import glob, hashlib, re, sys
from pathlib import Path
import docx
import pandas as pd

META = re.compile(r"^(?P<src>[^,]+), (?P<date>\d{1,2} \w+ \d{4})(?:, (?P<time>\d{1,2}:\d{2} [ap]m) GMT)?, (?P<words>[\d,]+) words, (?P<lang>\w+)")
CUTOFF_HOUR_UTC = 12                     # repo contract C3: news up to 12:00 UTC on day t counts for t
TOPICS = {"freight": r"capesize|dry ?bulk|bulk carrier|baltic", "hormuz": r"hormuz",
          "ironcoal": r"iron ore|coking coal|thermal coal"}


def parse(path):
    paras = [p.text.strip() for p in docx.Document(path).paragraphs]
    rows = []
    for i, p in enumerate(paras):
        m = META.match(p)
        if not m:
            continue
        j = i - 1
        while j >= 0 and not paras[j]:
            j -= 1
        k = i + 1
        while k < len(paras) and not paras[k]:
            k += 1
        ts = m["date"] + (" " + m["time"] if m["time"] else " 11:59 pm")   # date-only -> end of day (conservative)
        rows.append({"title": paras[j], "lead": paras[k] if k < len(paras) else "", "source": m["src"],
                     "published_raw": p, "time_missing": m["time"] is None,
                     "published_utc": pd.to_datetime(ts, format="%d %B %Y %I:%M %p").tz_localize("UTC"),
                     "words": int(m["words"].replace(",", "")), "file": Path(path).name})
    return rows


def news_day(ts):
    """Weekday whose window (12:00 UTC previous weekday, 12:00 UTC day t] contains ts.
    Weekdays only for now; switch to the repo's calendar.assign_news_day with real 5TC dates later."""
    d = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    late = (d - d.dt.normalize()) > pd.Timedelta(hours=CUTOFF_HOUR_UTC)   # exactly 12:00 still counts for day t
    day = d.dt.normalize() + pd.to_timedelta(late.astype(int), unit="D")
    return day.apply(lambda x: x if x.weekday() < 5 else x + pd.offsets.BDay(1))


def main(folder, out):
    rows = [r for f in sorted(glob.glob(str(Path(folder) / "*.docx"))) for r in parse(f)]
    df = pd.DataFrame(rows)
    n_raw = len(df)
    df["title_key"] = df["title"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    df = df.sort_values("published_utc").drop_duplicates(["title_key", "published_utc"])
    df["id"] = (df["title_key"] + df["published_utc"].astype(str)).map(lambda s: hashlib.md5(s.encode()).hexdigest()[:12])
    text = df["title"] + " " + df["lead"]
    for t, rx in TOPICS.items():
        df[f"topic_{t}"] = text.str.contains(rx, case=False).astype(int)
    df["is_flash"] = (df["title"] == df["title"].str.upper()).astype(int)   # ALL-CAPS breaking-news alerts
    df["news_date"] = news_day(df["published_utc"])
    df = df[(df["published_utc"] >= "2025-08-01") & (df["published_utc"] < "2026-11-06")]
    cols = ["id", "news_date", "published_utc", "published_raw", "time_missing", "source", "title", "lead",
            "topic_freight", "topic_hormuz", "topic_ironcoal", "is_flash", "words", "file"]
    df[cols].to_csv(out, index=False, encoding="utf-8")
    print(f"{n_raw} rows read -> {len(df)} unique articles -> {out}")
    print("missing time:", int(df.time_missing.sum()), "| flashes:", int(df.is_flash.sum()))
    print(df[["topic_freight", "topic_hormuz", "topic_ironcoal"]].sum().to_string())
    m = df.groupby(df.published_utc.dt.strftime("%Y-%m")).size()
    print("articles per month:\n" + m.to_string())
    bd = pd.bdate_range("2025-09-01", "2026-11-05")
    per_day = df.groupby("news_date").size().reindex(bd, fill_value=0)
    print(f"business days {len(bd)} | avg articles/day {per_day.mean():.1f} | days with 0: {(per_day == 0).sum()}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
